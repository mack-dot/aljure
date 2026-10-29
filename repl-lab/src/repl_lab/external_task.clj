(ns repl-lab.external-task
  "External-context task adapter for the existing controller and isolated SCI."
  (:require [clojure.java.io :as io] [clojure.string :as str] [repl-lab.util :as u] [repl-lab.controller :as c]
            [repl-lab.runtime :as runtime] [repl-lab.provider :as provider]
            [repl-lab.execution :as execution] [repl-lab.isolation :as isolation]
            [repl-lab.gateway :as gateway] [repl-lab.records :as records]
            [repl-lab.model-protocol :as wire] [repl-lab.skills :as skills]
            [repl-lab.executable :as executable] [repl-lab.limits :as limits]
            [repl-lab.acquisition :as acquisition] [repl-lab.capture :as capture]))

(defn emit! [value] (println (u/json-str value)) (flush))
(defn receive! [] (u/json-read (read-line)))

(def ephemeral {:type "ephemeral"})
(defn cache-breakpoints
  "Prompt caching as native Prime uses it: the tools and the end of the
  conversation carry cache_control, so an append-only history is read from cache
  on the next call. Only the request copy is marked; stored history is unchanged."
  [body]
  (let [mark-last (fn [blocks] (update blocks (dec (count blocks)) assoc :cache_control ephemeral))]
    (cond-> (update-in body [:messages (dec (count (:messages body))) :content]
                       #(mark-last (if (string? %) [{:type "text" :text %}] (vec %))))
      (seq (:tools body)) (update :tools (comp mark-last vec)))))

(defn provider-input-record
  "Tool-mode history only grows, so the ledger records what each request appends;
  the full body stays in the task's stdout trace, and its hash is kept here."
  [events id session messages]
  (let [previous (or (some #(when (and (= :provider-input (:type %)) (= session (get-in % [:payload :session])))
                              (get-in % [:payload :message-count]))
                           (reverse events))
                     0)]
    (u/ensure! (<= previous (count messages)) "Session history shrank" {})
    {:request-id id :session session :message-count (count messages)
     :appended (vec (drop previous messages)) :input-hash (u/hash-value messages)}))

(defrecord ExternalProvider [model-config gateway-config]
  provider/Provider
  (invoke! [_ store run session messages]
    (let [id (str (java.util.UUID/randomUUID)) ledger (c/get-run store run)
          _ (c/within-time! ledger)
          body (cond-> (merge {:model (:model model-config) :messages messages :max_tokens (:max-output gateway-config) :stream false}
                              (:pinned-settings gateway-config))
                 ;; Sonnet 5.5 rejects forced tool choice; auto with one call per turn.
                 (:tools model-config) (-> (assoc :tools (:tools model-config)
                                                  :tool_choice {:type "auto" :disable_parallel_tool_use true})
                                           ;; The proposal turn (acquisition) is the task's last call; no cache write.
                                           (cond-> (not (false? (:cache model-config))) cache-breakpoints)))
          bound (gateway/reservation gateway-config body)]
      (c/reserve! store run id session (:tokens bound) (:usd bound))
      (c/update-run! store run #(c/event % :provider-input (provider-input-record (:events %) id session messages)))
      (try
        (emit! {:type "external_provider_request" :id id :session session
                :parent (get-in ledger [:sessions session :parent]) :body body})
        (let [reply (receive!) _ (u/ensure! (= id (:id reply)) "Gateway response ID differs" {})
              response (:response reply) _ (u/ensure! (= 200 (:status response)) "External gateway rejected request" {})
              message (u/json-read (:body response)) usage (:usage message)
              charge (gateway/usage-cost (:rates gateway-config) usage)
              actual (merge charge {:model (:model message) :requested-model (:model model-config) :provider-id (:id message)
                                    :usage usage :provenance :external-gateway
                                    :request-id id :content (:content message) :stop-reason (:stop_reason message)
                                    :text (apply str (map :text (filter #(= "text" (:type %)) (:content message))))})]
          (c/reconcile! store run id actual)
          (u/ensure! (= (:model model-config) (:model actual)) "Model differs from external pin" {})
          actual)
        (catch Exception e (c/recover! store run id) (throw e))))))

(defn initialize-context!
  ([text assisted backend worker] (initialize-context! text assisted false backend worker))
  ([text assisted verify backend worker]
   ;; Bind the same entire public context Prime receives as a file. Chunks stay
   ;; below the existing worker wire bound and never enter model conversations.
   (execution/evaluate! backend worker "(do (def external-context \"\") nil)" {})
   (doseq [chunk (partition-all 4096 text)]
     (execution/evaluate! backend worker "(do (def external-context (str external-context chunk)) nil)"
                          {:chunk (apply str chunk)}))
   ;; The assisted surface's helpers (resources/sci-prelude.edn) load on every
   ;; new worker, so a replaced worker offers the same contract.
   (when assisted
     (execution/evaluate! backend worker (slurp "resources/sci-prelude.edn") {})
     (execution/evaluate! backend worker "(do (def context-lines (vec (clojure.string/split-lines external-context))) nil)" {})
     ;; Verification helpers exist only when the plan enables them; otherwise the worker is unchanged.
     (when verify
       (execution/evaluate! backend worker (slurp "resources/sci-verify.edn") {})))))

(defn instructions [config]
  (if (wire/assisted? config)
    (str (str/replace (slurp "resources/external-tools-assisted.txt") "{{SCI_RULES}}"
                      (str/join "\n" (map #(str "- " %) (wire/sci-rules config))))
         ;; Nested review levels, each enabled only with the one before it.
         (when (get-in config [:contract :structured-labels])
           (str "\n" (slurp "resources/structured-labels.txt")))
         (when (get-in config [:contract :uncertainty-audit])
           (slurp "resources/uncertainty-audit.txt"))
         (when (get-in config [:contract :targeted-review])
           (slurp "resources/targeted-review.txt")))
    (slurp "resources/external-tools.txt")))

(defn finalization
  "How the root's answer was delivered: a done call, or an accepted terminal text answer."
  [events]
  (if (some #(and (= :terminal-text-accepted (:type %)) (= "root" (get-in % [:payload :session]))) events)
    "terminal-text" "done"))

(defn sci-settings [config]
  (let [{:keys [surface results]} (:sci config)
        surface (keyword (or surface "raw")) results (keyword (or results "raw"))]
    (u/ensure! (and (#{:raw :assisted} surface) (#{:raw :bounded} results)
                    (or (= :raw results) (= :assisted surface)))
               "Unsupported SCI settings" {:surface surface :results results})
    (-> config (dissoc :sci) (assoc :sci-surface surface :sci-results results))))

(defn task-input
  "The root task. The approved-functions note appears only when aljure_contract.artifacts
  preloaded at least one function; otherwise the message is unchanged."
  [task note]
  (cond-> {:task task :context-handle "context" :repl-binding "external-context"}
    note (assoc :approved-functions note)))

(defn supply-source
  "Pilot 1 positive control (aljure_contract.artifacts.supply \"applied\"): the controller applies
  the preloaded exports, as a cascade in library order, to the text of every record line and
  binds one label (or nil where none decides) per record, in context order. Counts are returned."
  [names]
  (str "(do (def library-labels (let [fs [" (str/join " " names) "]] "
       "(vec (for [line (clojure.string/split-lines external-context) "
       ;; The worker's reader takes no regex literal; the pattern is built from a string.
       ":let [m (re-find (re-pattern \"\\\\|\\\\| Instance: (.*)$\") line)] :when m] "
       "(some (fn [f] (let [v (f (second m))] (when (string? v) v))) fs))))) "
       "{:records (count library-labels) :decided (count (filter some? library-labels))})"))

(def supplied-note
  (str "Controller-applied: library-labels holds one entry per record line, in context order: the label "
       "these functions assign, or nil where none decides. Records with nil need your own handling."))

(defn prepare-artifacts!
  "aljure_contract.artifacts, off by default. Before the first model call the controller
  discovers the approved entries of the pinned library, runs each applicability predicate
  on the public input in the root's first isolated worker, records every decision, preloads
  the applicable functions and hands that worker to the root session. Replacement and child
  workers get the same functions without a second check. No model call is made."
  [{:keys [store run spec initialize question prewarmed context]}]
  ;; The frozen plan fixes the root (benchmark/paired.py); every byte read is hash-verified.
  (let [{:keys [library library_sha256 supply]} spec
        _ (u/ensure! (string? library) "Artifact library root required" {})
        found (skills/discover library library_sha256)
        r (c/get-run store run) backend (execution/for-run r)
        _ (c/update-run! store run #(c/event % :artifact-library-loaded
                                     {:library-sha256 library_sha256 :statuses (:statuses found) :approved (count (:approved found))}))
        worker (runtime/open-worker! {:initialize-worker initialize} backend (:deadline-ms (limits/from-run r)))]
    (try
      (let [checked (mapv #(assoc % :check (executable/applicability! backend worker (:predicate %) {:question question}))
                          (:approved found))
            {:keys [functions decisions]} (executable/preload-plan checked)
            ;; Arm C's exact-reuse memo (only when the version names one): the controller hashes this
            ;; context's record texts and defines exact-label over the exact matches only.
            memo (when (:memo found)
                   (let [hits (acquisition/memo-hits (skills/load-memo library (:memo found)) (str context))
                         exact (acquisition/exact-label-function)]
                     (c/update-run! store run #(c/event % :artifact-memo-loaded {:memo-sha256 (:memo found) :hits (count hits)}))
                     {:hits hits :function exact
                      :decision {:artifact nil :code-hash (:code-hash exact) :applicability-code-hash nil :name (:name exact)
                                 :decision (if (seq hits) :preload :refuse) :reason (if (seq hits) :exact-match :no-exact-match)}}))
            decisions (cond-> decisions memo (conj (:decision memo)))
            functions (cond-> functions (seq (:hits memo)) (conj (:function memo)))
            memo-sources (when (seq (:hits memo)) (acquisition/memo-chunks (:hits memo)))
            _ (doseq [decision decisions] (c/update-run! store run #(c/event % :artifact-applicability decision)))
            loaded (atom 0)
            install! (fn [backend worker]
                       (let [begin (System/nanoTime) n (dec (swap! loaded inc))]
                         (doseq [[source bindings] memo-sources] (execution/evaluate! backend worker source bindings))
                         (executable/install! backend worker functions)
                         (when (= "applied" supply)
                           (let [names (keep #(when (= :export (:role %)) (:name %)) functions)
                                 counts (execution/evaluate! backend worker (supply-source names) {})]
                             (c/update-run! store run #(c/event % :artifact-supplied
                                                        (merge {:worker n :binding "library-labels"} counts)))))
                         (c/update-run! store run #(c/event % :artifact-preloaded
                                                    {:worker n :elapsed-ms (/ (- (System/nanoTime) begin) 1e6)
                                                     :functions (mapv (fn [f] (select-keys f [:name :arity :hash :code-hash :role])) functions)}))))
            by-code (into {} (map (fn [f] [(:code-hash f) {:name (:name f) :artifact (:hash f)}]) functions))
            record! (fn [{:keys [backend worker session op call-sequence current?]}]
                      (when current?
                        (try
                          (let [drained (executable/drain! backend worker (set (keys by-code)))]
                            (when (or (:error drained) (seq (:invocations drained)))
                              (c/update-run! store run #(c/event % :artifact-invocations
                                                         (merge {:session session :op op :call-sequence call-sequence}
                                                                (update drained :invocations
                                                                        (fn [items] (mapv (fn [i] (merge i (by-code (:code-hash i)))) items))))))))
                          (catch Exception _ nil))))]
        (when (seq functions) (install! backend worker))
        (swap! prewarmed assoc "root" (doto (promise) (deliver worker)))
        {:note (cond-> (skills/capability-note functions)
                 (and (= "applied" supply) (seq functions)) (assoc :supplied supplied-note))
         :env (when (seq functions)
                {:initialize-worker (fn [backend worker] (initialize backend worker) (install! backend worker))
                 :on-evaluated record!})})
      (catch Exception e (execution/close! backend worker) (throw e)))))

;; aljure_contract.acquisition, off by default (arms C and E of the thesis pilot).
(defn proposal-turn!
  "Runs from runtime's :after-root-done hook: the root's answer is written to answer.txt
  and answer-recorded.json first, then one optional proposal turn (acquisition/propose!)
  may follow. The turn offers the task tools plus the two proposal tools and writes no
  cache entry; it cannot change the recorded answer."
  [{:keys [store run out arm mode model-config gateway-config question library-sha256 provider]} {:keys [result] :as done}]
  (when (string? (:summary result))
    (u/atomic-write! (str out "/answer.txt") (:summary result))
    (u/write-json! (str out "/answer-recorded.json") {:sha256 (u/sha (:summary result)) :before-proposal true}))
  (let [r (c/get-run store run) config (:config r) mode (or mode "optional")
        ;; Capture mode: functions the model defined during this task, read (never run) from its recorded code.
        candidates (when (= "capture" mode)
                     (capture/candidates (vec (for [e (:events r)
                                                    :when (and (= :tool-call (:type e)) (= "root" (get-in e [:payload :session]))
                                                               (= :repl/eval (keyword (get-in e [:payload :command :op]))))]
                                                (get-in e [:payload :command :source])))))
        eligible (filterv (comp empty? :reasons) candidates)]
    (acquisition/propose!
      {:store store :run run :arm arm :mode mode :candidates candidates :config config :out out :question question
       :library-sha256 library-sha256
       :backend (execution/for-run (c/get-run store run))
       ;; Tests pass a scripted provider; a task always uses the external gateway.
       :provider (or provider
                     (->ExternalProvider (assoc model-config :cache false
                                                :tools (into (wire/tool-definitions config) (acquisition/proposal-tools arm mode eligible)))
                                         gateway-config))}
      done)))

(defn -main [out]
  (try
    (let [{:keys [task context config gateway-config model-config]} (receive!)
          _ (isolation/require-tested!)
          _ (u/ensure! (and (string? context) (<= (count (.getBytes context "UTF-8")) 1500000)) "External context limit" {})
          _ (u/ensure! (not (.exists (io/file out))) "Use a fresh task output" {})
          ;; Native tool turns must stay append-only: provider thinking blocks and
          ;; tool_use/tool_result pairs are invalid once earlier turns are dropped.
          ;; Call, token, cost and time budgets still bound the conversation.
          config (-> (sci-settings config) (assoc :response-envelope wire/tool-envelope-version)
                     (assoc-in [:limits :history-records] Integer/MAX_VALUE))
          store (str out "/controller.sqlite") run "external-task"
          _ (c/create-run! store run config nil) _ (c/session! store run "root" nil)
          _ (c/put-context-block! store run "context" (mapv (fn [i line] {:line i :text line}) (range) (str/split-lines context)))
          base (str (instructions config)
                    "\nThis is an external-context benchmark. The immutable complete public text is already bound to external-context in each SCI worker. "
                    "Inspect or compute over it through repl_eval without loading it into the model window. The context handle also permits line queries. "
                    "Finish with done: put the exact benchmark answer in summary, or compute it in SCI and pass source. "
                    "The answer is scored externally.\n")
          artifacts (get-in config [:contract :artifacts])
          initialize (partial initialize-context! context (wire/assisted? config)
                              (boolean (get-in config [:contract :structured-labels])))
          prewarmed (atom {})
          acquire (get-in config [:contract :acquisition])
          proposal (atom nil)
          ;; A failure after the run starts still leaves events and a result.
          result (try (let [prepared (when artifacts
                                       (prepare-artifacts! {:store store :run run :spec artifacts :initialize initialize
                                                            :question (when (map? task) (:question task)) :prewarmed prewarmed
                                                            :context context}))]
                        (runtime/run-session! (merge {:store store :run run :registry out :workers (atom {}) :prewarmed prewarmed
                                                      :allow-learning false
                                                      :base-instructions base
                                                      :provider (->ExternalProvider (assoc model-config :tools (wire/tool-definitions config)) gateway-config)
                                                      :initialize-worker initialize}
                                                     (:env prepared)
                                                     (when acquire
                                                       {:after-root-done
                                                        (fn [done]
                                                          (reset! proposal
                                                                  (proposal-turn! {:store store :run run :out out :arm (:arm acquire) :mode (:mode acquire)
                                                                                   :model-config model-config :gateway-config gateway-config
                                                                                   :question (when (map? task) (:question task))
                                                                                   :library-sha256 (:library_sha256 artifacts)}
                                                                                  done)))}))
                                              "root" (task-input task (:note prepared))))
                      (catch Exception e {:error (str "Task failed after start: " (.getMessage e)) :status :failed}))
          _ (when artifacts
              (c/update-run! store run #(c/event % :artifact-reuse-summary (skills/reuse-summary (:events %) result))))
          ledger (c/get-run store run)]
      (records/write-events! (str out "/events.jsonl") (:events ledger))
      (when (and (not (:error result)) (string? (:summary result)))
        (u/atomic-write! (str out "/answer.txt") (:summary result)))
      (u/write-json! (str out "/result.json") (cond-> {:status (if (:error result) "error" "completed") :result result
                                                       :spent (:spent ledger) :reserved (:reserved ledger)}
                                                (not (:error result)) (assoc :finalization (finalization (:events ledger)))
                                                artifacts (assoc :artifact-reuse (some #(when (= :artifact-reuse-summary (:type %)) (:payload %))
                                                                                       (:events ledger)))
                                                ;; Acquisition cost (session "proposal") is reported apart from task inference.
                                                acquire (assoc :acquisition (merge (or @proposal {:decision :not-offered :reason :no-recorded-answer})
                                                                                   {:spend (acquisition/acquisition-spend ledger)}))))
      (emit! {:type "external_agent_complete" :native_exit_code (if (:error result) 2 0)}))
    (catch Exception _ (emit! {:type "external_agent_complete" :native_exit_code 2 :error "External task failed; inspect preserved artifacts"}))
    (finally (shutdown-agents))))
