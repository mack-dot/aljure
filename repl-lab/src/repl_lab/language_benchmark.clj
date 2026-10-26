(ns repl-lab.language-benchmark
  "Offline adapter pilot. Scripted agents are FIXTURE, never learning evidence."
  (:refer-clojure :exclude [run!])
  (:require [clojure.java.io :as io] [repl-lab.util :as u] [repl-lab.execution :as x]
            [repl-lab.controller :as c] [repl-lab.runtime :as runtime]
            [repl-lab.provider :as provider] [repl-lab.experiment :as experiment]
            [repl-lab.records :as records] [repl-lab.model-protocol :as wire]))

(def languages [:clojure :python])
(def fixture-sources
  {:aggregate
   {:clojure "(do (def solve (fn [rows] (let [ready (filter :ready rows)] {:ids (vec (sort (map :id ready))) :total (reduce + 0 (map :weight ready))}))) nil)"
    :python "def solve(rows):\n    ready = [r for r in rows if r['ready']]\n    return {'ids': sorted(r['id'] for r in ready), 'total': sum(r['weight'] for r in ready)}"}
   :transform
   {:clojure "(do (def solve (fn [nodes] (reduce (fn [out node] (let [op (:op node) v (:value node) last-node (peek out)] (cond (or (and (= op \"add\") (= v 0)) (and (= op \"mul\") (= v 1))) out (and (= op \"add\") (= (:op last-node) \"add\")) (let [n (+ v (:value last-node))] (if (= n 0) (pop out) (conj (pop out) {:op \"add\" :value n}))) :else (conj out node)))) [] nodes))) nil)"
    :python "def solve(nodes):\n    out = []\n    for node in nodes:\n        op, value = node['op'], node['value']\n        if (op == 'add' and value == 0) or (op == 'mul' and value == 1):\n            continue\n        if op == 'add' and out and out[-1]['op'] == 'add':\n            value += out.pop()['value']\n            if value != 0:\n                out.append({'op': 'add', 'value': value})\n        else:\n            out.append(dict(node))\n    return out"}})

(defn call-source [language] (case language :clojure "(solve records)" :python "solve(records)"))
(defn identity-source [language]
  (case language :clojure "(do (def solve (fn [records] records)) nil)" :python "def solve(records):\n    return records"))

(defn examples [family seed]
  (let [rng (java.util.Random. seed)]
    (case family
      :aggregate
      (vec (concat [[] [{:id "only" :ready false :weight 7}]]
                   (for [i (range 8)]
                     (mapv (fn [j] {:id (str "node-" j) :ready (.nextBoolean rng) :weight (- (.nextInt rng 40) 10)})
                           (range (+ 1 i))))))
      :transform
      (vec (concat [[] [{:op "add" :value 0}] [{:op "mul" :value 1}]
                    [{:op "add" :value 4} {:op "add" :value -4}]]
                   (for [_ (range 6)]
                     (vec (concat [{:op "add" :value 0} {:op "add" :value 2} {:op "add" :value 3}]
                                  (for [_ (range 6)] {:op (if (.nextBoolean rng) "add" "mul") :value (.nextInt rng 5)})
                                  [{:op "mul" :value 1}]))))))))

(defn interpret [nodes value]
  (reduce (fn [v node] (case (:op node) "add" (+ v (:value node)) "mul" (* v (:value node)))) value nodes))

(defn correct? [family input output]
  (case family
    :aggregate (= output {:ids (vec (sort (for [r input :when (:ready r)] (:id r))))
                          :total (reduce + 0 (for [r input :when (:ready r)] (:weight r)))})
    :transform (and (vector? output) (<= (count output) (count input))
                    (every? #(and (map? %) (= #{:op :value} (set (keys %)))
                                   (#{"add" "mul"} (:op %)) (integer? (:value %))) output)
                    (not-any? #(or (and (= "add" (:op %)) (zero? (:value %)))
                                    (and (= "mul" (:op %)) (= 1 (:value %)))) output)
                    (not-any? #(every? (fn [n] (= "add" (:op n))) %) (partition 2 1 output))
                    (every? #(= (interpret input %) (interpret output %)) [-101 -9 -1 0 1 3 17 201]))))

(defn score! [language family source seed]
  (let [backend (x/backend language) worker (x/open! backend (+ (System/currentTimeMillis) 120000))
        started (System/nanoTime)]
    (try
      (x/evaluate! backend worker source {})
      (let [cases (mapv (fn [input]
                          (try (let [output (x/evaluate! backend worker (call-source language) {:records input})]
                                 {:input input :output output :passed (boolean (correct? family input output))})
                               (catch Exception e {:input input :passed false :error (.getMessage e) :diagnostics (ex-data e)})))
                        (examples family seed))]
        {:score (if (every? :passed cases) 1 0) :cases cases
         :wall-ms (/ (- (System/nanoTime) started) 1000000.0)})
      (catch Exception e {:score 0 :error (.getMessage e) :diagnostics (ex-data e) :cases []})
      (finally (x/close! backend worker)))))

(defn parity! [language]
  (let [backend (x/backend language) proof (x/require-tested! language)
        worker (x/open! backend (+ (System/currentTimeMillis) 120000))]
    (try
      (let [definition (case language :clojure "(do (def offset 40) nil)" :python "offset = 40")
            persistent (case language :clojure "(+ offset 2)" :python "offset + 2")
            transform (case language
                        :clojure "(let [form (quote (+ offset 1))] (str (list (first form) (second form) 2)))"
                        :python "import ast\ntree = ast.parse('offset + 1', mode='eval')\ntree.body.right = ast.Constant(value=2)\nast.unparse(ast.fix_missing_locations(tree))")
            _ (x/evaluate! backend worker definition {})
            before (x/evaluate! backend worker persistent {})
            changed (x/evaluate! backend worker transform {})
            after (x/evaluate! backend worker changed {})
            failed (try (x/evaluate! backend worker "missing_binding" {}) false (catch Exception _ true))
            repaired (x/evaluate! backend worker persistent {})]
        {:language language :isolation proof :persistent (= 42 before) :structural-transform (= 42 after)
         :error-feedback failed :repair (= 42 repaired)
         :transformed-source changed})
      (finally (x/close! backend worker)))))

(defn reset-check! [language]
  (let [backend (x/backend language) worker (x/open! backend (+ (System/currentTimeMillis) 30000))]
    (try (try (x/evaluate! backend worker "offset" {}) false (catch Exception _ true))
         (finally (x/close! backend worker)))))

(defn task! [root language family index]
  (let [id (str (name language) "-" (name family) "-" index) folder (str root "/tasks/" id)
        store (str folder "/controller.sqlite")
        config (assoc (u/read-file "config/experiment.edn") :execution-language language :command-format :json :mode :fixture)
        input (last (examples family (+ 100 index))) source (get-in fixture-sources [family language])
        _ (c/create-run! store id config "empty-library")
        _ (c/put-context! store id "input" input) _ (c/session! store id "root" nil)
        scripted [{:op :context/query :handle "input" :query {:limit 64}}
                  {:op :repl/eval :source source :bindings {}}
                  {:op :repl/eval :source (call-source language) :bindings {:records input}}
                  {:op :agent/call :id "child" :task "Count the supplied records through the execution backend" :context input}
                  {:op :done :summary {:source source}}]
        child [{:op :repl/eval :source (case language :clojure "(count records)" :python "len(records)") :bindings {:records input}}
               {:op :done :summary {:count (count input)}}]
        started (System/nanoTime)
        result (runtime/run-session!
                {:store store :run id :registry folder :workers (atom {}) :allow-learning false
                 :provenance :synthetic-fixture
                 :provider (provider/->FixtureProvider (atom {"root" scripted "child" child}))}
                "root" {:family family :context-handles ["input"] :execution-language language})
        ledger (c/get-run store id)
        controller-checks
        {:sessions-complete (every? #(= :complete (get-in ledger [:sessions % :status])) ["root" "child"])
         :child-execution (boolean (some #(and (= :tool-result (:type %))
                                               (= "child" (get-in % [:payload :session]))
                                               (= :repl/eval (get-in % [:payload :op]))
                                               (= (count input) (get-in % [:payload :result :value]))) (:events ledger)))
         :child-consumed (boolean (some #(= :child-result-consumed (:type %)) (:events ledger)))}
        scored (if (:error result) {:score 0 :error (:error result) :cases []}
                   (score! language family (get-in result [:summary :source]) (+ 9000 index)))
        trace (str folder "/events.jsonl")
        _ (records/write-events! trace (:events ledger))
        outcome (merge scored {:id id :case-id (str (name family) "-" index) :language language :family family
                               :evidence "FIXTURE" :model-calls 0 :scripted-calls (get-in ledger [:spent :calls])
                               :model-usd 0 :local-compute-usd nil :execution-language language
                               :command-format :json :prompt-sha256 (u/sha (wire/instructions config))
                               :task-sha256 (u/hash-value {:family family :input input})
                               :trace-path (str "tasks/" id "/events.jsonl") :trace-sha256 (u/sha (slurp trace))
                               :source-path (str "tasks/" id "/solution.txt")
                               :source-sha256 (u/sha source) :usage {:spent (:spent ledger) :reserved (:reserved ledger)}
                               :controller-checks controller-checks
                               :total-wall-ms (/ (- (System/nanoTime) started) 1000000.0)})]
    (records/write-events! (str folder "/events.jsonl") (:events ledger))
    (u/atomic-write! (str folder "/solution.txt") source)
    (u/write-json! (str folder "/evaluation.json") outcome)
    outcome))

(defn run! [action output]
  (u/ensure! (#{"parity" "fixtures" "pilot"} action) "Unknown language benchmark command" {})
  (doseq [language languages] (x/require-tested! language))
  (let [root (if (seq output) output (str "var/benchmarks/" action "-" (System/currentTimeMillis)))
        _ (u/ensure! (not (.exists (io/file root))) "Output already exists; preserve prior evidence" {:path root})
        snapshot (experiment/manifest (u/read-file "config/experiment.edn"))
        _ (u/write-edn! (str root "/manifest.edn") snapshot)
        parity (mapv #(assoc (parity! %) :session-reset (reset-check! %)) languages)
        checks (when (#{"fixtures" "pilot"} action)
                 (vec (for [language languages family [:aggregate :transform]]
                        {:language language :family family
                         :correct (score! language family (get-in fixture-sources [family language]) 7788)
                         :incorrect (score! language family (identity-source language) 7788)
                         :malformed (score! language family (case language :clojure "(" :python "def") 7788)})))
        rows (when (= "pilot" action)
               (vec (for [index (range 2) family [:aggregate :transform]
                          language (if (even? index) languages (reverse languages))]
                      (task! root language family index))))
        passed (and (every? #(every? true? ((juxt :persistent :structural-transform :error-feedback :repair :session-reset) %)) parity)
                    (every? #(and (= 1 (get-in % [:correct :score])) (= 0 (get-in % [:incorrect :score]))
                                  (= 0 (get-in % [:malformed :score]))) checks)
                    (every? #(and (= 1 (:score %)) (every? true? (vals (:controller-checks %)))) rows))
        report {:evidence "FIXTURE" :action action :passed (boolean passed) :model-calls 0 :learning-claim false
                :source-commit (:source-commit snapshot) :source-dirty (:source-dirty snapshot)
                :source-hash (:source-hash snapshot) :runtime (:runtime snapshot)
                :capabilities (u/json-read (slurp "research/capabilities.json"))
                :capability-sha256 (u/sha (slurp "research/capabilities.json"))
                :parity parity :evaluator-controls checks :rows rows
                :limitations ["No live model comparison" "Four-condition language learning study is not implemented"
                              "Pilot families are small developer fixtures, not an official benchmark or held-out experiment"
                              "Local compute price is unknown; no economic superiority claim"]}]
    (experiment/assert-frozen-source! snapshot)
    (u/write-json! (str root "/report.json") report)
    (u/ensure! passed "Language benchmark checks failed; inspect report" {:path root})
    {:path root :passed passed :evidence "FIXTURE" :model-calls 0 :paired-cases (/ (count rows) 2)}))

(defn -main [& [action output]]
  (try (println (u/json-str (run! action output))) (shutdown-agents)
       (catch Exception e
         (println (u/json-str {:error (.getMessage e) :data (ex-data e) :model-calls 0}))
         (shutdown-agents) (System/exit 2))))
