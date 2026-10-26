(ns repl-lab.evaluation
  (:require [clojure.java.io :as io] [clojure.string :as str]
            [repl-lab.util :as u] [repl-lab.bundle :as bundle] [repl-lab.artifact :as a]
            [repl-lab.controller :as c] [repl-lab.runtime :as runtime] [repl-lab.provider :as provider]
            [repl-lab.live :as live] [repl-lab.fixtures :as f] [repl-lab.sim :as sim]
            [repl-lab.experiment :as experiment] [repl-lab.isolation :as isolation] [repl-lab.records :as records]
            [repl-lab.baselines :as baselines] [repl-lab.limits :as limits]))

(defn restore-library [loaded]
  ;; Export omits author/session metadata. Rebuild fresh envelopes and remap every
  ;; dependency consistently. Policy forms stay byte-for-form equivalent.
  (let [restored (atom {})]
    (letfn [(visit [original stack]
              (or (get @restored original)
                  (do
                    (u/ensure! (not (contains? stack original)) "Bundle dependency cycle" {})
                    (let [item (get-in loaded [:artifacts original])
                          _ (u/ensure! item "Missing bundle artifact" {})
                          dependencies (mapv #(visit % (conj stack original)) (:dependencies item))
                          forms (if (= :workflow (:category item))
                                  (assoc-in (:forms item) [:strategy :policy]
                                            (:hash (visit (get-in item [:forms :strategy :policy]) (conj stack original))))
                                  (:forms item))
                          provenance (or (:provenance item)
                                         (when (= :synthetic-fixture (get-in loaded [:manifest :provenance])) :developer-fixture))
                          artifact (a/make-artifact (cond-> {:category (:category item) :source (a/forms-source forms (a/language item) (:category item))
                                                     :interface (:interface item) :dependencies (mapv :hash dependencies)
                                                     :author "fresh-evaluator" :parent nil :provenance provenance}
                                                     (contains? item :language) (assoc :language (:language item))))]
                      (swap! restored assoc original artifact) artifact))))]
      (let [active (visit (get-in loaded [:manifest :active]) #{})]
        {:active active :by-original @restored
         :by-hash (into {} (map (juxt :hash identity) (vals @restored)))}))))

(defn fresh-initial-library []
  ;; Apply the same identity reset to the control as to an exported library.
  ;; With no retained change, both arms must expose identical artifact metadata.
  (restore-library {:manifest {:active (:hash f/initial-workflow) :provenance :synthetic-fixture}
                    :artifacts (into {} (for [artifact [f/initial-policy f/initial-workflow]]
                                          [(:hash artifact) (select-keys artifact [:category :forms :interface :dependencies :provenance])]))}))

(defn episode! [{:keys [root id config provider execute provenance source-snapshot]} arm index world workflow policy]
  (when source-snapshot (experiment/assert-frozen-source! source-snapshot))
  (let [case-id (str arm "-" index) store (str root "/sessions/" case-id ".sqlite")
        run-id (str id "-" case-id) session "root"
        observation (sim/observe (sim/initial-state world) nil) begin (System/nanoTime)]
    (a/save! root workflow) (a/save! root policy)
    (c/create-run! store run-id config (:hash workflow))
    (c/put-context! store run-id "jobs" (:jobs observation))
    (c/put-context! store run-id "workers" (:workers observation))
    (c/put-context! store run-id "observation" [observation])
    (c/put-context! store run-id "artifacts" [workflow policy])
    (c/session! store run-id session nil)
    (let [env {:store store :run run-id :registry root :provider provider :workers (atom {}) :allow-learning false :provenance provenance}
          run
          (try
            (let [selection (runtime/workflow! store run-id workflow "jobs"
                              (fn [task selected]
                                (runtime/broker! env session {:op :agent/call :id "analyst" :task task :context selected})))
                  result (runtime/run-session! env session
                           {:task "Solve this task. You may inspect context, use SCI, call children, and choose a temporary policy. The library is frozen."
                            :workflow-result selection :context-handles ["jobs" "workers" "observation" "artifacts"]})
                  _ (u/ensure! (not (:error result)) "Agent did not complete within budget" result)
                  selected (or (get-in (c/get-run store run-id) [:sessions session :temporary-policy]) policy)]
              (a/save! root selected)
              (assoc (execute selected world (limits/from-run (c/get-run store run-id))) :executed-artifact (:hash selected)))
            (catch Exception e
              ;; Failed inference, interpreter timeouts, and budget exhaustion are
              ;; retained as scored incomplete episodes. No score reaches the agent.
              (sim/execution-failure world (.getMessage e))))
          ledger (c/get-run store run-id)
          record {:case (u/hash-value world) :arm arm :world world :metrics (:metrics run)
                  :artifact (or (:executed-artifact run) (:hash policy)) :workflow (:hash workflow)
                  :records (:records run) :final-hash (:final-hash run) :error (:error run)
                  :attempts (get-in run [:state :attempts]) :timeline (get-in run [:state :history])
                  :wall-ms (/ (- (System/nanoTime) begin) 1000000.0)
                  :usage {:spent (:spent ledger) :reserved (:reserved ledger)}
                  :execution-limits (limits/from-run ledger)
                  :model-identifiers (vec (set (keep #(get-in % [:response :model]) (vals (:provider-requests ledger)))))
                  :provenance provenance}]
      (records/save-episode! root case-id world run record)
      (u/atomic-write! (str root "/sessions/" case-id ".jsonl")
                       (str (str/join "\n" (map u/json-str (:events ledger))) "\n"))
      (when source-snapshot (experiment/assert-frozen-source! source-snapshot))
      record)))

(defn paired! [env worlds workflow policy]
  (let [initial (or (:frozen-library env) (fresh-initial-library))
        frozen-workflow (:active initial)
        frozen-policy (get-in initial [:by-hash (get-in frozen-workflow [:forms :strategy :policy])])
        pairs (mapv (fn [i world]
                      ;; Alternate arm order. Each episode gets its own identical
                      ;; caps, so one arm cannot drain the other's allowance.
                      (let [arms (if (even? i) [:frozen :evolving] [:evolving :frozen])]
                        (into {} (for [arm arms]
                                   [arm (episode! env (name arm) i world
                                          (if (= :frozen arm) frozen-workflow workflow)
                                          (if (= :frozen arm) frozen-policy policy))])))) (range) worlds)
        frozen (mapv :frozen pairs) evolving (mapv :evolving pairs)]
    {:raw-frozen frozen :raw-evolving evolving
     :conditions {:frozen (experiment/summarize frozen) :evolving (experiment/summarize evolving)}
     :paired (experiment/paired-summary frozen evolving)}))

(defn aggregate-usage [records]
  {:spent (reduce #(merge-with + %1 (get-in %2 [:usage :spent])) {} records)
   :reserved-unknown (reduce #(merge-with + %1 (get-in %2 [:usage :reserved])) {} records)})

(defn code-panel!
  ([root arm worlds policy execute] (code-panel! root arm worlds policy execute (u/read-file "config/experiment.edn")))
  ([root arm worlds policy execute config]
  (a/save! root policy)
  (mapv (fn [index world]
          (let [begin (System/nanoTime) execution-options (limits/fresh config)
                run (try (execute policy world execution-options) (catch Exception e (sim/execution-failure world (.getMessage e))))]
            (records/save-episode! root (str arm "-" index) world run
                                  {:arm arm :artifact (:hash policy) :execution-limits execution-options
                                   :wall-ms (/ (- (System/nanoTime) begin) 1000000.0)})))
        (range) worlds)))

(defn evaluate-live! [export-path profile env cold?]
  (u/ensure! (= "heldout" profile) "Supported final profile: heldout" {})
  (let [{:keys [model cap input-rate output-rate] :as options} (live/options env)
        check (isolation/require-tested!)]
    (u/ensure! (:ready check) "Final model evaluation requires isolated SCI" check)
    (let [prepared (live/prepare-provider! options)
          loaded (bundle/load-bundle export-path) export-root (.getCanonicalFile (io/file export-path))
          acquisition-root (.getParentFile export-root)
          acquisition-manifest (u/read-file (io/file acquisition-root "manifest.edn"))
          _ (experiment/assert-frozen-source! acquisition-manifest)
          _ (u/ensure! (= (:image check) (get-in acquisition-manifest [:isolation :image])) "Worker image differs from acquisition" {})
          _ (u/ensure! (= model (get-in acquisition-manifest [:model :requested])) "Evaluation model must match acquisition model" {})
          _ (u/ensure! (= [(get-in prepared [:model :provider]) input-rate output-rate (get-in prepared [:transport :cli_sha256])]
                         [(get-in acquisition-manifest [:model :provider]) (get-in acquisition-manifest [:model :input-usd-per-m])
                          (get-in acquisition-manifest [:model :output-usd-per-m]) (get-in acquisition-manifest [:transport :cli_sha256])])
                       "Evaluation provider, rates or CLI differ from acquisition" {})
          split-file (io/file acquisition-root "sealed-splits.edn") splits (u/read-file split-file)
          _ (u/ensure! (= (get-in acquisition-manifest [:config :split-version])
                         (u/hash-value [(:learning splits) (:development splits) (:final splits) (:coldboot splits)])) "Sealed split digest mismatch" {})
          seal (io/file acquisition-root (if cold? "cold-evaluation-seal.edn" "final-evaluation-seal.edn"))
          _ (u/ensure! (not (.exists seal)) "Final split already used or reserved. Create a new experiment for further tuning." {})
          id (str "evaluation-" (System/currentTimeMillis)) root (str "var/evaluations/" id)
          worlds (if cold? (:coldboot splits) (:final splits)) episode-count (* 2 (count worlds))
          config (-> (u/read-file "config/experiment.edn")
                     (assoc :mode :live :provenance :recorded-model-run :split-version (get-in acquisition-manifest [:config :split-version]))
                     (assoc-in [:limits :usd] (/ cap episode-count))
                     (assoc-in [:limits :calls] 6) (assoc-in [:limits :tokens] 64000)
                     (live/provider-scope options))
          library (restore-library loaded) workflow (:active library)
          initial-library (fresh-initial-library)
          initial-policy (get-in initial-library [:by-original (:hash f/initial-policy)])
          policy-id (get-in workflow [:forms :strategy :policy])
          policy (get-in library [:by-hash policy-id])
          dependencies (letfn [(visit [hash stack]
                                (u/ensure! (not (contains? stack hash)) "Bundle dependency cycle" {})
                                (let [item (get-in library [:by-hash hash])]
                                  (mapcat (fn [dep] (concat (visit dep (conj stack hash))
                                                           [(get-in library [:by-hash dep])])) (:dependencies item))))]
                         (vec (distinct (visit policy-id #{}))))
          p (:adapter prepared)]
      ;; Atomic reservation: another evaluator cannot consume the same final split.
      (let [seal-path (.toPath seal)]
        (java.nio.file.Files/write seal-path (.getBytes (pr-str {:evaluation id :bundle (u/hash-value (:manifest loaded)) :created (u/now)}) "UTF-8")
                                   (into-array java.nio.file.OpenOption [java.nio.file.StandardOpenOption/CREATE_NEW java.nio.file.StandardOpenOption/WRITE])))
      (doseq [dependency dependencies] (a/save! root dependency))
      (let [execute (fn [selected world options] (live/run-policy! selected world (if (= (:hash selected) (:hash policy)) dependencies []) options))
            report (paired! {:root root :id id :config config :provider p
                            :execute execute :frozen-library initial-library :source-snapshot acquisition-manifest
                            :provenance :recorded-model-run} worlds workflow policy)
            fifo (experiment/panel! root "fifo-baseline" worlds baselines/fifo "fixed-capacity-fifo-v1")
            estimate (experiment/panel! root "estimate-baseline" worlds baselines/estimate-aware "fixed-critical-path-v1")
            retained-code (code-panel! root "retained-code" worlds policy execute config)
            removed-code (code-panel! root "skill-removed" worlds initial-policy execute config)
            costs (aggregate-usage (concat (:raw-frozen report) (:raw-evolving report)))
            acquisition (select-keys (u/read-file (io/file acquisition-root "checkpoint.edn")) [:spent :reserved])
            _ (experiment/assert-frozen-source! acquisition-manifest)
            report (assoc report :run-id id :label "RECORDED MODEL RUN" :provenance :recorded-model-run :model model :config config
                          :raw-cases (vec (concat (:raw-frozen report) (:raw-evolving report) fifo estimate retained-code removed-code))
                          :conditions (assoc (:conditions report) :fifo (experiment/summarize fifo) :estimate (experiment/summarize estimate))
                          :ablation {:retained (experiment/summarize retained-code) :fallback (experiment/summarize removed-code)
                                     :paired (assoc (experiment/paired-summary removed-code retained-code) :independent-learning-runs 1)
                                     :llm-calls 0 :interpretation "Direct execution of retained policy versus contract-compatible initial policy; no model policy replacement. This isolates code effect, not agent inference."}
                          :manifest (assoc (experiment/manifest config) :transport (:transport prepared)
                                           :model (assoc (:model prepared) :returned-identifiers
                                            (vec (set (mapcat :model-identifiers (concat (:raw-frozen report) (:raw-evolving report)))))))
                          :costs {:acquisition acquisition :evaluation costs
                                  :acquisition-plus-evaluation-spent (merge-with + (:spent acquisition) (:spent costs))
                                  :usd-basis (:usd-basis prepared) :invoiced-usd nil
                                  :compute-efficiency-claim false}
                          :acquisition-manifest acquisition-manifest :bundle (:manifest loaded)
                          :artifact-remap (into {} (map (fn [[original artifact]] [original (:hash artifact)]) (:by-original library)))
                          :mode (if cold? :cold-boot-and-fallback-ablation :sealed-final)
                          :independent-learning-runs 1
                          :paired (assoc (:paired report) :independent-learning-runs 1
                                         :interpretation "Descriptive paired case dispersion within one learned library; not uncertainty across independent learning runs.")
                          :claims {:H1 :requires-analysis :H2 (if cold? :requires-analysis :untested) :H3 :out-of-scope
                                   :note "One learning run. No matched-total-budget compute-efficiency claim."})]
        (records/write-events! (str root "/events.jsonl")
          (mapcat (fn [record]
                    (let [case-index (.indexOf worlds (:world record)) case-id (str (:arm record) "-" case-index)]
                      (map #(assoc % :task case-id :arm (:arm record))
                           (:events (c/get-run (str root "/sessions/" case-id ".sqlite") (str id "-" case-id))))))
                  (concat (:raw-frozen report) (:raw-evolving report))))
        (u/write-edn! (str root "/report.edn") report) (u/write-json! (str root "/report.json") report)
        {:path root :conditions (:conditions report)}))))
