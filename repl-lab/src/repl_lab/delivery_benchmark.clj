(ns repl-lab.delivery-benchmark
  "Offline answer-delivery benchmark (RECURSIVE_COMPACTION_ABLATION.md, O1): the
  real isolated worker, no model. A returns the value in one worker reply (as
  repl_eval does); B is paged delivery (done with source). Writes
  var/delivery-benchmark-<bound>.json."
  (:require [repl-lab.util :as u] [repl-lab.isolation :as isolation] [repl-lab.execution :as execution]
            [repl-lab.model-protocol :as wire] [repl-lab.external-task :as external]
            [repl-lab.controller :as c] [repl-lab.runtime :as runtime]))

(def sizes [10000 60000 100000 500000 2000000 8000000])

(defn- env [kind]
  (let [root (str (System/getProperty "java.io.tmpdir") "/delivery-" (name kind) "-" (System/nanoTime))
        store (str root "/controller.sqlite") workers (atom {})]
    (c/create-run! store "delivery" (merge (u/read-file "config/experiment.edn")
                                           {:response-envelope wire/tool-envelope-version
                                            :sci-surface :assisted :sci-results :raw}) nil)
    (c/session! store "delivery" "root" nil)
    {:store store :run "delivery" :workers workers :registry root :allow-learning false
     :initialize-worker (partial external/initialize-context! "line one\nline two" true)}))

(defn- measure [strategy chars text]
  (let [e (env strategy)
        source (str "(apply str (repeat " (quot chars (count text)) " " (pr-str text) "))")
        expected (apply str (repeat (quot chars (count text)) text))
        started (System/nanoTime)
        result (try (runtime/broker! e "root" (if (= :raw strategy)
                                               {:op :repl/eval :source source :bindings {}}
                                               {:op :done/eval :source source}))
                    (catch Exception error {:error (.getMessage error)}))
        ms (/ (- (System/nanoTime) started) 1e6)
        delivered (or (:summary result) (:value result))]
    (try
      {:strategy strategy :chars (count expected) :bytes (count (.getBytes ^String expected "UTF-8"))
       :delivered (string? delivered)
       :exact (and (string? delivered) (= (u/sha delivered) (u/sha expected)))
       :ms (Math/round ms) :workers (count @(:workers e))
       :pages (some #(get-in % [:payload :pages]) (filter #(= :answer-delivered (:type %)) (:events (c/get-run (:store e) "delivery"))))
       :error (some-> (:error result) (subs 0 (min 120 (count (:error result)))))}
      (finally (doseq [[_ w] @(:workers e)] (execution/close! (execution/backend :clojure) w))))))

(defn -main [& _]
  (isolation/require-tested!)
  (let [rows (vec (concat (for [chars sizes strategy [:raw :paged]] (measure strategy chars "x"))
                          ;; "a" plus an emoji: 3 UTF-16 chars, so page ends fall inside surrogate pairs.
                          (for [strategy [:raw :paged] chars [100000 500000]] (measure strategy chars "a😀"))))
        out (str "var/delivery-benchmark-" (isolation/output-bound) ".json")]
    (u/write-json! out {:evidence "OFFLINE; real isolated worker; no model" :output-bytes (isolation/output-bound) :rows rows})
    (doseq [r rows] (println (u/json-str r)))
    (shutdown-agents)
    (System/exit 0)))
