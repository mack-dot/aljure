(ns repl-lab.runtime
  (:require [clojure.string :as str] [repl-lab.util :as u] [repl-lab.controller :as c] [repl-lab.provider :as p]
            [repl-lab.artifact :as a] [repl-lab.isolation :as isolation] [repl-lab.limits :as limits]
            [repl-lab.execution :as execution] [repl-lab.executable :as executable]
            [repl-lab.python-source :as python] [repl-lab.model-protocol :as wire]
            [repl-lab.skills :as skills]))

(def schemas
  {:context/query #{:op :handle :query} :context/metadata #{:op :handle}
   :repl/eval #{:op :source :bindings} :agent/call #{:op :id :task :context}
   :message/send #{:op :recipient :correlation-id :payload} :message/receive #{:op}
   :agent/await #{:op :id} :agent/cancel #{:op :id}
   :artifact/submit #{:op :category :source :interface :dependencies :parent}
   :artifact/inspect #{:op :hash}
   :artifact/subtree #{:op :hash :path}
   :artifact/patch #{:op :hash :base-hash :path :expected-hash :replacement :dependencies}
   :artifact/call #{:op :hash :arguments}
   :development/evaluate #{:op :hash} :policy/use #{:op :source} :done #{:op :summary}
   ;; Finish with a summary computed in this session's SCI worker.
   :done/eval #{:op :source}
   :skills/list #{:op} :skills/describe #{:op :hash} :policy/select #{:op :hash}})
(declare run-session!)
;; Matches Prime's 8 MiB answer file limit (/work fsize).
(def answer-limit-chars (* 8 1024 1024))
(defn artifact-provenance [env]
  (if (= :synthetic-fixture (:provenance env)) :developer-fixture :model-generated))

(defn artifact-input [ledger input]
  (cond-> input (= :python (get-in ledger [:config :execution-language])) (assoc :language :python)))

(defn stage! [env session artifact]
  (let [{:keys [registry store run]} env]
    (a/dependency-closure registry artifact)
    (a/save! registry artifact)
    (c/update-run! store run #(c/event % :artifact-staged {:hash (:hash artifact) :session session}))
    {:hash (:hash artifact) :status :staged}))

(defn open-worker! [env backend deadline]
  (let [worker (execution/open! backend deadline)]
    (try
      (when-let [initialize (:initialize-worker env)] (initialize backend worker))
      worker
      (catch Exception e (execution/close! backend worker) (throw e)))))

(defn prewarm!
  "With (:prewarmed env), open a session's next worker in the background, so
  its cold start overlaps a model call. Opening a worker needs nothing from the
  model. A failed open is thrown where the worker is taken, as before."
  [{:keys [store run prewarmed] :as env} session]
  (when prewarmed
    (locking prewarmed
      (when-not (get @prewarmed session)
        (let [r (c/get-run store run) deadline (:deadline-ms (limits/from-run r))]
          (swap! prewarmed assoc session (future (open-worker! env (execution/for-run r) deadline))))))))

(defn- take-prewarmed! [{:keys [prewarmed]} session]
  (when-let [pending (some-> prewarmed deref (get session))]
    (swap! prewarmed dissoc session)
    @pending))

(defn- close-prewarmed! [{:keys [prewarmed]} close?]
  (doseq [[id pending] (some-> prewarmed deref) :when (close? id)]
    (swap! prewarmed dissoc id)
    ;; Wait for an open in progress: its container must be closed too.
    (when-let [worker (try (deref pending 60000 nil) (catch Exception _ nil))]
      (isolation/close-session! worker))))

(defn broker! [{:keys [store run registry provider workers development-evaluator allow-learning] :as env} session command]
  (let [r (c/get-run store run) op (:op command) s (get-in r [:sessions session])]
    (c/within-time! r)
    (u/ensure! (and s (= :ready (:status s))) "Session cannot use broker" {})
    (u/ensure! (= (get schemas op) (set (keys command))) "Unknown capability or invalid schema" {:op op})
    (u/ensure! (<= (count (.getBytes (pr-str command) "UTF-8")) 32768) "Tool request too large" {})
    (let [started-ns (System/nanoTime)
          called (c/update-run! store run #(c/event % :tool-call {:session session :command command :artifact (:artifact s)
                                                                :started-ms (System/currentTimeMillis)}))
          call-sequence (dec (:sequence called))]
      (try
        (binding [python/*deadline-ms* (:deadline-ms (limits/from-run r))]
        (let [result (case op
      :context/query (c/context store run (:handle command) (:query command))
      :context/metadata (dissoc (c/context store run (:handle command) {:limit 1 :select []}) :records)
      (:repl/eval :done/eval)
      (let [backend (execution/for-run r) config (:config r)
            ;; Read and wrap source before any worker is touched.
            source (cond (= :done/eval op) (wire/answer-source config (:source command))
                         (wire/assisted? config) (wire/assisted-source config op (:source command))
                         :else (:source command))
            worker (or (get @workers session)
                       (let [new (or (take-prewarmed! env session)
                                     (open-worker! env backend (:deadline-ms (limits/from-run r))))]
                         (swap! workers assoc session new) new))
            evaluate! (fn [source bindings]
                        (try (execution/evaluate! backend worker source bindings)
                             (catch Exception e
                               (let [message (str (.getMessage e))]
                                 ;; Only an expression error leaves the worker usable. After any other
                                 ;; failure (output limit, deadline, closed stream) retire the worker:
                                 ;; the task's final cleanup still closes it, and the next call starts afresh.
                                 (when-not (some #(str/starts-with? message %) ["Worker rejected expression" "Worker input too large"])
                                   (swap! workers #(-> % (dissoc session) (assoc (str session "/retired-" (System/nanoTime)) worker)))
                                   (prewarm! env session)
                                   (u/fail (str message ". The worker stopped; the next repl_eval starts a fresh worker with the "
                                                "same context, and earlier definitions are gone.") {}))
                                 (throw e)))))
            value (evaluate! source (get command :bindings {}))]
        (if (= :repl/eval op)
          {:value value}
          (let [[n checksum] (when (vector? value) value)
                ;; Pages of an eighth of the bound stay under it even for 4-byte characters with escapes.
                page (max 1024 (quot (isolation/output-bound) 8))]
            (u/ensure! (and (nat-int? n) (int? checksum)) "done source must evaluate to a string" {})
            (u/ensure! (<= n answer-limit-chars) "Answer exceeds the 8 MiB delivery limit" {:chars n})
            ;; The worker picks each page's end so a surrogate pair is never split;
            ;; a lone surrogate would not survive UTF-8 transport.
            (let [pages (loop [start 0 parts []]
                          (if (>= start n)
                            parts
                            (let [[end part] (evaluate! (str "(let [e (min " n " " (+ start page) ") "
                                                             "e (if (and (< e " n ") (<= 55296 (int (.charAt aljure-answer (dec e))) 56319)) (dec e) e)] "
                                                             "[e (subs aljure-answer " start " e)])") {})]
                              (u/ensure! (and (int? end) (< start end) (string? part)) "Answer page malformed" {})
                              (recur end (conj parts part)))))
                  answer (apply str pages)]
              (u/ensure! (and (= n (count answer)) (= checksum (hash answer))) "Answer delivery failed its length or hash check" {})
              (c/update-run! store run #(c/event % :answer-delivered {:session session :chars n :pages (count pages)
                                                                      :sha256 (u/sha answer)}))
              {:summary answer}))))
      :agent/call
      (let [id (:id command) _ (u/ensure! (and (string? id) (<= 1 (count id) 128) (not= id session)) "Invalid child ID" {})
            prior (get-in r [:sessions id])]
        (if prior
          (do (u/ensure! (= session (:parent prior)) "Only parent can resume child" {}) (c/resume-session! store run id))
          (c/session! store run id session))
        (c/send! store run {:message-id (str (java.util.UUID/randomUUID)) :run-id run :sender session :recipient id
                           :correlation-id id :schema-version 1 :payload (select-keys command [:task :context])})
        (let [result (run-session! env id (select-keys command [:task :context]))]
          (c/update-run! store run #(c/event % :child-result-consumed {:parent session :child id :result result}))
          result))
      :message/send (do (c/send! store run {:message-id (str (java.util.UUID/randomUUID)) :run-id run :sender session
                                           :recipient (:recipient command) :correlation-id (:correlation-id command)
                                           :schema-version 1 :payload (:payload command)}) {:sent true})
      :message/receive (let [messages (c/deliver! store run session)]
                         (doseq [m messages] (c/acknowledge! store run session (:message-id m) {:received (:payload m)}))
                         {:messages messages})
      :agent/await (do (u/ensure! (= session (get-in r [:sessions (:id command) :parent])) "Only parent can await child" {})
                      (c/await-status store run (:id command)))
      :agent/cancel (do (u/ensure! (= session (get-in r [:sessions (:id command) :parent])) "Only parent may cancel child" {})
                       (let [cancelled (c/cancel! store run (:id command))]
                         (doseq [[id worker] @workers :when (= :cancelled (get-in cancelled [:sessions id :status]))]
                           (isolation/close-session! worker) (swap! workers dissoc id)))
                       {:cancelled true})
      :artifact/submit (do
                         (u/ensure! allow-learning "Library is frozen" {})
                         (c/consume! store run :candidates 1)
                         (stage! env session
                           (a/make-artifact (artifact-input r (-> command (dissoc :op)
                             (assoc :author session :provenance (artifact-provenance env)))))))
      :skills/list {:skills (mapv skills/compact (skills/inventory registry (:artifact s)))}
      :skills/describe (skills/describe registry (:artifact s) (:hash command))
      :policy/select (let [target (skills/select-policy registry (:artifact s) (:hash command))]
                       (c/update-run! store run
                         #(-> % (update-in [:sessions session] dissoc :temporary-policy)
                              (assoc-in [:sessions session :selected-policy] (:hash target))
                              (c/event :policy-selected {:session session :hash (:hash target) :origin :approved-library})))
                       {:hash (:hash target) :scope :current-task-only :origin :approved-library})
      :artifact/inspect (wire/inspect-artifact (:config r) (a/load! registry (:hash command)))
      :artifact/subtree (let [artifact (a/load! registry (:hash command))
                             _ (u/ensure! (vector? (:path command)) "Subtree path must be a vector" {})
                             value (a/subtree (:forms artifact) (:path command))]
                         (merge {:hash (u/hash-value value)}
                                (if (and (wire/json? (:config r)) (= :clojure (a/language artifact)))
                                  {:value-edn (pr-str value)} {:value value})))
      :artifact/patch (do
                        (u/ensure! allow-learning "Library is frozen" {})
                        (c/consume! store run :candidates 1)
                        (let [base (a/load! registry (:hash command))]
                          (u/ensure! (= (a/language base) (get-in r [:config :execution-language] :clojure)) "Artifact language differs from session" {})
                          (stage! env session (a/patch base (assoc command :author session :provenance (artifact-provenance env))))))
      :artifact/call (let [active (a/load! registry (:artifact s))
                           approved (conj (a/dependency-closure registry active) active)
                           target (first (filter #(= (:hash command) (:hash %)) approved))
                           _ (u/ensure! target "Artifact is not in this session's approved library" {})
                           _ (u/ensure! (= (a/language target) (get-in r [:config :execution-language] :clojure)) "Artifact language differs from session" {})
                           value (executable/invoke! registry target (:arguments command) (:deadline-ms (limits/from-run r)))]
                       (c/update-run! store run #(c/event % :artifact-invoked
                                                 {:session session :hash (:hash target) :dependencies (:dependencies target)
                                                  :arguments (:arguments command) :value value :language (a/language target)}))
                       {:value value :artifact (:hash target)})
      :development/evaluate (do (u/ensure! (and allow-learning development-evaluator) "Development evaluation is unavailable" {})
                                (development-evaluator (:hash command)))
      :policy/use (let [artifact (a/make-artifact (artifact-input r {:category :policy :source (:source command)
                                                   :interface {:name "decide" :arity 2} :dependencies []
                                                   :author session :parent nil :provenance (artifact-provenance env)}))]
                    (c/update-run! store run #(-> % (update-in [:sessions session] dissoc :selected-policy)
                                                 (assoc-in [:sessions session :temporary-policy] artifact)))
                    {:hash (:hash artifact) :scope :current-task-only})
      :done {:summary (:summary command)})]
          (c/update-run! store run #(c/event % :tool-result {:session session :call-sequence call-sequence
                                                            :op op :status :ok :result result
                                                            :elapsed-ms (/ (- (System/nanoTime) started-ns) 1000000.0)}))
          result))
        (catch Exception e
          (c/update-run! store run #(c/event % :tool-result {:session session :call-sequence call-sequence
                                                            :op op :status :error :error (.getMessage e)
                                                            :elapsed-ms (/ (- (System/nanoTime) started-ns) 1000000.0)}))
          (throw e))))))

(defn selected-policy [registry ledger session default-policy]
  (or (get-in ledger [:sessions session :temporary-policy])
      (when-let [hash (get-in ledger [:sessions session :selected-policy])]
        (skills/select-policy registry (get-in ledger [:sessions session :artifact]) hash))
      default-policy))

(defn- response-evidence [response]
  {:provider-id (:provider-id response) :request-id (:request-id response)
   :response-hash (u/hash-value (select-keys response [:content :text :stop-reason]))})

(defn- retry-truncated-turn!
  "Transport recovery, separate from the model's format correction. A turn that
  ends for tool use with no tool call carried no command, so nothing ran and the
  same request can be sent again. Both calls are charged under the normal caps.
  The durable task counter bounds the retries; when it is spent, the task fails."
  [store run session response limit]
  (let [updated (c/update-run! store run
                  (fn [r]
                    (let [used (get r :transport-retries-issued 0) allowed (< used limit)]
                      (cond-> (c/event r :provider-turn-retried
                                (merge {:session session :reason :truncated-tool-turn :executed false
                                        :attempt (inc used) :retried allowed :stop-reason (:stop-reason response)
                                        :block-types (mapv :type (:content response))}
                                       (response-evidence response)))
                        allowed (update :transport-retries-issued (fnil inc 0))))))]
    (when-not (get-in (last (:events updated)) [:payload :retried])
      (u/fail "Provider turn truncated; transport retry budget exhausted" {:reason :truncated-tool-turn}))
    {:retry true}))

(defn response-command! [{:keys [store run]} session response]
  (let [ledger (c/get-run store run) config (:config ledger)
        retries (get-in config [:contract :truncated-turn-retries] 0)
        terminal-text (get-in config [:contract :terminal-text-answer] false)
        root? (nil? (get-in ledger [:sessions session :parent]))]
    (if (and (pos? retries) (wire/tool-envelope? config) (wire/truncated-tool-turn? response))
      (retry-truncated-turn! store run session response retries)
    (try {:command (wire/parse-response config response schemas)}
      (catch clojure.lang.ExceptionInfo e
        (let [{:keys [command-envelope-error reason recoverable]} (ex-data e)]
          (when-not command-envelope-error (throw e))
          (if-let [answer (and terminal-text root? (= :no-tool-call reason)
                               (get-in ledger [:sessions session :terminal-text-requested])
                               (wire/terminal-text-answer response))]
            ;; Only the reply to the FINAL ANSWER instruction, in the root session.
            (do (c/update-run! store run #(c/event % :terminal-text-accepted
                                            (merge {:session session :answer answer} (response-evidence response))))
                {:command {:op :done :summary answer}})
          ;; This counter belongs to the durable task ledger, not a session or
          ;; loop. Success, child creation and resume never replenish it.
          (let [terminal? (and terminal-text root? (= :no-tool-call reason))
                updated (c/update-run! store run
                          (fn [r]
                            (let [allowed (and recoverable (< (get r :command-corrections-issued 0) 1))]
                              (cond-> (c/event r :command-rejected
                                        (merge {:session session :reason reason :recoverable recoverable :executed false
                                                :text (:text response) :correction-requested allowed}
                                               (response-evidence response)))
                                allowed (update :command-corrections-issued (fnil inc 0))
                                (and allowed terminal?) (assoc-in [:sessions session :terminal-text-requested] true)))))
                allowed (get-in (last (:events updated)) [:payload :correction-requested])]
            (when-not allowed
              (u/fail "Command response rejected; no correction permitted" {:reason reason}))
            {:feedback (wire/write-value config
                         {:status :command-rejected :reason reason :executed false
                          :instruction (if terminal? (wire/terminal-text-instruction)
                                         (wire/correction-instruction config))})}))))))))

(defn next-messages! [store run session messages additions]
  (let [cap (get-in (c/get-run store run) [:config :limits :history-records])
        next (into [(first messages)] (take-last cap (concat (rest messages) additions)))]
    (c/update-run! store run #(assoc-in % [:sessions session :history] next))
    next))

(defn run-session! [{:keys [store run provider workers] :as env} session task]
  ;; Only the root starts a worker before its first repl_eval; a child may never use one.
  (when (nil? (get-in (c/get-run store run) [:sessions session :parent])) (prewarm! env session))
  (try
    (loop [messages (let [r (c/get-run store run) base (or (:base-instructions env) (wire/instructions (:config r)))
                          history (->> (get-in r [:sessions session :history]) (filter :role)
                                       (remove #(and (string? (:content %)) (str/starts-with? (:content %) base)))
                                       (take-last (get-in r [:config :limits :history-records])))]
                      (vec (concat [{:role "user" :content base}] history [{:role "user" :content (wire/write-value (:config r) task)}]))) n 0]
      (u/ensure! (< n (get-in (c/get-run store run) [:config :limits :session-steps] 64)) "Session tool-step limit" {})
      (let [response (p/invoke! provider store run session messages)
            {:keys [command feedback retry]} (response-command! env session response)]
        (cond
          ;; Same messages again: the truncated turn never enters history.
          retry (recur messages (inc n))

          feedback
          ;; The invalid bytes stay in evidence, not in a guessed command or
          ;; an assistant history entry that could be mistaken for execution.
          (recur (next-messages! store run session messages [{:role "user" :content feedback}]) (inc n))

          (= :done (:op command))
          (let [result (broker! env session command)]
            (c/finish-session! store run session :complete result) result)

          ;; A failed answer expression is an ordinary tool error; the session continues.
          (= :done/eval (:op command))
          (let [result (try (broker! env session command) (catch Exception e {:error (.getMessage e)}))]
            (if (:error result)
              (recur (next-messages! store run session messages
                       (wire/result-messages (:config (c/get-run store run)) response result)) (inc n))
              (do (c/finish-session! store run session :complete result) result)))

          :else
          (let [result (try (broker! env session command)
                            (catch Exception e {:error (.getMessage e)}))
                next (next-messages! store run session messages
                       (wire/result-messages (:config (c/get-run store run)) response result))]
            (recur next (inc n))))))
    (catch Exception e
      (c/finish-session! store run session :failed {:error (.getMessage e)})
      {:error (.getMessage e) :status :failed})
    (finally
      (let [state (get-in (c/get-run store run) [:sessions session])]
        ;; A completed child can be resumed in this task with its SCI bindings.
        ;; Root completion, cancellation, and failure release every task worker.
        (doseq [[id worker] @workers
                :when (or (nil? (:parent state)) (and (= id session) (not= :complete (:status state))))]
          (isolation/close-session! worker) (swap! workers dissoc id))
        (close-prewarmed! env #(or (nil? (:parent state)) (and (= % session) (not= :complete (:status state)))))))))

(defn workflow! [store run workflow context-handle child-call]
  (let [strategy (get-in workflow [:forms :strategy])
        _ (u/ensure! (and (map? strategy) (map? (:context strategy)) (string? (:policy strategy))) "Invalid workflow" {})
        selected (c/context store run context-handle (:context strategy))
        result (when-let [delegation (:delegate strategy)] (child-call (:task delegation) (:records selected)))]
    (c/update-run! store run #(c/event % :workflow-invoked
                                     {:artifact (:hash workflow) :input-handle context-handle
                                      :selected (:records selected) :child-result result :policy (:policy strategy)}))
    {:policy (:policy strategy) :evidence selected :child-result result}))
