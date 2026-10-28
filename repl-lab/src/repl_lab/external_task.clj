(ns repl-lab.external-task
  "External-context task adapter for the existing controller and isolated SCI."
  (:require [clojure.java.io :as io] [clojure.string :as str] [repl-lab.util :as u] [repl-lab.controller :as c]
            [repl-lab.runtime :as runtime] [repl-lab.provider :as provider]
            [repl-lab.execution :as execution] [repl-lab.isolation :as isolation]
            [repl-lab.gateway :as gateway] [repl-lab.records :as records]
            [repl-lab.model-protocol :as wire]))

(defn emit! [value] (println (u/json-str value)) (flush))
(defn receive! [] (u/json-read (read-line)))

(defrecord ExternalProvider [model-config gateway-config]
  provider/Provider
  (invoke! [_ store run session messages]
    (let [id (str (java.util.UUID/randomUUID)) ledger (c/get-run store run)
          _ (c/within-time! ledger)
          body (merge {:model (:model model-config) :messages messages :max_tokens (:max-output gateway-config) :stream false}
                      (:pinned-settings gateway-config))
          bound (gateway/reservation gateway-config body)]
      (c/reserve! store run id session (:tokens bound) (:usd bound))
      (c/update-run! store run #(c/event % :provider-input {:request-id id :session session :input messages :input-hash (u/hash-value messages)}))
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

(defn initialize-context! [text backend worker]
  ;; Bind the same entire public context Prime receives as a file. Chunks stay
  ;; below the existing worker wire bound and never enter model conversations.
  (execution/evaluate! backend worker "(do (def external-context \"\") nil)" {})
  (doseq [chunk (partition-all 4096 text)]
    (execution/evaluate! backend worker "(do (def external-context (str external-context chunk)) nil)"
                         {:chunk (apply str chunk)})))

(defn -main [out]
  (try
    (let [{:keys [task context config gateway-config model-config]} (receive!)
          _ (isolation/require-tested!)
          _ (u/ensure! (and (string? context) (<= (count (.getBytes context "UTF-8")) 1500000)) "External context limit" {})
          _ (u/ensure! (not (.exists (io/file out))) "Use a fresh task output" {})
          config (assoc config :response-envelope wire/block-envelope-version)
          store (str out "/controller.sqlite") run "external-task"
          _ (c/create-run! store run config nil) _ (c/session! store run "root" nil)
          _ (c/put-context-block! store run "context" (mapv (fn [i line] {:line i :text line}) (range) (str/split-lines context)))
          base (str (slurp "resources/base-instructions.txt")
                    "\nThis is an external-context benchmark. The immutable complete public text is already bound to external-context in each SCI worker. "
                    "Inspect or compute over it through repl/eval without loading it into the model window. The context handle also permits line queries. "
                    "Finish with done and put your exact benchmark answer in the summary string. The answer is scored externally.\n"
                    (slurp "resources/external-command-v2.txt"))
          result (runtime/run-session! {:store store :run run :registry out :workers (atom {}) :allow-learning false
                                        :base-instructions base :provider (->ExternalProvider model-config gateway-config)
                                        :initialize-worker (partial initialize-context! context)}
                                       "root" {:task task :context-handle "context" :repl-binding "external-context"})
          ledger (c/get-run store run)]
      (records/write-events! (str out "/events.jsonl") (:events ledger))
      (when (and (not (:error result)) (string? (:summary result)))
        (u/atomic-write! (str out "/answer.txt") (:summary result)))
      (u/write-json! (str out "/result.json") {:status (if (:error result) "error" "completed") :result result
                                              :spent (:spent ledger) :reserved (:reserved ledger)})
      (emit! {:type "external_agent_complete" :native_exit_code (if (:error result) 2 0)}))
    (catch Exception _ (emit! {:type "external_agent_complete" :native_exit_code 2 :error "External task failed; inspect preserved artifacts"}))
    (finally (shutdown-agents))))
