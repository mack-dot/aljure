(ns repl-lab.live
  (:require [clojure.java.io :as io] [clojure.string :as str] [repl-lab.util :as u]
            [repl-lab.isolation :as iso] [repl-lab.controller :as c] [repl-lab.artifact :as a]
            [repl-lab.fixtures :as f] [repl-lab.workloads :as w] [repl-lab.sim :as sim]
            [repl-lab.runtime :as runtime] [repl-lab.provider :as provider]
            [repl-lab.bundle :as bundle] [repl-lab.experiment :as experiment]
            [repl-lab.records :as records] [repl-lab.limits :as limits]
            [repl-lab.execution :as execution] [repl-lab.executable :as executable]
            [repl-lab.python-source :as python] [repl-lab.subscription :as subscription]))

(defn positive-number [value label]
  (let [n (try (Double/parseDouble (or value "")) (catch Exception _ 0.0))]
    (u/ensure! (and (Double/isFinite n) (pos? n)) (str "Positive " label " is required") {}) n))
(defn options [env]
  (u/ensure! (= "1" (get env "LIVE")) "Paid calls are disabled. Set LIVE=1 with an explicit model and cap." {})
  (let [model (get env "MODEL") cap (positive-number (get env "MAX_USD") "MAX_USD")]
    (u/ensure! (and (seq model) (not (str/ends-with? model "latest"))) "Set a pinned MODEL identifier" {})
    (u/ensure! (#{"anthropic" "claude-subscription"} (get env "INFERENCE_PROVIDER" "anthropic")) "Unsupported inference provider" {})
    {:model model :cap cap :provider (if (= "claude-subscription" (get env "INFERENCE_PROVIDER")) :claude-code-subscription :anthropic)
     :input-rate (positive-number (get env "INPUT_USD_PER_M") "INPUT_USD_PER_M")
     :output-rate (positive-number (get env "OUTPUT_USD_PER_M") "OUTPUT_USD_PER_M")
     :api-key (get env "ANTHROPIC_API_KEY")}))

(defn prepare-provider! [{:keys [model provider input-rate output-rate api-key]}]
  (let [subscription? (= provider :claude-code-subscription)
        _ (if subscription?
            (u/ensure! (= [model input-rate output-rate] ["claude-sonnet-5-5" 2.0 10.0]) "Subscription experiment model/rates differ" {})
            (u/ensure! (seq api-key) "ANTHROPIC_API_KEY is required for the direct API" {}))
        cli (when subscription? (subscription/preflight!))]
    {:adapter (if cli (subscription/->SubscriptionProvider model input-rate output-rate 2048 cli)
                  (provider/->AnthropicProvider model api-key input-rate output-rate 2048))
     :transport (when cli (select-keys cli [:cli_version :cli_sha256 :auth]))
     :model {:requested model :provider provider :input-usd-per-m input-rate :output-usd-per-m output-rate
             :max-output-tokens 2048}
     :usd-basis (if cli :standard-rate-equivalent :operator-supplied-token-rates)}))

(defn provider-scope [config options]
  (cond-> config (= :claude-code-subscription (:provider options))
    (assoc :subscription-scope :learning-evaluation)))

(defn dependency-closure [registry artifact]
  (a/dependency-closure registry artifact))

(defn policy-response [language response]
  (if (and (= language :python) (map? response) (vector? (:actions response)))
    (update response :actions #(mapv (fn [action]
                                      (if (and (map? action) (string? (:op action)))
                                        (update action :op keyword) action)) %))
    response))

(defn run-policy!
  ([artifact world] (run-policy! artifact world []))
  ([artifact world dependencies]
   (run-policy! artifact world dependencies (limits/fresh (u/read-file "config/experiment.edn"))))
  ([artifact world dependencies execution-options]
  (binding [python/*deadline-ms* (:deadline-ms execution-options)]
  (let [language (a/language artifact) backend (execution/backend language)
        worker (execution/open! backend (:deadline-ms execution-options)) begin (System/nanoTime)]
    (try
      (a/verify artifact)
      (u/ensure! (= :policy (:category artifact)) "Expected policy" {})
      (executable/load! backend worker artifact dependencies)
      (let [result (sim/run-episode world
                     (fn [obs memory] (policy-response language (executable/call! backend worker artifact [obs memory])))
                     execution-options)]
        (assoc result :wall-ms (/ (- (System/nanoTime) begin) 1000000.0)))
      (finally (execution/close! backend worker)))))))

(defn development-panel!
  ([store id registry policy-hash worlds]
   (development-panel! store id registry policy-hash worlds run-policy!))
  ([store id registry policy-hash worlds execute]
   (let [artifact (a/load! registry policy-hash)]
     (mapv
       (fn [world]
         (c/consume! store id :evaluation-episodes 1)
         (let [episode-id (str "development-" (java.util.UUID/randomUUID)) begin (System/nanoTime)]
           (c/update-run! store id #(do (u/ensure! (nil? (:episode %)) "Episode already active" {})
                                       (assoc % :episode {:id episode-id :artifact policy-hash})))
           (try
             (let [execution-options (limits/from-run (c/get-run store id))
                   run (try (execute artifact world (dependency-closure registry artifact) execution-options)
                            (catch Exception e (sim/execution-failure world (.getMessage e))))
                   record (records/save-episode! registry episode-id world run
                            {:arm "development" :artifact policy-hash
                             :wall-ms (/ (- (System/nanoTime) begin) 1000000.0) :execution-limits execution-options})
                   handle (str "trace-" episode-id)
                   ;; Full worlds, ownership hashes and future events stay in the
                   ;; controller record. Only permitted observations enter context.
                   visible (mapv #(select-keys % [:type :action :accepted :error :observation :response]) (:records run))]
               (c/put-context-block! store id handle visible)
               (c/update-run! store id #(-> %
                  (update-in [:contexts "trace-index"] (fnil conj [])
                             {:handle handle :artifact policy-hash :records (count visible)})
                  (c/event :development-episode
                           {:artifact policy-hash :case (:case record) :record episode-id
                            :metrics (:metrics run) :wall-ms (:wall-ms record)})))
               (assoc (:metrics run) :case (:case record)))
             (finally (c/update-run! store id #(dissoc % :episode)))))) worlds))))

(defn copy-library! [from to workflow]
  (doseq [artifact (conj (dependency-closure from workflow) workflow)] (a/save! to artifact)))

(defn finish-task! [{:keys [config provenance execute]} arm index world workflow task-root run-id begin]
  (let [store (str task-root "/controller.sqlite") session "root"]
    (let [ledger (c/get-run store run-id) active (a/load! task-root (:active ledger))
          policy (runtime/selected-policy task-root ledger session
                     (a/load! task-root (get-in active [:forms :strategy :policy])))
          _ (a/save! task-root policy)
          ;; A failed model task stays failed; do not substitute a successful baseline.
          run (if (and (= :complete (:status ledger)) (not (.exists (io/file task-root "episodes/learning.edn"))))
                (try (execute policy world (dependency-closure task-root policy) (limits/from-run ledger))
                     (catch Exception e (sim/execution-failure world (.getMessage e))))
                (sim/execution-failure world "Acquisition task stopped; see controller events"))
          episode (if (.exists (io/file task-root "episodes/learning.edn"))
                    (u/read-file (io/file task-root "episodes/learning.edn"))
                    (records/save-episode! task-root "learning" world run
                    {:arm (name arm) :artifact (:hash policy) :workflow (:hash active)
                     :wall-ms (/ (- (System/nanoTime) begin) 1000000.0) :provenance provenance
                     :usage {:spent (:spent ledger) :reserved (:reserved ledger)}}))
          result {:arm arm :index index :root task-root :id run-id :status (:status ledger)
                  :config config :initial (:hash workflow) :active (:hash active) :episode episode
                  :spent (:spent ledger) :reserved (:reserved ledger) :promotions (:promotions ledger)
                  :model-identifiers (vec (set (keep #(get-in % [:response :model]) (vals (:provider-requests ledger)))))}]
      (records/write-events! (str task-root "/events.jsonl") (:events ledger))
      (u/write-edn! (str task-root "/checkpoint.edn") result)
      result)))

(defn acquisition-task!
  "Both conditions use this identical task runner. Retention is outside its broker."
  [{:keys [root id config provider execute provenance]} arm index world development workflow library-root]
  (let [task-id (str (name arm) "-" index) task-root (str root "/tasks/" task-id)
        store (str task-root "/controller.sqlite") run-id (str id "-" task-id) session "root"
        begin (System/nanoTime) policy-hash (get-in workflow [:forms :strategy :policy])]
    (copy-library! library-root task-root workflow)
    (c/create-run! store run-id config (:hash workflow))
    (try
      (let [before (development-panel! store run-id task-root policy-hash development execute)
            observation (sim/observe (sim/initial-state world) nil)]
        (doseq [[handle data] [["jobs" (:jobs observation)] ["workers" (:workers observation)]
                              ["observation" [observation]] ["artifacts" (conj (dependency-closure task-root workflow) workflow)]
                              ["development" before]]]
          (c/put-context! store run-id handle data))
        (c/session! store run-id session nil)
        (let [env {:store store :run run-id :registry task-root :provider provider :workers (atom {})
                   :allow-learning true :provenance provenance
                   :development-evaluator (fn [hash] {:cases (development-panel! store run-id task-root hash development execute)})}
              selected (runtime/workflow! store run-id workflow "jobs"
                         (fn [task context] (runtime/broker! env session {:op :agent/call :id "analyst" :task task :context context})))
              result (runtime/run-session! env session
                       {:task "Investigate the bottleneck. Use code-selected evidence and a child call. Propose a reusable policy and a workflow that uses it. You may also choose temporary code for this task."
                        :workflow-result selected :active-workflow (:hash workflow)
                        :context-handles ["jobs" "workers" "observation" "artifacts" "development" "trace-index"]})]
          (u/ensure! (not (:error result)) "Acquisition session failed" result))
        ;; The fixed controller alone decides. Both arms may use approved code
        ;; within this task. Only the paired runner can carry it to the next task.
        (doseq [event (:events (c/get-run store run-id)) :when (= :artifact-staged (:type event))
                :let [candidate (a/load! task-root (get-in event [:payload :hash]))]
                :when (= :workflow (:category candidate))]
          (if (= (:parent candidate) (:active (c/get-run store run-id)))
            (let [after (development-panel! store run-id task-root (get-in candidate [:forms :strategy :policy]) development execute)
                  current (if (= (:parent candidate) (:hash workflow)) before
                            (development-panel! store run-id task-root
                              (get-in (a/load! task-root (:parent candidate)) [:forms :strategy :policy]) development execute))]
              (a/promote! store run-id task-root candidate (a/promotion-evidence current after (:promotion config))))
            (c/update-run! store run-id #(c/event % :candidate-stale {:artifact (:hash candidate) :parent (:parent candidate) :active (:active %)}))))
        (c/update-run! store run-id #(assoc % :status :complete)))
      (catch Exception e
        (c/update-run! store run-id #(-> % (assoc :status :checkpointed)
                                        (c/event :run-stopped {:reason (.getMessage e) :data (ex-data e)})))))
    (finish-task! {:config config :provenance provenance :execute execute} arm index world workflow task-root run-id begin)))

(defn recorded-or-new-task! [env arm index world development workflow]
  (let [task-root (str (:root env) "/tasks/" (name arm) "-" index)
        checkpoint (io/file task-root "checkpoint.edn") store (str task-root "/controller.sqlite")
        run-id (str (:id env) "-" (name arm) "-" index)]
    (cond
      (.exists checkpoint)
      (let [saved (u/read-file checkpoint)]
        (u/ensure! (and (= (:config env) (:config saved)) (= (:hash workflow) (:initial saved))
                        (= world (get-in saved [:episode :world]))) "Checkpoint configuration mismatch" {})
        saved)
      (.exists (io/file store))
      (let [ledger (c/get-run store run-id)]
        (u/ensure! (and (= (:config env) (:config ledger)) (= (:hash workflow) (:initial-artifact ledger)))
                   "Interrupted task configuration mismatch" {})
        (c/recover! store run-id)
        (doseq [[session item] (:sessions ledger) :when (not (c/terminal-statuses (:status item)))]
          (c/finish-session! store run-id session :cancelled {:reason "Controller process restarted; no provider retry"}))
        (c/update-run! store run-id #(-> % (dissoc :episode) (assoc :status :checkpointed)
                                        (c/event :run-stopped {:reason "Interrupted task retained as failure; pending provider charges remain reserved"})))
        (finish-task! env arm index world workflow task-root run-id (System/nanoTime)))
      :else (acquisition-task! env arm index world development workflow (:root env)))))

(defn paired-acquisition-unlocked!
  [{:keys [root config provenance] :as env} learning development]
  (u/ensure! (seq learning) "Learning panel is empty" {})
  (doseq [artifact [f/initial-policy f/initial-workflow]] (a/save! root artifact))
  (loop [index 0 active f/initial-workflow tasks []]
    (if (= index (count learning))
      (let [spent (reduce #(merge-with + %1 (:spent %2)) {} tasks)
            reserved (reduce #(merge-with + %1 (:reserved %2)) {} tasks)
            report {:active (:hash active) :tasks tasks :spent spent :reserved reserved
                    :status (if (every? #(= :complete (:status %)) tasks) :complete :checkpointed)
                    :conditions (into {} (for [arm [:frozen :evolving]]
                                           [arm (experiment/summarize (mapv :episode (filter #(= arm (:arm %)) tasks)))]))}]
        (u/write-edn! (str root "/checkpoint.edn") report) report)
      (let [_ (when-let [snapshot (:source-snapshot env)] (experiment/assert-frozen-source! snapshot))
            arms (if (even? index) [:frozen :evolving] [:evolving :frozen])
            next-tasks (mapv (fn [arm]
                              (recorded-or-new-task! env arm index (nth learning index) development
                                                     (if (= arm :frozen) f/initial-workflow active))) arms)
            evolved (first (filter #(= :evolving (:arm %)) next-tasks))
            next-active (a/load! (:root evolved) (:active evolved))]
        (copy-library! (:root evolved) root next-active)
        (u/write-edn! (str root "/acquisition-progress.edn")
                      {:completed-pairs (inc index) :active (:hash next-active) :tasks (into tasks next-tasks)
                       :provenance provenance :per-task-config config})
        (recur (inc index) next-active (into tasks next-tasks))))))

(defn paired-acquisition! [{:keys [root] :as env} learning development]
  (.mkdirs (io/file root))
  (with-open [file (java.io.RandomAccessFile. (str root "/acquisition.lock") "rw")
              channel (.getChannel file)]
    (let [lock (.tryLock channel)]
      (u/ensure! lock "Acquisition is already running" {})
      (try
        (doseq [seal ["final-evaluation-seal.edn" "cold-evaluation-seal.edn"]]
          (u/ensure! (not (.exists (io/file root seal))) "Cannot resume acquisition after a final split was reserved" {}))
        (paired-acquisition-unlocked! env learning development)
        (finally (.release lock))))))

(defn complete-acquisition! [id root config p snapshot {:keys [learning development]}]
(let [result (paired-acquisition! {:root root :id id :config config :provider p :execute run-policy!
                                         :provenance :recorded-model-run :source-snapshot snapshot} learning development)
            export-path (str root "/export")
            _ (experiment/assert-frozen-source! snapshot)
            export (if (.exists (io/file export-path))
                     (let [loaded (bundle/load-bundle export-path)]
                       (u/ensure! (= (:active result) (get-in loaded [:manifest :active])) "Existing export does not match checkpoint" {})
                       (:manifest loaded))
                     (bundle/export! root export-path (:active result) :recorded-model-run))
            events (mapcat (fn [task]
                             (map #(assoc % :task (:id task) :arm (:arm task))
                                  (:events (c/get-run (str (:root task) "/controller.sqlite") (:id task))))) (:tasks result))
            report (assoc result :run-id id :provenance :recorded-model-run :label "RECORDED MODEL RUN"
                          :mode :paired-acquisition :manifest snapshot :bundle export
                          :raw-cases (mapv :episode (:tasks result))
                          :costs {:acquisition {:spent (:spent result) :reserved-unknown (:reserved result)}
                                  :usd-basis (get snapshot :usd-basis :operator-supplied-token-rates) :invoiced-usd nil :compute-efficiency-claim false}
                          :claims {:H1 :untested :H2 :untested :H3 :out-of-scope
                                   :note "Acquisition is development evidence. Sealed evaluation is required."})]
        (u/write-edn! (str root "/manifest.edn")
                      (assoc-in snapshot [:model :returned-identifiers] (set (mapcat :model-identifiers (:tasks result)))))
        (records/write-events! (str root "/events.jsonl") events)
        (u/write-edn! (str root "/report.edn") report) (u/write-json! (str root "/report.json") report)
        (u/atomic-write! "var/latest-run" id)
        {:run-id id :path root :export export-path :status (:status result)
         :conditions (:conditions result) :spent (:spent result) :reserved (:reserved result)}))

(defn evolve! [env]
  (let [{:keys [model cap input-rate output-rate api-key] :as options} (options env)
        isolation (iso/require-tested!)]
    (u/ensure! (:ready isolation) "Live evolution requires verified isolated SCI execution" isolation)
    (let [prepared (prepare-provider! options)
          id (str "model-" (System/currentTimeMillis)) root (str "var/runs/" id) store (str root "/controller.sqlite")
          seed (.nextInt (java.security.SecureRandom.) 1000000000)
          learning (mapv #(w/generate (+ seed %) {}) (range 3))
          development (mapv #(w/generate (+ seed %) {}) (range 100 106))
          final (vec (concat (map #(w/generate (+ seed %) {}) (range 200 206))
                             [(w/generate (+ seed 300) {:size 24 :structure :fanout :fault-count 3 :resource-mix true})
                              (w/generate (+ seed 301) {:size 24 :structure :chain :fault-count 3 :resource-mix true})]))
          coldboot (vec (concat (map #(w/generate (+ seed %) {}) (range 400 406))
                                [(w/generate (+ seed 500) {:size 30 :structure :independent :fault-count 4 :resource-mix true})
                                 (w/generate (+ seed 501) {:size 30 :structure :fanout :fault-count 4 :resource-mix true})]))
          config (-> (u/read-file "config/experiment.edn")
                     (assoc :mode :live :provenance :recorded-model-run
                            :split-version (u/hash-value [learning development final coldboot]))
                     ;; Non-transferable equal task allowances bound the sum of
                     ;; spent plus uncertain reservations across both conditions.
                     (assoc-in [:limits :usd] (/ cap (* 2 (count learning))))
                     ;; Real-worker rehearsal used ~109 s for validation alone.
                     ;; Pre-register five minutes for both acquisition arms;
                     ;; individual SCI expression/session limits stay unchanged.
                     (assoc-in [:limits :wall-ms] 300000)
                     (provider-scope options))
          p (:adapter prepared)
          snapshot (assoc (experiment/manifest config)
                          :acquisition-design {:arms [:frozen :evolving] :tasks-per-arm (count learning)
                                               :total-usd-cap cap :budget-scope :per-task-shared-with-children
                                               :retention :approved-executables-only}
                          :model (:model prepared) :transport (:transport prepared) :usd-basis (:usd-basis prepared)
                          :isolation isolation)]
      (u/write-edn! (str root "/manifest.edn") snapshot)
      ;; Controller-only file; never sent through the capability broker or mounted.
      (u/write-edn! (str root "/sealed-splits.edn") {:learning learning :development development :final final :coldboot coldboot})
      (complete-acquisition! id root config p snapshot {:learning learning :development development}))))

(defn resume! [root env]
  (let [{:keys [model cap input-rate output-rate] :as options} (options env)
        snapshot (u/read-file (io/file root "manifest.edn"))
        splits (u/read-file (io/file root "sealed-splits.edn"))
        check (iso/require-tested!)
        prepared (prepare-provider! options)]
    (u/ensure! (:ready check) "Resume requires verified isolation" {})
    (u/ensure! (= [model cap input-rate output-rate (:image check)]
                   [(get-in snapshot [:model :requested]) (get-in snapshot [:acquisition-design :total-usd-cap])
                    (get-in snapshot [:model :input-usd-per-m]) (get-in snapshot [:model :output-usd-per-m])
                    (get-in snapshot [:isolation :image])]) "Resume must use the original model, total cap, rates, and worker image" {})
    (u/ensure! (= [(get-in prepared [:model :provider]) (get-in prepared [:transport :cli_sha256])]
                   [(get-in snapshot [:model :provider]) (get-in snapshot [:transport :cli_sha256])])
               "Resume provider or CLI differs from acquisition" {})
    (experiment/assert-frozen-source! snapshot)
    (u/ensure! (= (get-in snapshot [:config :split-version])
                   (u/hash-value [(:learning splits) (:development splits) (:final splits) (:coldboot splits)]))
               "Sealed split digest mismatch" {})
    (complete-acquisition! (.getName (io/file root)) root (:config snapshot)
                          (:adapter prepared) snapshot splits)))
