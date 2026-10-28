(ns repl-lab.sci-contract
  "Checks every advertised SCI behaviour (resources/sci-contract.json) through
  the controller's own source, result and error paths against the real isolated
  worker. Writes a proof the paired preflight requires for the assisted surface."
  (:require [clojure.string :as str] [repl-lab.util :as u] [repl-lab.isolation :as isolation]
            [repl-lab.execution :as execution] [repl-lab.model-protocol :as wire]
            [repl-lab.external-task :as external] [repl-lab.controller :as c] [repl-lab.runtime :as runtime]))

(defn proof-path []
  (let [bound (isolation/output-bound)]
    (if (= 65536 bound) "var/sci-contract-proof.json" (str "var/sci-contract-proof-" bound ".json"))))

(defn digests []
  {:contract-sha256 (u/sha (slurp "resources/sci-contract.json"))
   :prelude-sha256 (u/sha (slurp "resources/sci-prelude.edn"))
   :model-protocol-sha256 (u/sha (slurp "src/repl_lab/model_protocol.clj"))})

(defn display
  "What the model would see for this result, through the runtime's own path."
  [config result]
  (let [response {:content [{:type "tool_use" :id "contract" :name "repl_eval" :input {}}]}
        block (first (:content (second (wire/result-messages config response result))))]
    {:text (:content block) :error (boolean (:is_error block))}))

(defn run-probe [config backend worker {:keys [source]}]
  (display config
           (try {:value (execution/evaluate! backend worker (wire/assisted-source config :repl/eval source) {})}
                (catch Exception e {:error (.getMessage e)}))))

(defn passes? [{:keys [text error] :as expected} shown]
  (and (= (boolean error) (:error shown))
       (or (nil? text) (= text (:text shown)))
       (or (nil? (:text-prefix expected)) (str/starts-with? (:text shown) (:text-prefix expected)))
       (or (nil? (:text-contains expected)) (str/includes? (:text shown) (:text-contains expected)))))

(defn check-mode [contract mode]
  (let [config {:response-envelope wire/tool-envelope-version :sci-surface :assisted :sci-results (keyword mode)}
        backend (execution/backend :clojure)
        worker (execution/open! backend (+ (System/currentTimeMillis) 110000))]
    (try
      (external/initialize-context! (:context contract) true backend worker)
      (vec (for [probe (:probes contract) :when (some #{mode} (or (:modes probe) ["raw" "bounded"]))]
             (let [shown (run-probe config backend worker probe)]
               {:mode mode :source (:source probe) :passed (passes? probe shown) :shown (subs (:text shown) 0 (min 300 (count (:text shown))))})))
      (finally (execution/close! backend worker)))))

(defn check-recovery
  "Raw results: an output over the bound stops the worker. Through the real broker
  and ledger, the next call must get a fresh worker, and the record must keep both calls."
  [contract]
  (let [root (str (System/getProperty "java.io.tmpdir") "/sci-contract-" (System/nanoTime))
        store (str root "/controller.sqlite") run "contract"
        config (merge (u/read-file "config/experiment.edn")
                      {:response-envelope wire/tool-envelope-version :sci-surface :assisted :sci-results :raw})
        workers (atom {})
        env {:store store :run run :workers workers :registry root :allow-learning false
             :initialize-worker (partial external/initialize-context! (:context contract) true)}
        big (str "(apply str (repeat " (+ 100 (isolation/output-bound)) " \"x\"))")
        call (fn [source] (try {:value (runtime/broker! env "root" {:op :repl/eval :source source :bindings {}})}
                               (catch Exception e {:error (.getMessage e)})))]
    (c/create-run! store run config nil) (c/session! store run "root" nil)
    (try
      (let [before (call "(def kept 7)")
            oversized (call big)
            after (call "(count context-lines)")
            lost (call "kept")
            events (filter #(#{:tool-call :tool-result} (:type %)) (:events (c/get-run store run)))]
        [{:mode "raw-recovery" :source big
          :passed (and (:value before) (re-find #"The worker stopped" (str (:error oversized)))
                       (= {:value 3} (:value after)) (re-find #"Could not resolve symbol: kept" (str (:error lost)))
                       (= 2 (count @workers)) (= 8 (count events)))
          :shown (u/json-str {:oversized (:error oversized) :after (:value after) :lost (:error lost)
                              :workers (count @workers) :recorded-events (count events)})}])
      (finally (doseq [[_ w] @workers] (execution/close! (execution/backend :clojure) w))))))

(defn -main [& _]
  (try
    (let [check (isolation/require-tested!)
          contract (wire/sci-contract)
          results (-> (check-mode contract "raw") (into (check-mode contract "bounded")) (into (check-recovery contract)))
          passed (every? :passed results)
          proof (merge (digests) {:status (if passed "TESTED" "FAILED") :image (:image check)
                                  :output-bytes (isolation/output-bound) :results results})]
      (when passed (u/write-json! (proof-path) proof))
      (println (u/json-str (dissoc proof :results)))
      (doseq [r results :when (not (:passed r))] (println "FAILED" (u/json-str r)))
      (shutdown-agents)
      (System/exit (if passed 0 1)))
    (catch Exception e
      (println "SCI contract check failed:" (.getMessage e))
      (shutdown-agents)
      (System/exit 2))))
