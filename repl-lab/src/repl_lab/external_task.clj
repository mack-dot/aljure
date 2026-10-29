(ns repl-lab.external-task
  "External-context task adapter for the existing controller and isolated SCI."
  (:require [clojure.java.io :as io] [clojure.string :as str] [repl-lab.util :as u] [repl-lab.controller :as c]
            [repl-lab.runtime :as runtime] [repl-lab.provider :as provider]
            [repl-lab.execution :as execution] [repl-lab.isolation :as isolation]
            [repl-lab.gateway :as gateway] [repl-lab.records :as records]
            [repl-lab.model-protocol :as wire]))

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
                                           cache-breakpoints))
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
        (catch Exception e (c/recover! store run) (throw e))))))

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
          ;; A failure after the run starts still leaves events and a result.
          result (try (runtime/run-session! {:store store :run run :registry out :workers (atom {}) :prewarmed (atom {})
                                             :allow-learning false
                                             :base-instructions base
                                             :provider (->ExternalProvider (assoc model-config :tools (wire/tool-definitions config)) gateway-config)
                                             :initialize-worker (partial initialize-context! context (wire/assisted? config)
                                                                         (boolean (get-in config [:contract :structured-labels])))}
                                            "root" {:task task :context-handle "context" :repl-binding "external-context"})
                      (catch Exception e {:error (str "Task failed after start: " (.getMessage e)) :status :failed}))
          ledger (c/get-run store run)]
      (records/write-events! (str out "/events.jsonl") (:events ledger))
      (when (and (not (:error result)) (string? (:summary result)))
        (u/atomic-write! (str out "/answer.txt") (:summary result)))
      (u/write-json! (str out "/result.json") (cond-> {:status (if (:error result) "error" "completed") :result result
                                                       :spent (:spent ledger) :reserved (:reserved ledger)}
                                                (not (:error result)) (assoc :finalization (finalization (:events ledger)))))
      (emit! {:type "external_agent_complete" :native_exit_code (if (:error result) 2 0)}))
    (catch Exception _ (emit! {:type "external_agent_complete" :native_exit_code 2 :error "External task failed; inspect preserved artifacts"}))
    (finally (shutdown-agents))))
