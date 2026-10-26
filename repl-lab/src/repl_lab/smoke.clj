(ns repl-lab.smoke
  (:require [repl-lab.util :as u] [repl-lab.controller :as c] [repl-lab.runtime :as runtime]
            [repl-lab.provider :as provider] [repl-lab.isolation :as isolation]
            [repl-lab.live :as live] [repl-lab.experiment :as experiment] [repl-lab.records :as records]
            [repl-lab.subscription :as subscription]))

(def task
  {:task (str "Capability smoke test, not a learning experiment. Follow these steps in order. "
              "1. Query the external jobs handle with {:limit 16}. The records are not in this prompt. "
              "2. Pass those returned records in :repl/eval bindings under :records. Write Clojure to filter "
              "ready records and return {:ids <sorted vector of ready IDs> :estimate-sum <sum of their estimates>}. "
              "3. Call a real child named smoke-child. Pass exactly that SCI result as :context. "
              "Ask the child to bind it as :selection, use SCI to compute {:count <number of IDs> "
              ":double-estimate <twice estimate-sum>}, and finish with that map as its :summary. "
              "4. Consume the child's result and finish with that same map as your :summary. "
              "Both sessions must execute SCI. Use ordinary broker operations, not claims of execution.")
   :context-handles ["jobs"]})

(defn expected [rows]
  (let [ready (filter :ready rows)]
    {:ids (vec (sort (map :id ready))) :estimate-sum (reduce + (map :estimate ready))}))

(defn evidence [ledger rows]
  (let [selection (expected rows) answer {:count (count (:ids selection)) :double-estimate (* 2 (:estimate-sum selection))}
        events (:events ledger)
        outputs (into {} (for [e events :when (and (= :tool-result (:type e)) (= :ok (get-in e [:payload :status])))]
                           [(get-in e [:payload :call-sequence]) e]))
        calls (filter #(= :tool-call (:type %)) events)
        find-call (fn [session op predicate]
                    (first (filter #(and (= session (get-in % [:payload :session]))
                                         (= op (get-in % [:payload :command :op]))
                                         (predicate (get-in % [:payload :command])
                                                    (get-in outputs [(:sequence %) :payload :result]))) calls)))
        query (find-call "root" :context/query #(and (= "jobs" (:handle %1)) (= rows (:records %2))))
        root-sci (find-call "root" :repl/eval #(and (some (partial = rows) (vals (:bindings %1))) (= selection (:value %2))))
        child-call (find-call "root" :agent/call #(and (= "smoke-child" (:id %1)) (= selection (:context %1)) (= answer (:summary %2))))
        child-sci (find-call "smoke-child" :repl/eval #(and (some (partial = selection) (vals (:bindings %1))) (= answer (:value %2))))
        consumed (first (filter #(and (= :child-result-consumed (:type %))
                                      (= "root" (get-in % [:payload :parent]))
                                      (= "smoke-child" (get-in % [:payload :child]))
                                      (= answer (get-in % [:payload :result :summary]))) events))
        finished (find-call "root" :done #(and (= answer (:summary %1)) (= answer (:summary %2))))
        ordered [query root-sci child-call child-sci consumed finished]
        real-call? (fn [session]
                     (boolean (some #(and (= session (:session %)) (= :complete (:status %))
                                          (= :recorded-model-run (get-in % [:response :provenance])))
                                    (vals (:provider-requests ledger)))))
        checks {:external-context-query (boolean query) :root-sci-result (boolean root-sci)
                :selected-context-to-child (boolean child-call) :child-sci-result (boolean child-sci)
                :parent-consumed-child (boolean consumed) :parent-final-answer (boolean finished)
                :ordered-evidence (boolean (and (every? some? ordered) (apply < (map :sequence ordered))))
                :root-model-call (real-call? "root") :child-model-call (real-call? "smoke-child")
                :sessions-complete (every? #(= :complete (get-in ledger [:sessions % :status])) ["root" "smoke-child"])
                :no-uncertain-calls (zero? (get-in ledger [:reserved :calls]))}]
    {:passed (every? true? (vals checks)) :checks checks
     :expected-selection selection :expected-answer answer
     :event-sequences (mapv :sequence ordered)}))

(defn completed-evidence [ledger rows result]
  (let [verified (evidence ledger rows)
        checks (assoc (:checks verified) :runtime-completed
                      (and (not (:error result)) (= (:expected-answer verified) (:summary result))))]
    (assoc verified :checks checks :passed (every? true? (vals checks)))))

(defn execute! [{:keys [root id config provider snapshot provenance]} rows]
  (let [store (str root "/controller.sqlite") start (System/nanoTime)]
    (c/create-run! store id config "smoke-no-retained-artifacts")
    (c/put-context! store id "jobs" rows)
    (c/session! store id "root" nil)
    (u/write-edn! (str root "/manifest.edn") snapshot)
    (u/write-edn! (str root "/context.edn") {:jobs rows})
    (let [result (try (runtime/run-session! {:store store :run id :registry root :provider provider
                                            :workers (atom {}) :allow-learning false :provenance provenance}
                                           "root" task)
                      (catch Exception e {:error (.getMessage e)}))
          ledger (c/get-run store id) verified (completed-evidence ledger rows result)
          subscription? (= :claude-code-subscription (get-in snapshot [:model :provider]))
          known? (zero? (get-in ledger [:reserved :calls]))
          report (merge verified {:run-id id :mode :capability-smoke :provenance provenance
                                  :result result :manifest snapshot
                                  :wall-ms (/ (- (System/nanoTime) start) 1000000.0)
                                  :usage {:spent (:spent ledger) :reserved-unknown (:reserved ledger)}
                                  :budget-basis (if subscription? :standard-rate-equivalent :api-estimated-cost)
                                  :standard-rate-equivalent-usd (when (and known? subscription?) (get-in ledger [:spent :usd]))
                                  :model-cost-usd (when (and known? (not subscription?)) (get-in ledger [:spent :usd]))
                                  :invoiced-usd nil :learning-claim false})]
      (c/update-run! store id #(assoc % :status (if (:passed verified) :complete :checkpointed)))
      (records/write-events! (str root "/events.jsonl") (:events ledger))
      (u/write-edn! (str root "/generated-code.edn")
                    (mapv :payload (filter #(and (= :tool-call (:type %)) (= :repl/eval (get-in % [:payload :command :op]))) (:events ledger))))
      (u/write-edn! (str root "/report.edn") report)
      (u/write-json! (str root "/report.json") report)
      report)))

(defn smoke! [env]
  (let [{:keys [model cap input-rate output-rate api-key]} (live/options env)
        selected (get env "SMOKE_PROVIDER" "anthropic")
        _ (u/ensure! (#{"anthropic" "claude-subscription"} selected) "Unsupported smoke provider" {})
        check (isolation/require-tested!)
        cli (when (= selected "claude-subscription") (subscription/preflight!))]
    (if cli
      (u/ensure! (and (= model "claude-sonnet-5-5") (<= cap 1.0) (= 2.0 input-rate) (= 10.0 output-rate))
                 "Subscription smoke requires the authorized model, rates, and at most $1 equivalent budget" {})
      (u/ensure! (seq api-key) "ANTHROPIC_API_KEY is required" {}))
    (let [id (str "smoke-" (System/currentTimeMillis)) root (str "var/runs/" id)
          random (java.security.SecureRandom.)
          rows (mapv (fn [i] {:id (str "smoke-job-" i) :ready (even? i) :estimate (+ 1 (.nextInt random 50))}) (range 4))
          config (-> (u/read-file "config/experiment.edn")
                     (assoc :mode :live :provenance :recorded-model-run)
                     (assoc-in [:limits :usd] cap) (assoc-in [:limits :calls] 8)
                     (assoc-in [:limits :recursion-depth] 1) (assoc-in [:limits :concurrent-subagents] 1))
          snapshot (assoc (experiment/manifest config) :isolation check :mode :capability-smoke
                          :transport (when cli (select-keys cli [:cli_version :cli_sha256 :auth]))
                          :model {:requested model :provider (if cli :claude-code-subscription :anthropic) :input-usd-per-m input-rate
                                  :output-usd-per-m output-rate :max-output-tokens 2048})
          report (execute! {:root root :id id :config config :snapshot snapshot :provenance :recorded-model-run
                            :provider (if cli (subscription/->SubscriptionProvider model input-rate output-rate 2048 cli)
                                          (provider/->AnthropicProvider model api-key input-rate output-rate 2048))} rows)]
      (experiment/assert-frozen-source! snapshot)
      (u/ensure! (:passed report) "Live smoke did not pass; inspect preserved evidence before another attempt"
                 {:path root :checks (:checks report)})
      {:path root :passed true :checks (:checks report) :usage (:usage report) :learning-claim false})))
