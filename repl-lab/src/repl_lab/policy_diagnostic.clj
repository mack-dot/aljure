(ns repl-lab.policy-diagnostic
  "Versioned fixed-policy diagnostic. No provider adapter or model invocation."
  (:refer-clojure :exclude [run!])
  (:require [clojure.java.io :as io] [clojure.string :as str]
            [repl-lab.util :as u] [repl-lab.artifact :as a]
            [repl-lab.fixtures :as fixtures] [repl-lab.workloads :as workloads]
            [repl-lab.experiment :as experiment] [repl-lab.isolation :as isolation]
            [repl-lab.execution :as execution] [repl-lab.executable :as executable]
            [repl-lab.sim :as sim] [repl-lab.records :as records]
            [repl-lab.limits :as limits]))

(def version "policy-runtime-diagnostic-v1")
(def original-hash "aa12262b1989915c4a34dad851efeff75b2040964757825ac41e0d5c3bb90003")
(def retained-hash "834a4e02cd945ad6f889947c2ad4223e04a0bb175e4d7ba266329f2193a0e4d3")
(def retained-registry "var/runs/model-1793062055972/tasks/evolving-0")
(defn worlds []
  (mapv (fn [index seed]
          (workloads/generate seed
            (if (< index 6) {:size 12 :structure :layered :fault-count 1 :resource-mix false}
              {:size 24 :structure (if (< index 9) :fanout :chain) :fault-count 3 :resource-mix true})))
        (range 12) (range 830000 830012)))
(defn plan []
  (vec (for [repetition (range 2) index (range 12)
             arm (if (even? (+ repetition index)) [:original :retained] [:retained :original])]
         {:repetition repetition :index index :arm arm
          :id (str (name arm) "-" index "-r" repetition)})))
(defn exception-data [error]
  {:message (.getMessage error) :data (ex-data error) :class (.getName (class error))})
(defn error-kind [error]
  (let [s (str (:message error) " " (:data error))]
    (cond (re-find #"Worker rejected expression" s) :code-rejection
          (re-find #"[Oo]ut[Oo]f[Mm]emory|OOM|memory limit" s) :resource-memory
          (re-find #"wall-time|wall budget|response timeout|Task wall" s) :resource-time
          (re-find #"cleanup|termination" s) :cleanup
          (re-find #"Generated-code execution disabled|Docker|Worker terminated" s) :infrastructure-or-unresolved
          :else :unresolved)))

(defn prepare! [root]
  (u/ensure! (not (.exists (io/file root))) "Diagnostic output already exists" {})
  (let [config (-> (u/read-file "config/experiment.edn")
                   (assoc :mode :no-inference :provenance :fixed-policy-diagnostic)
                   (assoc-in [:limits :calls] 0) (assoc-in [:limits :tokens] 0)
                   (assoc-in [:limits :usd] 0))
        original fixtures/initial-policy retained (a/load! retained-registry retained-hash)
        cases (worlds) old-splits (u/read-file "var/runs/model-1793062055972/sealed-splits.edn")
        old-cases (set (map u/hash-value (mapcat val old-splits)))
        _ (u/ensure! (not-any? old-cases (map u/hash-value cases)) "Diagnostic overlaps prior cases" {})
        _ (u/ensure! (= original-hash (:hash original)) "Initial policy differs" {})
        check (isolation/doctor)
        _ (u/ensure! (:ready check) "Docker readiness failed" check)
        manifest (assoc (experiment/manifest config) :version version :model "claude-sonnet-5-5"
                        :model-role :artifact-source-only :model-calls 0 :inference-usd 0
                        :isolation check :world-hashes (mapv u/hash-value cases) :plan (plan)
                        :policies {:original original-hash :retained retained-hash}
                        :readiness-control "(+ 20 22)" :retries 0
                        :stop-rule "Stop after an unconfirmed startup/readiness or cleanup; preserve unattempted cases.")]
    (a/save! root original) (a/save! root retained)
    (u/write-edn! (str root "/worlds.edn") cases)
    (u/write-json! (str root "/worlds.json") cases)
    (u/write-edn! (str root "/manifest.edn") manifest)
    (u/write-json! (str root "/manifest.json") manifest)
    {:prepared root :planned-episodes 48 :model-calls 0}))

(defn episode! [root config world {:keys [id arm] :as task} policy]
  (let [backend (execution/backend :clojure) worker (atom nil) stage (atom :startup)
        stages (atom []) calls (atom 0) execution-error (atom nil) cleanup-error (atom nil)
        options (limits/fresh config) begin (System/nanoTime)
        mark! (fn [phase] (swap! stages conj {:phase phase :elapsed-ms (/ (- (System/nanoTime) begin) 1e6)}))
        result
        (try
          (reset! worker (execution/open! backend (:deadline-ms options)))
          (u/ensure! (= 42 (execution/evaluate! backend @worker "(+ 20 22)" {})) "Readiness control failed" {})
          (mark! :startup-ready)
          (reset! stage :code-loading)
          (executable/load! backend @worker policy [])
          (mark! :code-loaded)
          (reset! stage :execution)
          (let [run (sim/run-episode world
                      (fn [observation memory]
                        (swap! calls inc)
                        (try (executable/call! backend @worker policy [observation memory])
                             (catch Exception e (reset! execution-error (exception-data e)) (throw e)))) options)]
            (mark! :execution-finished)
            {:run run :failure-stage (when-not (= :complete (get-in run [:metrics :status])) :execution)
             :failure-kind (when-not (= :complete (get-in run [:metrics :status]))
                             (if @execution-error (error-kind @execution-error) :algorithm-or-contract))
             :exception @execution-error})
          (catch Exception e
            (let [error (exception-data e)]
              {:run (sim/execution-failure world (:message error)) :failure-stage @stage
               :failure-kind (error-kind error) :exception error}))
          (finally
            (when @worker
              (try (execution/close! backend @worker)
                   (catch Exception e (reset! cleanup-error (exception-data e)))))
            (mark! :cleanup-finished)))
        process (:process @worker)
        extra (merge task (dissoc result :run)
                {:artifact (:hash policy) :execution-limits options :stages @stages
                 :attempted-policy-invocations @calls
                 :supervisor-pid (when process (.pid process))
                 :supervisor-exit (when (and process (not (.isAlive process))) (.exitValue process))
                 :worker-stderr (when-let [errors (:errors @worker)] (deref errors 5000 "Diagnostics unavailable"))
                 :cleanup-error @cleanup-error :wall-ms (/ (- (System/nanoTime) begin) 1e6)
                 :inference {:calls 0 :input-tokens 0 :output-tokens 0 :usd 0}
                 :local-compute-usd nil :provenance :model-authored-retained-policy-diagnostic})
        record (records/save-episode! root id world (:run result) extra)]
    (u/write-json! (str root "/episodes/" id ".summary.json") (dissoc record :world :records :timeline :attempts))
    (println (u/json-str (select-keys record [:id :arm :failure-stage :failure-kind :metrics :wall-ms])))
    (flush)
    record))

(defn run! [root]
  (let [manifest (u/read-file (str root "/manifest.edn")) config (:config manifest)
        cases (u/read-file (str root "/worlds.edn")) audit-dir (System/getenv "REPL_LAB_WORKER_AUDIT_DIR")]
    (u/ensure! (= version (:version manifest)) "Diagnostic version differs" {})
    (u/ensure! (= (.getCanonicalPath (io/file root "workers"))
                   (when audit-dir (.getCanonicalPath (io/file audit-dir)))) "Worker audit directory must be this run's workers directory" {})
    (experiment/assert-frozen-source! manifest)
    (u/ensure! (= (:world-hashes manifest) (mapv u/hash-value cases)) "Worlds changed" {})
    (u/ensure! (= (get-in manifest [:isolation :image]) (:image (isolation/require-tested!))) "Image differs" {})
    (u/ensure! (.createNewFile (io/file root "execution.seal")) "Diagnostic already attempted; no retries" {})
    (loop [remaining (:plan manifest) results []]
      (if (seq remaining)
        (let [task (first remaining) policy (a/load! root (get-in manifest [:policies (:arm task)]))
              record (episode! root config (cases (:index task)) task policy)
              stop? (or (= :startup (:failure-stage record)) (:cleanup-error record)
                        (let [path (io/file "var/isolation-quarantine")] (and (.exists path) (seq (.listFiles path)))))
              results (conj results record)]
          (u/write-edn! (str root "/progress.edn") {:attempted (count results) :stopped stop?})
          (if stop?
            (let [report {:status :stopped-unhealthy :attempted (count results) :planned 48
                          :unattempted (vec (rest remaining)) :raw-cases results :model-calls 0}]
              (u/write-edn! (str root "/report.edn") report) (u/write-json! (str root "/report.json") report)
              {:status :stopped-unhealthy :path root :attempted (count results)})
            (recur (rest remaining) results)))
        (let [report {:status :complete :planned 48 :attempted 48 :raw-cases results :model-calls 0
                      :conditions (into {} (for [arm [:original :retained]]
                                            [arm (experiment/summarize (filter #(= arm (:arm %)) results))]))}]
          (experiment/assert-frozen-source! manifest)
          (u/write-edn! (str root "/report.edn") report) (u/write-json! (str root "/report.json") report)
          {:status :complete :path root :conditions (:conditions report)})))))

(defn -main [action root]
  (try
    (u/ensure! (and root (str/starts-with? root "var/diagnostics/")) "Use a new var/diagnostics/ path" {})
    (println (u/json-str (case action "prepare" (prepare! root) "run" (run! root)
                               (u/fail "Actions: prepare, run" {}))))
    (shutdown-agents)
    (catch Exception e
      (println (u/json-str {:error (.getMessage e) :data (ex-data e)}))
      (shutdown-agents) (System/exit 2))))
