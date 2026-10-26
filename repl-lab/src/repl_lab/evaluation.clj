(ns repl-lab.evaluation
  (:require [clojure.java.io :as io] [clojure.string :as str]
            [repl-lab.util :as u] [repl-lab.bundle :as bundle] [repl-lab.artifact :as a]
            [repl-lab.controller :as c] [repl-lab.runtime :as runtime] [repl-lab.provider :as provider]
            [repl-lab.live :as live] [repl-lab.fixtures :as f] [repl-lab.sim :as sim]
            [repl-lab.experiment :as experiment] [repl-lab.isolation :as isolation]))

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
                          artifact (a/make-artifact {:category (:category item) :source (pr-str forms)
                                                     :interface (:interface item) :dependencies (mapv :hash dependencies)
                                                     :author "fresh-evaluator" :parent nil :provenance provenance})]
                      (swap! restored assoc original artifact) artifact))))]
      (let [active (visit (get-in loaded [:manifest :active]) #{})]
        {:active active :by-original @restored
         :by-hash (into {} (map (juxt :hash identity) (vals @restored)))}))))

(defn episode! [{:keys [root id config provider execute provenance]} arm index world workflow policy]
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
              (assoc (execute selected world) :executed-artifact (:hash selected)))
            (catch Exception e
              ;; Failed inference, interpreter timeouts, and budget exhaustion are
              ;; retained as scored incomplete episodes. No score reaches the agent.
              (let [state (assoc (sim/initial-state world) :status :execution-failure)]
                {:state state :final-hash (sim/state-hash state) :records []
                 :metrics (sim/metrics state) :error (.getMessage e)})))
          ledger (c/get-run store run-id)
          record {:case (u/hash-value world) :arm arm :world world :metrics (:metrics run)
                  :artifact (or (:executed-artifact run) (:hash policy)) :workflow (:hash workflow)
                  :records (:records run) :final-hash (:final-hash run) :error (:error run)
                  :attempts (get-in run [:state :attempts]) :timeline (get-in run [:state :history])
                  :wall-ms (/ (- (System/nanoTime) begin) 1000000.0)
                  :usage {:spent (:spent ledger) :reserved (:reserved ledger)}
                  :model-identifiers (vec (set (keep #(get-in % [:response :model]) (vals (:provider-requests ledger)))))
                  :provenance provenance}]
      (u/write-edn! (str root "/episodes/" case-id ".edn") record)
      (u/atomic-write! (str root "/episodes/" case-id ".jsonl")
                       (str (str/join "\n" (map u/json-str (:records run))) "\n"))
      (u/atomic-write! (str root "/sessions/" case-id ".jsonl")
                       (str (str/join "\n" (map u/json-str (:events ledger))) "\n"))
      record)))

(defn paired! [env worlds workflow policy]
  (let [pairs (mapv (fn [i world]
                      ;; Alternate arm order. Each episode gets its own identical
                      ;; caps, so one arm cannot drain the other's allowance.
                      (let [arms (if (even? i) [:frozen :evolving] [:evolving :frozen])]
                        (into {} (for [arm arms]
                                   [arm (episode! env (name arm) i world
                                          (if (= :frozen arm) f/initial-workflow workflow)
                                          (if (= :frozen arm) f/initial-policy policy))])))) (range) worlds)
        frozen (mapv :frozen pairs) evolving (mapv :evolving pairs)]
    {:raw-frozen frozen :raw-evolving evolving
     :conditions {:frozen (experiment/summarize frozen) :evolving (experiment/summarize evolving)}
     :paired (experiment/paired-summary frozen evolving)}))

(defn aggregate-usage [records]
  {:spent (reduce #(merge-with + %1 (get-in %2 [:usage :spent])) {} records)
   :reserved-unknown (reduce #(merge-with + %1 (get-in %2 [:usage :reserved])) {} records)})

(defn evaluate-live! [export-path profile env cold?]
  (u/ensure! (= "heldout" profile) "Supported final profile: heldout" {})
  (let [{:keys [model cap input-rate output-rate api-key]} (live/options env)
        check (isolation/doctor)]
    (u/ensure! (:ready check) "Final model evaluation requires isolated SCI" check)
    (u/ensure! (seq api-key) "ANTHROPIC_API_KEY required" {})
    (let [loaded (bundle/load-bundle export-path) export-root (.getCanonicalFile (io/file export-path))
          acquisition-root (.getParentFile export-root)
          acquisition-manifest (u/read-file (io/file acquisition-root "manifest.edn"))
          _ (experiment/assert-frozen-source! acquisition-manifest)
          _ (u/ensure! (= (:image check) (get-in acquisition-manifest [:isolation :image])) "Worker image differs from acquisition" {})
          _ (u/ensure! (= model (get-in acquisition-manifest [:model :requested])) "Evaluation model must match acquisition model" {})
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
                     (assoc-in [:limits :calls] 6) (assoc-in [:limits :tokens] 64000))
          library (restore-library loaded) workflow (:active library)
          policy-id (get-in workflow [:forms :strategy :policy])
          policy (get-in library [:by-hash policy-id])
          dependencies (letfn [(visit [hash stack]
                                (u/ensure! (not (contains? stack hash)) "Bundle dependency cycle" {})
                                (let [item (get-in library [:by-hash hash])]
                                  (mapcat (fn [dep] (concat (visit dep (conj stack hash))
                                                           [(get-in library [:by-hash dep])])) (:dependencies item))))]
                         (vec (distinct (visit policy-id #{}))))
          p (provider/->AnthropicProvider model api-key input-rate output-rate 2048)]
      ;; Atomic reservation: another evaluator cannot consume the same final split.
      (let [seal-path (.toPath seal)]
        (java.nio.file.Files/write seal-path (.getBytes (pr-str {:evaluation id :bundle (u/hash-value (:manifest loaded)) :created (u/now)}) "UTF-8")
                                   (into-array java.nio.file.OpenOption [java.nio.file.StandardOpenOption/CREATE_NEW java.nio.file.StandardOpenOption/WRITE])))
      (doseq [dependency dependencies] (a/save! root dependency))
      (let [report (paired! {:root root :id id :config config :provider p
                            :execute (fn [selected world] (live/run-policy! selected world (if (= (:hash selected) (:hash policy)) dependencies [])))
                            :provenance :recorded-model-run} worlds workflow policy)
            costs (aggregate-usage (concat (:raw-frozen report) (:raw-evolving report)))
            acquisition (select-keys (u/read-file (io/file acquisition-root "checkpoint.edn")) [:spent :reserved])
            report (assoc report :provenance :recorded-model-run :model model :config config
                          :manifest (assoc (experiment/manifest config) :model {:requested model :provider :anthropic
                                            :returned-identifiers (vec (set (mapcat :model-identifiers (concat (:raw-frozen report) (:raw-evolving report)))))})
                          :costs {:acquisition acquisition :evaluation costs
                                  :acquisition-plus-evaluation-spent (merge-with + (:spent acquisition) (:spent costs))
                                  :usd-basis :operator-supplied-token-rates :invoiced-usd nil
                                  :compute-efficiency-claim false}
                          :acquisition-manifest acquisition-manifest :bundle (:manifest loaded)
                          :artifact-remap (into {} (map (fn [[original artifact]] [original (:hash artifact)]) (:by-original library)))
                          :mode (if cold? :cold-boot-and-fallback-ablation :sealed-final)
                          :independent-learning-runs 1
                          :paired (assoc (:paired report) :independent-learning-runs 1
                                         :interpretation "Descriptive paired case dispersion within one learned library; not uncertainty across independent learning runs.")
                          :claims {:H1 :requires-analysis :H2 (if cold? :requires-analysis :untested) :H3 :out-of-scope
                                   :note "One learning run. No matched-total-budget compute-efficiency claim."})]
        (u/write-edn! (str root "/report.edn") report) (u/write-json! (str root "/report.json") report)
        {:path root :conditions (:conditions report)}))))
