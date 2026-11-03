(ns repl-lab.python-contract
  "Checks every advertised Python-surface behaviour (resources/python-contract.json)
  through the controller's own request, display and error paths against the real
  isolated Python worker, then paged answer delivery and overflow recovery through
  the real broker. Writes var/python-contract-proof.json, which the paired preflight
  requires for execution_language python. Developer probes only; no model call."
  (:require [repl-lab.util :as u] [repl-lab.isolation :as isolation] [repl-lab.execution :as execution]
            [repl-lab.model-protocol :as wire] [repl-lab.external-task :as external]
            [repl-lab.sci-contract :as sci-contract] [repl-lab.controller :as c] [repl-lab.runtime :as runtime]))

(def proof-path "var/python-contract-proof.json")

(def config {:response-envelope wire/tool-envelope-version :sci-surface :assisted :sci-results :bounded
             :execution-language :python})

(defn digests []
  {:contract-sha256 (u/sha (slurp "resources/python-contract.json"))
   :prelude-sha256 (u/sha (slurp "resources/python-prelude.py"))
   :worker-sha256 (u/sha (slurp "worker/src/repl_lab/python_worker.py"))
   :model-protocol-sha256 (u/sha (slurp "src/repl_lab/model_protocol.clj"))
   :runtime-sha256 (u/sha (slurp "src/repl_lab/runtime.clj"))
   :external-task-sha256 (u/sha (slurp "src/repl_lab/external_task.clj"))})

(defn check-probes
  "Each probe through assisted-source (a display request), the worker, and result-messages."
  [contract]
  (let [backend (execution/backend :python)
        worker (execution/open! backend (+ (System/currentTimeMillis) 110000))]
    (try
      (external/initialize-context! (:context contract) true backend worker)
      (vec (for [probe (:probes contract)]
             (let [shown (sci-contract/run-probe config backend worker probe)]
               {:mode "bounded" :source (:source probe) :passed (sci-contract/passes? probe shown)
                :shown (subs (:text shown) 0 (min 300 (count (:text shown))))})))
      (finally (execution/close! backend worker)))))

(defn- env [name]
  (let [root (str (System/getProperty "java.io.tmpdir") "/python-contract-" name "-" (System/nanoTime))
        store (str root "/controller.sqlite") run name]
    (c/create-run! store run (merge (u/read-file "config/experiment.edn") config) nil)
    (c/session! store run "root" nil)
    {:store store :run run :workers (atom {}) :registry root :allow-learning false
     :initialize-worker (partial external/initialize-context! "line one\nline two\nline three" true)}))

(defn- close-all! [e] (doseq [[_ w] @(:workers e)] (execution/close! (execution/backend :python) w)))

(defn check-answer-delivery
  "done with source: an answer larger than one worker reply arrives whole, in pages below
  the bound, through the real broker; the worker is not replaced. ASCII, then a letter plus
  an emoji (one code point in Python, a surrogate pair on the controller side)."
  []
  (let [size (* 3 (isolation/output-bound))]
    (vec (for [[text label] [["y" "ascii"] ["a😀" "astral"]]]
           (let [e (env (str "answer-" label))
                 units (count text)
                 expected (apply str (repeat (quot size units) text))
                 result (try (runtime/broker! e "root" {:op :done/eval :source (str "x = " (pr-str text) " * " (quot size units) "\nx")})
                             (catch Exception ex {:error (.getMessage ex)}))
                 summary (:summary result)]
             (try
               {:mode (str "answer-delivery-" label) :source (str (count expected) " characters")
                :passed (and (string? summary) (= (u/sha expected) (u/sha summary)) (= 1 (count @(:workers e))))
                :shown (u/json-str {:chars (count summary) :error (:error result) :workers (count @(:workers e))})}
               (finally (close-all! e))))))))

(defn check-recovery
  "Overflow is recoverable and the worker is kept: a printed flood is refused with a hint,
  an oversized value is previewed, and definitions survive both. A non-string answer is
  refused without ending the session."
  []
  (let [e (env "recovery")
        call (fn [command] (try (runtime/broker! e "root" command) (catch Exception ex {:error (.getMessage ex)})))
        eval (fn [source] (call {:op :repl/eval :source source :bindings {}}))]
    (try
      (let [kept (eval "kept = 7")
            flood (eval "print('z' * 2000000)")
            big (eval "'x' * 3000000")
            full (eval "len(full_result)")
            lines (eval "len(context_lines)")
            still (eval "kept")
            answer (call {:op :done/eval :source "kept"})
            after (eval "kept + 1")
            events (filter #(#{:tool-call :tool-result} (:type %)) (:events (c/get-run (:store e) (:run e))))]
        [{:mode "overflow-recovery" :source "print flood, oversized value, non-string answer"
          :passed (and (= {:value "(no output)"} kept)
                       (re-find #"Printed output limit" (str (:error flood)))
                       (not (re-find #"worker stopped" (str (:error flood))))
                       (:aljure/truncated (:value big)) (= 3000002 (:total-chars (:value big)))
                       (= {:value "3000002"} full) (= {:value "3"} lines) (= {:value "7"} still)
                       (re-find #"must evaluate to a string" (str (:error answer)))
                       (= {:value "8"} after)
                       (= 1 (count @(:workers e))) (= 16 (count events)))
          :shown (u/json-str {:flood (:error flood) :big (dissoc (:value big) :preview) :answer (:error answer)
                              :workers (count @(:workers e)) :recorded-events (count events)})}])
      (finally (close-all! e)))))

(defn -main [& _]
  (try
    (let [check (execution/require-tested! :python)
          contract (wire/python-contract)
          results (-> (check-probes contract) (into (check-answer-delivery)) (into (check-recovery)))
          passed (every? :passed results)
          proof (merge (digests) {:status (if passed "TESTED" "FAILED") :image (:image check)
                                  :output-bytes (isolation/output-bound) :model-calls 0 :results results})]
      (when passed (u/write-json! proof-path proof))
      (println (u/json-str (dissoc proof :results)))
      (doseq [r results :when (not (:passed r))] (println "FAILED" (u/json-str r)))
      (shutdown-agents)
      (System/exit (if passed 0 1)))
    (catch Exception e
      (println "Python contract check failed:" (.getMessage e))
      (shutdown-agents)
      (System/exit 2))))
