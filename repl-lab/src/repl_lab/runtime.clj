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
   :skills/list #{:op} :skills/describe #{:op :hash} :policy/select #{:op :hash}})
(declare run-session!)
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
      :repl/eval (let [backend (execution/for-run r)
                      worker (or (get @workers session)
                                  (let [new (open-worker! env backend (:deadline-ms (limits/from-run r)))] (swap! workers assoc session new) new))]
                   {:value (execution/evaluate! backend worker (:source command) (:bindings command))})
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

(defn run-session! [{:keys [store run provider workers] :as env} session task]
  (try
    (loop [messages (let [r (c/get-run store run) base (or (:base-instructions env) (wire/instructions (:config r)))
                          history (->> (get-in r [:sessions session :history]) (filter :role)
                                       (remove #(str/starts-with? (:content %) base))
                                       (take-last (get-in r [:config :limits :history-records])))]
                      (vec (concat [{:role "user" :content base}] history [{:role "user" :content (wire/write-value (:config r) task)}]))) n 0]
      (u/ensure! (< n 64) "Session tool-step limit" {})
      (let [response (p/invoke! provider store run session messages)
            command (wire/parse-command (:config (c/get-run store run)) (:text response))]
        (if (= :done (:op command))
          (let [result (broker! env session command)]
            (c/finish-session! store run session :complete result) result)
          (let [result (try (broker! env session command)
                            (catch Exception e {:error (.getMessage e)}))
                r (c/get-run store run) cap (get-in r [:config :limits :history-records])
                next (into [(first messages)]
                           (take-last cap (concat (rest messages)
                                                  [{:role "assistant" :content (:text response)}
                                                   {:role "user" :content (wire/write-value (:config r) result)}])))]
            (c/update-run! store run #(assoc-in % [:sessions session :history] next))
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
          (isolation/close-session! worker) (swap! workers dissoc id))))))

(defn workflow! [store run workflow context-handle child-call]
  (let [strategy (get-in workflow [:forms :strategy])
        _ (u/ensure! (and (map? strategy) (map? (:context strategy)) (string? (:policy strategy))) "Invalid workflow" {})
        selected (c/context store run context-handle (:context strategy))
        result (when-let [delegation (:delegate strategy)] (child-call (:task delegation) (:records selected)))]
    (c/update-run! store run #(c/event % :workflow-invoked
                                     {:artifact (:hash workflow) :input-handle context-handle
                                      :selected (:records selected) :child-result result :policy (:policy strategy)}))
    {:policy (:policy strategy) :evidence selected :child-result result}))
