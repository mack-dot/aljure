(ns repl-lab.artifact-fixture
  "Real-worker engineering controls. All solutions are developer-authored FIXTURE."
  (:refer-clojure :exclude [run!])
  (:require [clojure.java.io :as io] [repl-lab.util :as u] [repl-lab.artifact :as a]
            [repl-lab.bundle :as bundle] [repl-lab.evaluation :as evaluation]
            [repl-lab.execution :as execution] [repl-lab.executable :as executable]
            [repl-lab.python-source :as python] [repl-lab.controller :as c]
            [repl-lab.runtime :as runtime] [repl-lab.provider :as provider]
            [repl-lab.records :as records] [repl-lab.experiment :as experiment])
  (:import [java.util.concurrent TimeUnit] [java.lang ProcessHandle]))

(def development [-3 0 4])
(def transfer [-11 -1 2 19])
(def rule {:objective :verified-cases :min-score-improvement 1})
(defn config [language]
  (-> (u/read-file "config/experiment.edn")
      (assoc :execution-language language :command-format :json :promotion rule)
      ;; This fixture includes many independent syntax-worker starts, no inference.
      (assoc-in [:limits :wall-ms] 600000)))
(defn source [language part]
  (get-in {:clojure {:initial "(fn [x] (+ x 1))" :helper "(fn [x] (* x 1))" :candidate "(fn [x] (+ (twice x) 1))"
                    :local "(do (def solve (fn [x] (+ (* x 2) 1))) (solve -3))"}
           :python {:initial "def solve(x):\n    return x + 1" :helper "def twice(x):\n    return x * 1"
                    :candidate "def solve(x):\n    return twice(x) + 1"
                    :local "def solve(x):\n    return x * 2 + 1\nsolve(-3)"}} [language part]))
(defn artifact [language name source parent dependencies]
  (a/make-artifact (cond-> {:category :analysis :source source :interface {:name name :arity 1}
                            :dependencies dependencies :author "root" :parent parent :provenance :developer-fixture}
                    (= :python language) (assoc :language language))))
(defn submit [artifact]
  (assoc (select-keys artifact [:category :source :interface :dependencies :parent]) :op :artifact/submit))
(defn fails? [f] (try (f) false (catch Exception _ true)))

(defn panel! [root artifact inputs]
  (let [backend (execution/backend (a/language artifact))
        worker (execution/open! backend (+ (System/currentTimeMillis) 120000))]
    (try
      (executable/load! backend worker artifact (a/dependency-closure root artifact))
      (mapv (fn [input]
              (let [output (executable/call! backend worker artifact [input]) expected (inc (* input 2))]
                {:case (str "integer-" input) :input input :output output :expected expected :passed (= expected output)})) inputs)
      (finally (execution/close! backend worker)))))

(defn acquire! [root language]
  (let [folder (str root "/" (name language)) store (str folder "/controller.sqlite") id "evolving"
        initial (artifact language "solve" (source language :initial) nil [])
        helper (artifact language "twice" (source language :helper) nil [])
        path (case language :clojure [2 2] :python [:fields :body 0 :fields :body 0 :fields :value :fields :right :fields :value])
        patch {:op :artifact/patch :hash (:hash helper) :base-hash (:hash helper) :path path
               :expected-hash (u/hash-value 1) :replacement 2 :dependencies []}
        changed (a/patch helper (assoc patch :author "root" :provenance :developer-fixture))
        candidate (artifact language "solve" (source language :candidate) (:hash initial) [(:hash changed)])
        _ (a/save! folder initial)
        _ (c/create-run! store id (config language) (:hash initial))
        _ (c/session! store id "root" nil)
        env {:store store :run id :registry folder :workers (atom {}) :allow-learning true :provenance :synthetic-fixture
             :provider (provider/->FixtureProvider
                         (atom {"root" [(submit helper) {:op :artifact/subtree :hash (:hash helper) :path path}
                                        patch (submit candidate) {:op :artifact/call :hash (:hash candidate) :arguments [3]}
                                        {:op :done :summary "FIXTURE: controller must evaluate this candidate"}]}))}
        result (runtime/run-session! env "root" {:task "FIXTURE composition test"})
        _ (u/ensure! (not (:error result)) "Fixture acquisition failed" result)
        ledger (c/get-run store id)
        _ (u/ensure! (= 3 (count (filter #(= :artifact-staged (:type %)) (:events ledger)))) "Expected three staged fixture artifacts" {})
        denied? (boolean (some #(and (= :tool-result (:type %)) (= :artifact/call (get-in % [:payload :op]))
                                     (= :error (get-in % [:payload :status]))) (:events ledger)))
        stale? (fails? #(a/patch helper (assoc patch :base-hash (:hash changed) :author "root")))
        old (panel! folder initial development) new (panel! folder candidate development)
        evidence (a/promotion-evidence old new rule)
        _ (a/promote! store id folder candidate evidence)
        _ (c/session! store id "reuse" nil)
        value (runtime/broker! env "reuse" {:op :artifact/call :hash (:hash candidate) :arguments [7]})
        _ (c/finish-session! store id "reuse" :complete {:summary "FIXTURE invocation"})
        export (bundle/export! folder (str folder "/export") (:hash candidate) :synthetic-fixture)
        frozen-store (str folder "/frozen.sqlite")
        _ (c/create-run! frozen-store "frozen" (config language) (:hash initial))
        _ (c/session! frozen-store "frozen" "root" nil)
        frozen-env {:store frozen-store :run "frozen" :registry folder :workers (atom {}) :allow-learning false :provenance :synthetic-fixture
                    :provider (provider/->FixtureProvider (atom {"root" [{:op :repl/eval :source (source language :local) :bindings {}}
                                                                        (submit candidate) {:op :done :summary "FIXTURE frozen task"}]}))}
        frozen-result (runtime/run-session! frozen-env "root" {})
        frozen-ledger (c/get-run frozen-store "frozen")
        local? (boolean (some #(and (= :tool-result (:type %)) (= :repl/eval (get-in % [:payload :op]))
                                    (= -5 (get-in % [:payload :result :value]))) (:events frozen-ledger)))
        frozen? (and (not (:error frozen-result)) (= (:hash initial) (:active frozen-ledger))
                     (not-any? #(= :artifact-staged (:type %)) (:events frozen-ledger)))
        checks {:unapproved-call-denied denied? :stale-patch-denied stale? :promoted (:approved evidence)
                :approved-invocation (= 15 (:value value)) :frozen-task-local-code local? :frozen-retention-denied frozen?}]
    (records/write-events! (str folder "/events.jsonl") (:events (c/get-run store id)))
    (records/write-events! (str folder "/frozen-events.jsonl") (:events frozen-ledger))
    (let [report {:language language :checks checks :development evidence :export export
                  :initial (:hash initial) :candidate (:hash candidate) :evidence "FIXTURE"}]
      (u/write-edn! (str folder "/acquisition.edn") report)
      (u/ensure! (every? true? (vals checks)) "Artifact fixture failed" report)
      report)))

(defn cold! [export output]
  (let [library (evaluation/restore-library (bundle/load-bundle export)) candidate (:active library)
        language (a/language candidate) _ (execution/require-tested! language)
        _ (u/ensure! (not (.exists (io/file output))) "Cold output already exists" {})
        _ (doseq [item (vals (:by-hash library))] (a/save! output item))
        fallback (artifact language "solve" (source language :initial) nil [])
        _ (a/save! output fallback)
        learned (panel! output candidate transfer) ablated (panel! output fallback transfer)
        ;; Fresh controller/conversation: no old ledger or conversation is opened.
        store (str output "/controller.sqlite") _ (c/create-run! store "fresh" (config language) (:hash candidate))
        _ (c/session! store "fresh" "root" nil)
        result (runtime/run-session!
                 {:store store :run "fresh" :registry output :workers (atom {}) :allow-learning false :provenance :synthetic-fixture
                  :provider (provider/->FixtureProvider
                              (atom {"root" [{:op :artifact/call :hash (:hash candidate) :arguments [19]}
                                             {:op :done :summary "FIXTURE fresh conversation"}]}))} "root" {})
        ledger (c/get-run store "fresh")
        invoked? (boolean (some #(and (= :artifact-invoked (:type %)) (= 39 (get-in % [:payload :value]))) (:events ledger)))
        passed (and (every? :passed learned) (not-any? :passed ablated) invoked? (not (:error result)))
        report {:evidence "FIXTURE" :learning-claim false :language language :process-id (.pid (ProcessHandle/current))
                :restored-hash (:hash candidate) :learned learned :ablation ablated :invoked invoked? :passed passed}]
    (records/write-events! (str output "/events.jsonl") (:events ledger))
    (u/write-edn! (str output "/result.edn") report)
    (u/ensure! passed "Fresh-process fixture failed" report)
    report))

(defn syntax-check! []
  (let [input "raise RuntimeError('parse must not run this')\ndef solve(x):\n    return x"
        forms (python/parse! input)
        audited (bundle/audit (artifact :python "solve" "def solve(x):\n    \"\"\"Fixture docstring\"\"\"\n    return x" nil []))]
    {:parse-without-execution (= "Module" (:node forms))
     :invalid-arity-denied (fails? #(artifact :python "solve" "def solve(x, y):\n    return x" nil []))
     :variable-arity-denied (fails? #(artifact :python "solve" "def solve(*args):\n    return args" nil []))
     :missing-export-denied (fails? #(artifact :python "solve" "def other(x):\n    return x" nil []))
     :docstring-audited (= ["Fixture docstring"] (get-in audited [:docstrings :values]))}))

(defn run! [output]
  (let [root (if (seq output) output (str "var/benchmarks/artifacts-" (System/currentTimeMillis)))
        _ (u/ensure! (not (.exists (io/file root))) "Output already exists" {})
        gates (into {} (for [lang [:clojure :python]] [lang (execution/require-tested! lang)]))
        snapshot (experiment/manifest (config :clojure))
        _ (u/write-edn! (str root "/manifest.edn") snapshot)
        syntax (syntax-check!)
        _ (u/ensure! (every? true? (vals syntax)) "Python syntax fixture failed" syntax)
        arms (mapv #(acquire! root %) [:clojure :python])
        cold (mapv (fn [language]
                     (let [folder (str root "/" (name language))
                           builder (ProcessBuilder. ^java.util.List ["python3" "scripts/clj.py" "-m" "repl-lab.artifact-fixture"
                                                                    "cold" (str folder "/export") (str folder "/cold")])
                           _ (.redirectErrorStream builder true)
                           _ (.redirectOutput builder (io/file folder "cold-process.log"))
                           process (.start builder)]
                       (when-not (.waitFor process 180 TimeUnit/SECONDS)
                         (doseq [child (.toList (.descendants (.toHandle process)))] (.destroyForcibly child))
                         (.destroyForcibly process)
                         (u/fail "Cold fixture process timeout" {:language language}))
                       (u/ensure! (zero? (.exitValue process)) "Cold fixture process failed; inspect cold-process.log" {:language language})
                       (let [result (u/read-file (str folder "/cold/result.edn"))]
                         (u/ensure! (not= (.pid (ProcessHandle/current)) (:process-id result)) "Cold boot did not reset JVM" {})
                         result))) [:clojure :python])
        report {:evidence "FIXTURE" :passed true :model-calls 0 :model-created-skill false :learning-claim false
                :syntax syntax :gates gates :acquisition arms :cold cold
                :limitations ["Developer-written correct and incorrect solutions" "No held-out model experiment"
                              "No learned-efficiency or language-superiority claim" "Local compute price unknown"]}]
    (experiment/assert-frozen-source! snapshot)
    (u/write-json! (str root "/report.json") report)
    {:path root :passed true :evidence "FIXTURE" :model-calls 0}))

(defn -main [& [action input output]]
  (try
    (println (u/json-str (case action "run" (run! input) "cold" (select-keys (cold! input output) [:passed :evidence :language])
                              (u/fail "Expected run or cold" {}))))
    (shutdown-agents)
    (catch Exception e
      (println (u/json-str {:error (.getMessage e) :data (ex-data e) :evidence "FIXTURE" :model-calls 0}))
      (shutdown-agents) (System/exit 2))))
