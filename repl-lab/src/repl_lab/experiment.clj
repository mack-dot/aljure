(ns repl-lab.experiment
  (:require [clojure.java.io :as io] [clojure.string :as str] [clojure.java.shell :as shell]
            [repl-lab.util :as u] [repl-lab.sim :as sim] [repl-lab.workloads :as w]
            [repl-lab.baselines :as baselines] [repl-lab.fixtures :as f] [repl-lab.controller :as c]
            [repl-lab.artifact :as a] [repl-lab.bundle :as bundle] [repl-lab.runtime :as runtime]
            [repl-lab.provider :as provider] [repl-lab.records :as records] [repl-lab.limits :as limits]))

(defn source-manifest []
  (into (sorted-map)
        (for [dir ["src" "worker" "scripts" "resources" "config" "benchmark" "research/capabilities.json" "deps.edn" "Makefile" ".dockerignore"
                   "dashboard/src" "dashboard/package.json" "dashboard/package-lock.json" "dashboard/build.mjs"] file (file-seq (io/file dir))
              :when (and (.isFile file) (not (str/includes? (str file) "__pycache__")))]
          [(str file) (u/sha (slurp file))])))
(defn manifest [config]
  (let [sources (source-manifest)
        python (shell/sh "python3" "-c" "import json,platform,sqlite3; print(json.dumps({'python':platform.python_version(),'sqlite':sqlite3.sqlite_version}))")
        _ (u/ensure! (zero? (:exit python)) "Cannot record Python/SQLite runtime" {})
        commit (shell/sh "git" "rev-parse" "HEAD") status (shell/sh "git" "status" "--porcelain" "--" ".")]
    {:created (u/now) :source-commit (when (zero? (:exit commit)) (str/trim (:out commit)))
     :source-dirty (when (zero? (:exit status)) (not (str/blank? (:out status))))
     :source-commit-note "Source hashes identify the executed snapshot, including uncommitted changes."
     :source-files sources :source-hash (u/hash-value sources) :config config
     :runtime (merge {:java (System/getProperty "java.version") :clojure (clojure-version)
                      :os (System/getProperty "os.name") :arch (System/getProperty "os.arch")}
                     (u/json-read (:out python)))
     :dependencies (u/read-file "deps.edn") :model {:requested nil :returned nil :provider :fixture}
     :claim-status {:H1 :untested :H2 :untested :H3 :out-of-scope}}))

(defn assert-frozen-source! [snapshot]
  (u/ensure! (= (:source-files snapshot) (source-manifest)) "Fixed experiment source changed during run; create a new experiment" {}))

(defn write-episode! [root arm index world policy artifact]
  (let [start (System/nanoTime) options (limits/fresh (u/read-file "config/experiment.edn"))
        run (sim/run-episode world policy options)]
    (records/save-episode! root (str arm "-" index) world run
                          {:arm arm :artifact artifact :execution-limits options :wall-ms (/ (- (System/nanoTime) start) 1000000.0)})))

(defn panel! [root arm worlds policy artifact]
  (mapv (fn [i world] (write-episode! root arm i world policy artifact)) (range) worlds))
(defn paired-metrics [panel] (mapv #(assoc (:metrics %) :case (:case %)) panel))
(defn summarize [panel]
  (let [scores (map #(get-in % [:metrics :score]) panel) mean (/ (reduce + scores) (count scores))
        variance (/ (reduce + (map #(* (- % mean) (- % mean)) scores)) (max 1 (dec (count scores))))]
    {:cases (count panel) :complete (count (filter #(= :complete (get-in % [:metrics :status])) panel))
     :mean-penalized-makespan (double mean) :sample-standard-deviation (Math/sqrt (double variance))
     :min-score (apply min scores) :max-score (apply max scores)}))
(defn paired-summary [old new]
  (u/ensure! (= (mapv :case old) (mapv :case new)) "Unpaired report" {})
  (let [deltas (mapv #(- (get-in %1 [:metrics :score]) (get-in %2 [:metrics :score])) old new)
        n (count deltas) mean (/ (reduce + deltas) n)
        variance (/ (reduce + (map #(let [d (- % mean)] (* d d)) deltas)) (max 1 (dec n)))
        se (Math/sqrt (/ (double variance) n))]
    {:deltas deltas :mean (double mean) :descriptive-normal-interval [(- (double mean) (* 1.96 se)) (+ (double mean) (* 1.96 se))]
     :independent-learning-runs 0 :interpretation "Fixture case dispersion only; not uncertainty over independent model learning runs."}))

(defn budget-fixture! [root config world]
  (let [store (str root "/budget-fixture.sqlite") id "budget-fixture"
        config (assoc-in config [:limits :calls] 1)
        p (provider/->FixtureProvider (atom {"root" [{:op :context/metadata :handle "jobs"}
                                                     {:op :done :summary "This response must not be dispatched"}]}))]
    (c/create-run! store id config (:hash f/initial-workflow))
    (c/put-context! store id "jobs" (:jobs (sim/observe (sim/initial-state world) nil)))
    (c/session! store id "root" nil)
    (let [result (runtime/run-session! {:store store :run id :registry root :provider p :workers (atom {})
                                       :allow-learning false :provenance :synthetic-fixture} "root" {})
          ledger (c/get-run store id)
          _ (u/ensure! (and (= :failed (:status result)) (= 1 (get-in ledger [:spent :calls])))
                       "Budget fixture did not stop at its limit" {})
          episode (records/save-episode! root "budget-fixture-0" world (sim/execution-failure world (:error result))
                    {:arm "budget-exhaustion-fixture" :artifact (:hash f/initial-policy) :provenance :synthetic-fixture
                     :note "Staged one-call budget test; not spontaneous model behavior."})]
      (records/write-events! (str root "/budget-fixture-events.jsonl") (:events ledger))
      {:result result :call-cap 1 :spent (:spent ledger) :reserved (:reserved ledger) :episode episode
       :provenance :synthetic-fixture :note "Staged transport fixture; no real model calls."})))

(defn fixture-demo! []
  (let [id (str "fixture-" (System/currentTimeMillis)) root (str "var/runs/" id) store (str root "/controller.sqlite")
        config (u/read-file "config/experiment.edn") begin (System/nanoTime)]
    (doseq [artifact [f/initial-policy f/packed-policy f/initial-workflow f/improved-workflow]] (a/save! root artifact))
    (c/create-run! store id config (:hash f/initial-workflow))
    (u/write-edn! (str root "/manifest.edn") (manifest config))
    (c/session! store id "root" nil)
    (let [world (first (:learning w/fixture-panels)) observations (:jobs (sim/observe (sim/initial-state world) nil))
          _ (c/put-context! store id "jobs" observations)
          ;; This scripted provider is explicitly a transport fixture. No discovery
          ;; is attributed to an experimental model.
          p (provider/->FixtureProvider
             (atom {"root" [{:op :context/query :handle "jobs" :query {:where {:ready true} :limit 8}}
                             {:op :agent/call :id "analyst" :task "Summarize selected frontier" :context (vec (take 3 (filter :ready observations)))}
                             {:op :done :summary "Fixture parent consumed child evidence; test candidate plumbing."}]
                    "analyst" [{:op :message/receive}
                               {:op :message/send :recipient "root" :correlation-id "analysis" :payload {:finding "Fixture: serial dispatch leaves capacity unused."}}
                               {:op :done :summary "Fixture child summary: consider parallel dispatch."}]}))]
      (runtime/run-session! {:store store :run id :registry root :provider p :workers (atom {}) :allow-learning false} "root" {:context-handle "jobs"}))
    (let [dev (:development w/fixture-panels)
          _ (c/consume! store id :evaluation-episodes (* 2 (count dev)))
          old (panel! root "development-parent" dev f/serial (:hash f/initial-policy))
          new (panel! root "development-candidate" dev f/packed (:hash f/packed-policy))
          evidence (a/promotion-evidence (paired-metrics old) (paired-metrics new) (:promotion config))
          _ (c/consume! store id :candidates 1)
          ;; Exercise a rejection with real measured parent-vs-parent results.
          rejection (a/promotion-evidence (paired-metrics old) (paired-metrics old) (:promotion config))
          _ (a/promote! store id root f/improved-workflow rejection)
          _ (c/consume! store id :candidates 1)
          _ (a/promote! store id root f/improved-workflow evidence)
          active (:active (c/get-run store id)) workflow (a/load! root active)
          policy-hash (get-in workflow [:forms :strategy :policy]) policy (f/resolve-policy (a/load! root policy-hash))
          selection (runtime/workflow! store id workflow "jobs" (fn [task selected]
                                                                {:provenance :synthetic-fixture :task task :selected-count (count selected)}))
          export-path (str root "/export") export (bundle/export! root export-path active :synthetic-fixture)
          cases (:heldout w/fixture-panels)
          _ (c/consume! store id :evaluation-episodes (* 4 (count cases)))
          frozen (panel! root "frozen-fixture" cases f/serial (:hash f/initial-policy))
          evolved (panel! root "retained-fixture" cases policy policy-hash)
          fifo (panel! root "fifo-baseline" cases baselines/fifo "fixed-capacity-fifo-v1")
          estimate (panel! root "estimate-baseline" cases baselines/estimate-aware "fixed-critical-path-v1")
          exhaustion (budget-fixture! root config (first (:learning w/fixture-panels)))
          _ (c/update-run! store id #(c/event % :budget-exhausted-fixture (dissoc exhaustion :episode)))
          snapshot (u/read-file (str root "/manifest.edn"))
          _ (assert-frozen-source! snapshot)
          report {:run-id id :provenance :synthetic-fixture :label "SYNTHETIC FIXTURE"
                  :manifest snapshot :promotion evidence :rejection rejection
                  :workflow-invocation selection :bundle export :export-path export-path
                  :conditions {:frozen (summarize frozen) :retained (summarize evolved)
                               :fifo (summarize fifo) :estimate (summarize estimate)}
                  :paired (paired-summary frozen evolved)
                  :raw-cases (vec (concat frozen evolved fifo estimate [(:episode exhaustion)]))
                  :budget-demonstration (dissoc exhaustion :episode)
                  :costs {:acquisition {:llm-calls 0 :tokens 0 :usd 0 :candidate-attempts 2 :evaluation-episodes (* 2 (count dev))}
                          :evaluation {:llm-calls 0 :tokens 0 :usd 0 :episodes (* 4 (count cases))}
                          :fixture-provider-calls (+ (get-in (c/get-run store id) [:spent :calls]) (get-in exhaustion [:spent :calls]))
                          :compute-efficiency-claim false}
                  :claims {:real-model-retained-skill false :model-changed-harness false
                           :fixture-workflow-modified true :model-benefit-survived-cold-boot :untested}
                  :wall-ms (/ (- (System/nanoTime) begin) 1000000.0)}]
      (c/update-run! store id #(assoc % :status :complete))
      (u/write-edn! (str root "/report.edn") report)
      (u/write-json! (str root "/report.json") report)
      (u/atomic-write! (str root "/events.jsonl") (str (str/join "\n" (map u/json-str (:events (c/get-run store id)))) "\n"))
      (u/atomic-write! "var/latest-run" id)
      {:run-id id :path root :export export-path :conditions (:conditions report) :promotion-approved (:approved evidence)})))

(defn bundle-policy [loaded]
  (let [active (get-in loaded [:manifest :active]) workflow (get-in loaded [:artifacts active])
        policy-id (get-in workflow [:forms :strategy :policy]) policy (get-in loaded [:artifacts policy-id])
        known (cond (= policy-id (:hash f/initial-policy)) f/initial-policy
                    (= policy-id (:hash f/packed-policy)) f/packed-policy)]
    (u/ensure! (= :synthetic-fixture (get-in loaded [:manifest :provenance])) "Real bundle execution requires verified SCI evaluation" {})
    (u/ensure! (and known (= policy (select-keys known (cond-> [:category :forms :interface :dependencies]
                                                       (contains? policy :provenance) (conj :provenance))))) "Bundle is not an exact trusted fixture" {})
    {:policy (f/resolve-policy known) :hash policy-id :workflow workflow}))

(defn evaluate! [export-path profile output]
  (u/ensure! (= "heldout" profile) "Supported profile: heldout" {})
  (let [loaded (bundle/load-bundle export-path) {:keys [policy hash]} (bundle-policy loaded)
        snapshot (manifest (u/read-file "config/experiment.edn"))
        _ (doseq [artifact [f/initial-policy f/packed-policy f/initial-workflow f/improved-workflow]] (a/save! output artifact))
        results (panel! output "bundle-fixture" (:heldout w/fixture-panels) policy hash)
        ablation (panel! output "parent-ablation-fixture" (:heldout w/fixture-panels) f/serial (:hash f/initial-policy))
        report {:run-id (.getName (io/file output)) :label "SYNTHETIC FIXTURE"
                :provenance :synthetic-fixture :mode :fresh-process-fixture-evaluation :manifest snapshot
                :bundle (get loaded :manifest) :process-id (.pid (java.lang.ProcessHandle/current))
                :conversation nil :learning false :promotion false
                :summary (summarize results) :ablation (summarize ablation)
                :conditions {:retained (summarize results) :fallback (summarize ablation)}
                :paired (paired-summary ablation results) :raw-cases results :raw-ablation ablation
                :costs {:evaluation {:llm-calls 0 :tokens 0 :usd 0 :episodes (+ (count results) (count ablation))}
                        :compute-efficiency-claim false}
                :claims {:H1 :untested :H2 :untested :note "Compiled fixture resolution only; no fresh model session or isolated SCI execution."}}]
    (assert-frozen-source! snapshot)
    (u/write-edn! (str output "/manifest.edn") snapshot)
    (u/write-edn! (str output "/report.edn") report) (u/write-json! (str output "/report.json") report)
    {:path output :summary (:summary report) :ablation (:ablation report)}))

(defn replay! [root]
  (let [files (filter #(and (.isFile %) (= "episodes" (.getName (.getParentFile %)))
                           (str/ends-with? (.getName %) ".edn")) (file-seq (io/file root)))]
    (u/ensure! (seq files) "No recorded episodes" {:root root})
    (doseq [file files :let [r (u/read-file file)]]
      (let [registry (.getParentFile (.getParentFile file))]
        (doseq [hash [(:artifact r) (:workflow r)] :when (and hash (re-matches #"[a-f0-9]{64}" hash))]
          (a/load! registry hash)))
      (sim/replay (:world r) (:records r) (:final-hash r) (get-in r [:metrics :status])))
    {:replayed (count files) :mode :recorded-actions :provider-rerun false}))
