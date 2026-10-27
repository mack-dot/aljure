(ns repl-lab.selector-acquisition
  "Versioned selector acquisition on the existing runtime. No implicit live authorization."
  (:require [clojure.java.io :as io] [repl-lab.util :as u] [repl-lab.artifact :as a]
            [repl-lab.selector-tasks :as tasks] [repl-lab.selector-gate :as gate]
            [repl-lab.selector-accounting :as accounting] [repl-lab.controller :as c]
            [repl-lab.runtime :as runtime] [repl-lab.provider :as provider]
            [repl-lab.execution :as execution] [repl-lab.executable :as executable]
            [repl-lab.limits :as limits] [repl-lab.sim :as sim] [repl-lab.live :as live]
            [repl-lab.experiment :as experiment] [repl-lab.bundle :as bundle]
            [repl-lab.evaluation :as evaluation] [repl-lab.isolation :as isolation]
            [repl-lab.policy-diagnostic :as diagnostic]))

(def proposal-path "config/selector-acquisition-v1.edn")
(defn instructions
  ([] (instructions :author))
  ([role] (str (slurp "resources/base-instructions.txt") "\n"
               (slurp (if (= :author role) "resources/selector-acquisition-v1.txt" "resources/selector-routes-v1.txt")))))

(defn config [proposal mode kind]
  (-> (u/read-file "config/experiment.edn")
      (assoc :mode mode :execution-language :clojure :selector-gate-version 2
             :selector-role kind
             :amortization-tasks (:amortization-tasks proposal)
             :subscription-scope :learning-evaluation)
      (update :limits merge (get proposal (if (= :author kind) :acquisition-limits :task-limits)))))

(defn validate-proposal! [proposal]
  (u/ensure! (= [tasks/version "claude-sonnet-5-5" :claude-code-subscription {:input 2.0 :output 10.0} 2048]
                 ((juxt :version :model :provider :rates :max-output-tokens) proposal))
             "Selector provider contract differs; no transport/model fallback" {})
  (u/ensure! (and (= #{:acquisition :heldout :coldboot} (set (keys (:phase-caps proposal))))
                  (every? #(and (accounting/finite-nonnegative? %) (pos? %)) (vals (:phase-caps proposal)))
                  (<= (reduce + (vals (:phase-caps proposal))) (:global-cap proposal))
                  (= 0 (:retries proposal))) "Invalid campaign caps or retry policy" {})
  proposal)

(defn plan! [root]
  (u/ensure! (not (.exists (io/file root))) "Plan destination already exists" {})
  (let [proposal (validate-proposal! (u/read-file proposal-path))
        isolation-proof (isolation/require-tested!)
        random (java.security.SecureRandom.)
        seeds (vec (take (reduce + (map count (vals tasks/profiles)))
                         (distinct (repeatedly #(.nextInt random Integer/MAX_VALUE)))))
        splits (tasks/generate-splits seeds) library (tasks/library)
        plan {:version tasks/version :status :NOT-AUTHORIZED :proposal proposal
              :source (experiment/manifest proposal)
              :prompt-hashes {:author (u/sha (instructions :author)) :task (u/sha (instructions :task))}
              :library-hash (:hash library) :splits-hash (u/hash-value splits)
              :worker-image (:image isolation-proof) :isolation-proof-hash (u/sha (slurp "var/isolation-proof.json"))
              :case-hashes (into {} (map (fn [[phase worlds]] [phase (mapv u/hash-value worlds)]) splits))
              :conditions (conj (:controls proposal) :model-authored-selection)
              :no-retries true :inference-dispatched false}
        plan (assoc plan :plan-hash (u/hash-value plan))]
    ;; Hidden worlds stay in controller storage. Workers receive observations only.
    (u/write-edn! (str root "/sealed-splits.edn") splits)
    (java.nio.file.Files/setPosixFilePermissions (.toPath (io/file root "sealed-splits.edn"))
      (java.nio.file.attribute.PosixFilePermissions/fromString "rw-------"))
    (u/write-edn! (str root "/plan.edn") plan)
    plan))

(defn load-plan! [root]
  (let [plan (u/read-file (str root "/plan.edn")) splits (u/read-file (str root "/sealed-splits.edn"))]
    (u/ensure! (= (:plan-hash plan) (u/hash-value (dissoc plan :plan-hash))) "Plan hash differs" {})
    (u/ensure! (= (:splits-hash plan) (u/hash-value splits)) "Sealed splits changed" {})
    (experiment/assert-frozen-source! (:source plan))
    (u/ensure! (= (:library-hash plan) (:hash (tasks/library))) "Initial library changed" {})
    (u/ensure! (= (:isolation-proof-hash plan) (u/sha (slurp "var/isolation-proof.json"))) "Frozen isolation evidence changed" {})
    (assoc plan :splits splits)))

(defn authorize! [plan env]
  (u/ensure! (and (= "1" (get env "LIVE"))
                  (= (:plan-hash plan) (get env "SELECTOR_APPROVED_PLAN"))
                  (= "claude-sonnet-5-5" (get env "MODEL"))
                  (= "claude-subscription" (get env "INFERENCE_PROVIDER"))
                  (= (get-in plan [:proposal :global-cap]) (live/positive-number (get env "MAX_USD") "MAX_USD")))
             "Separate operator authorization of this selector plan, transport and all caps is required" {})
  true)

(defn install! [root library]
  (doseq [artifact (conj (:artifacts library) (:workflow library))] (a/save! root artifact)))

(defn phase! [root proposal mode phase delegate]
  (let [cfg (-> (config proposal mode :author)
                (assoc-in [:limits :calls] 10000) (assoc-in [:limits :tokens] 100000000)
                (assoc-in [:limits :wall-ms] 7200000)
                (assoc-in [:limits :usd] (get-in proposal [:phase-caps phase])))
        store (str root "/" (name phase) "-accounting.sqlite") id (name phase)]
    (validate-proposal! proposal)
    (c/create-run! store id cfg nil) (c/session! store id "accounting" nil)
    {:store store :run id :provider (accounting/->PhaseProvider delegate store id (:max-output-tokens proposal))}))

(defn context! [root cfg library p]
  (let [ctx {:store (str root "/session.sqlite") :run "task" :registry (str root "/registry")
             :provider p :workers (atom {}) :allow-learning true
             :provenance (if (= :live (:mode cfg)) :recorded-model-run :synthetic-fixture)
             :base-instructions (instructions (:selector-role cfg)) :root root}]
    (install! (:registry ctx) library)
    (c/create-run! (:store ctx) (:run ctx) cfg (:hash (:workflow library)))
    ctx))

(defn ledger [ctx] (assoc (c/get-run (:store ctx) (:run ctx)) :accounting-store (:store ctx)))
(defn session! [ctx id task]
  (c/session! (:store ctx) (:run ctx) id nil)
  (runtime/run-session! ctx id task))

(defn public-context! [ctx public]
  (c/put-context! (:store ctx) (:run ctx) "observation" [(:observation public)])
  (c/put-context! (:store ctx) (:run ctx) "skills" (:skills public)))

(def initialize-invocations "(do (def selector-invocations (atom {})) nil)")
(def read-invocations "(deref selector-invocations)")
(defn instrument-source [item]
  (let [name (get-in item [:interface :name]) hash (:hash item)]
    (str "(do (def " name " (let [original " name "] (fn [& args] "
         "(swap! selector-invocations update " (pr-str hash) " (fnil inc 0)) (apply original args)))) nil)")))

(defn isolated-policy! [registry target world options]
  (let [backend (execution/backend :clojure) worker (atom nil) phase (atom :startup)
        invocations (atom {}) stages (atom []) failure (atom nil) cleanup (atom nil) episode (atom nil)
        begin (System/nanoTime) elapsed #(/ (- (System/nanoTime) begin) 1e6)
        result (try
                 (execution/require-tested! :clojure)
                 (reset! worker (execution/open! backend (:deadline-ms options)))
                 (u/ensure! (= 42 (execution/evaluate! backend @worker "(+ 20 22)" {})) "Worker readiness failed" {})
                 (swap! stages conj {:phase :ready :elapsed-ms (elapsed)})
                 (reset! phase :code-loading)
                 (let [dependencies (a/dependency-closure registry target)]
                   (executable/load! backend @worker target dependencies)
                   ;; Same instrumentation for every condition. Count actual calls,
                   ;; including each component inside the reviewed composition.
                   (reset! phase :instrumentation)
                   (execution/evaluate! backend @worker initialize-invocations {})
                   (doseq [item (conj (vec dependencies) target)]
                     (execution/evaluate! backend @worker (instrument-source item) {}))
                   (swap! stages conj {:phase :loaded :elapsed-ms (elapsed)})
                   (reset! phase :execution)
                   (let [result (sim/run-episode world
                                   (fn [observation memory]
                                     (try (executable/call! backend @worker target [observation memory])
                                          (catch Exception e (reset! failure (diagnostic/exception-data e)) (throw e)))) options)]
                     (reset! episode result)
                     (reset! phase :instrumentation)
                     (reset! invocations (execution/evaluate! backend @worker read-invocations {}))
                     (reset! phase :execution)
                     result))
                 (catch Exception e (reset! failure (diagnostic/exception-data e))
                   (or @episode (sim/execution-failure world (.getMessage e))))
                 (finally
                   (when @worker (try (execution/close! backend @worker)
                                      (catch Exception e (reset! cleanup (.getMessage e)))))
                   (swap! stages conj {:phase :cleanup :elapsed-ms (elapsed)})))
        failure-stage (cond @cleanup :cleanup @failure @phase
                            (= :wall-budget (get-in result [:metrics :status])) :execution
                            (not= :complete (get-in result [:metrics :status])) :algorithm)]
    {:episode result :failure-stage failure-stage
     :failure-kind (cond @cleanup :cleanup @failure (diagnostic/error-kind @failure)
                         failure-stage :algorithm-or-contract)
     :error @failure :cleanup-error @cleanup
     :invocations @invocations :stages @stages :wall-ms (elapsed) :artifact (:hash target)}))

(defn resolve-policy! [ctx library decision public]
  (gate/decision! decision (set (map :version-hash (:registry library))) 2)
  (let [route (:route decision)
        generated (fn [session-id]
                    (let [target (get-in (ledger ctx) [:sessions session-id :temporary-policy])]
                      (u/ensure! target "Route did not produce a task-local executable policy" {}) target))
        task {:task "Produce a task-local scheduling function via :policy/use, then :done. Do not claim it was retained."
              :route route :input public :context-handles ["observation" "skills"]}
        target (case route
                 :reuse (a/load! (:registry ctx) (:hash decision))
                 :compute (a/load! (:registry ctx) (:compute library))
                 :compose (tasks/composed library (:hashes decision))
                 (:adapt :synthesize) (do (session! ctx "generation" task) (generated "generation"))
                 :delegate (do (c/session! (:store ctx) (:run ctx) "delegator" nil)
                               (runtime/broker! ctx "delegator"
                                 {:op :agent/call :id "policy-child" :task (:task task) :context public})
                               (c/finish-session! (:store ctx) (:run ctx) "delegator" :complete {:delegated true})
                               (generated "policy-child")))]
    (u/ensure! (and (= :policy (:category target)) (= 2 (get-in target [:interface :arity])))
               "Route must produce an approved or task-local policy" {})
    (a/save! (:registry ctx) target) target))

(defn execute!
  ([root proposal mode library p world decision-fn]
   (execute! root proposal mode library p world decision-fn nil))
  ([root proposal mode library p world decision-fn deadline]
  (let [cfg (cond-> (config proposal mode :task)
              deadline (assoc-in [:limits :wall-ms] (max 1 (min (get-in proposal [:task-limits :wall-ms])
                                                               (- deadline (limits/now-ms))))))
        ctx (context! root cfg library p)
        public (gate/public-input world (:registry library)) _ (public-context! ctx public)
        decision (atom nil)
        row (try
              (when deadline (limits/timeout-ms deadline 1))
              (reset! decision (decision-fn ctx public))
              (let [target (resolve-policy! ctx library @decision public)]
                (isolated-policy! (:registry ctx) target world (limits/from-run (ledger ctx))))
              (catch Exception e {:episode (sim/execution-failure world (.getMessage e))
                                  :failure-stage :route-generation :error (.getMessage e) :invocations {}}))
        row (assoc row :decision @decision :ledger (ledger ctx) :evidence-root root)]
    (u/write-edn! (str root "/result.edn") row)
    row)))

(defn directed! [ctx public]
  (let [result (session! ctx "selection"
                 {:task "Choose one route. Return its exact EDN decision map as the :done :summary string."
                  :input public :context-handles ["observation" "skills"]})]
    (u/ensure! (string? (:summary result)) "No route-selection result" {})
    (u/read-edn (:summary result))))

(defn control [library name]
  (case name
    :deterministic-reuse (fn [_ _] {:route :reuse :hash (:retained library)})
    :descriptive-discovery directed!
    :fresh-synthesis (fn [_ _] {:route :synthesize})
    :always-compose (fn [_ _] {:route :compose :hashes [(:rank library) (:pack library)]})
    :applicability-guard (fn [_ public] (tasks/guard library public))))

(defn validate-candidate! [root proposal mode library p author-ctx worlds candidate prior-ledgers]
  (let [counter (atom 0)
        author-deadline (:deadline-ms (limits/from-run (ledger author-ctx)))
        run-route (fn [world choose task-deadline]
                    (execute! (str root "/route-" (swap! counter inc)) proposal mode library p world choose
                              (min author-deadline task-deadline)))
        cfg (assoc (config proposal mode :task) :development-case-hashes (mapv u/hash-value worlds)
                   :acquisition-deadline-ms author-deadline)
        receipt (gate/adjudicate!
                  {:root (:registry author-ctx) :candidate candidate :mode mode :config cfg
                   :authoring-ledger (ledger author-ctx) :acquisition-ledgers prior-ledgers
                   :development-worlds worlds :registry (:registry library)
                   :execute-route (fn [decision world options] (run-route world (fn [_ _] decision) (:deadline-ms options)))
                   :control-executors (into {} (for [name (:controls proposal)]
                                               [name (fn [_ world options] (run-route world (control library name) (:deadline-ms options)))]))})]
    (u/write-edn! (str root "/decision.edn") receipt)
    {:receipt receipt
     :ledgers (mapv #(-> (u/read-file (str root "/route-" % "/result.edn")) :ledger) (range 1 (inc @counter)))}))

(defn promote! [root library candidate receipt author-ledger]
  ;; Called only at a terminal authoring boundary. The model has no promotion tool.
  (u/ensure! (and (= :accepted (:status receipt)) (= :LIVE-MODEL-DEVELOPMENT (:evidence-category receipt))
                  (= (:hash candidate) (:candidate receipt)) (gate/authored? candidate author-ledger)
                  (= (:evidence-hash receipt) (u/hash-value (dissoc receipt :evidence-hash)))
                  (every? #(c/terminal-statuses (:status %)) (vals (:sessions author-ledger))))
             "Independent live acceptance and a terminal authoring session are required" {})
  (accounting/usage! author-ledger)
  (let [workflow (a/make-artifact
                   (-> (:workflow library) (select-keys [:category :interface :source :dependencies :provenance])
                       (update :dependencies conj (:hash candidate))
                       (assoc :parent nil :author "independent-selector-controller")))]
    (install! (str root "/approved") library)
    (a/save! (str root "/approved") candidate) (a/save! (str root "/approved") workflow)
    (let [manifest (bundle/export! (str root "/approved") (str root "/executable-library") (:hash workflow) :recorded-model-run)
          promotion {:candidate (:hash candidate) :receipt-hash (:evidence-hash receipt)
                     :bundle-hash (u/hash-value manifest) :selector-source-hash (u/sha (:source candidate))
                     :inspection-required (:audit manifest) :export-claim :executable-retention-only}]
      (u/write-edn! (str root "/promotion.edn") promotion) promotion)))

(defn acquire! [root plan mode delegate]
  (let [proposal (:proposal plan) library (tasks/library)
        phase (phase! root proposal mode :acquisition delegate)
        ctx (context! (str root "/author") (config proposal mode :author) library (:provider phase))
        prior (atom []) decisions (atom []) calls (atom 0)
        evaluate (fn [hash]
                   (u/ensure! (< @calls (:max-candidates proposal)) "Candidate evaluation limit reached" {})
                   (let [candidate (a/load! (:registry ctx) hash)
                         result (validate-candidate! (str root "/candidate-" (swap! calls inc)) proposal mode library
                                  (:provider phase) ctx (get-in plan [:splits :development]) candidate @prior)]
                     (swap! prior into (:ledgers result)) (swap! decisions conj [candidate (:receipt result)])
                     (:receipt result)))
        ctx (assoc ctx :development-evaluator evaluate)
        learning (mapv #(gate/public-input % (:registry library)) (get-in plan [:splits :learning]))]
    (c/put-context! (:store ctx) (:run ctx) "learning" learning)
    (c/put-context! (:store ctx) (:run ctx) "development"
                    (mapv #(gate/public-input % (:registry library)) (get-in plan [:splits :development])))
    (c/put-context! (:store ctx) (:run ctx) "skills" (:registry library))
    (let [result (session! ctx "author"
                   {:task "Investigate the available computations and propose an executable route selector. Request development evaluation."
                    :context-handles ["learning" "development" "skills"] :skills (:registry library)})
          author-ledger (ledger ctx)
          phase-ledger (ledger phase)
          complete-usage (try (accounting/reconcile-phase! phase-ledger (conj @prior author-ledger))
                              (catch Exception e {:error (.getMessage e)}))
          decisions (mapv (fn [[candidate receipt]]
                            (if (and (not (:error complete-usage)) (:acquisition-usd receipt))
                              [candidate (gate/finalize-acquisition receipt (:usd complete-usage))]
                              [candidate receipt])) @decisions)
          _ (u/write-edn! (str root "/final-decisions.edn") decisions)
          accepted (first (filter #(= :accepted (get-in % [1 :status])) decisions))
          promotion (when (and accepted (not (:error complete-usage)))
                      (promote! root library (first accepted) (second accepted) author-ledger))
          report {:version tasks/version :evidence-category (if (= mode :fixture) :FIXTURE :LIVE-MODEL-RUN)
                  :plan-hash (:plan-hash plan) :process-id (.pid (java.lang.ProcessHandle/current))
                  :result result :usage complete-usage :phase-ledger phase-ledger
                  :authoring-ledger author-ledger :candidates (mapv #(select-keys (second %) [:candidate :status :evidence-hash]) decisions)
                  :staged-artifacts (mapv :payload (filter #(= :artifact-staged (:type %)) (:events author-ledger)))
                  :promotion promotion :heldout :NOT-RUN :coldboot :NOT-RUN :harness-improvement :UNPROVEN}]
      (u/write-edn! (str root "/acquisition.edn") report)
      ;; A later cold controller reads only this receipt and executable code,
      ;; never the acquisition ledger/transcripts just to recover scalar costs.
      (u/write-edn! (str root "/transfer-manifest.edn")
                    {:plan-hash (:plan-hash plan) :process-id (:process-id report)
                     :acquisition-usd (:usd complete-usage) :promotion promotion})
      report)))

(defn cold-library [path original-library selector-hash]
  (let [loaded (bundle/load-bundle path) restored (evaluation/restore-library loaded)
        by-original (:by-original restored) selector (get by-original selector-hash)]
    (u/ensure! selector "Selector absent from executable export" {})
    ;; The initial tools are controller-authored constants, with no conversation
    ;; state. Check every form against the whitelist export before restoring their
    ;; public identities. This preserves hashes embedded in the learned selector
    ;; without rewriting its source. Only its fresh envelope changes identity.
    (doseq [artifact (:artifacts original-library)]
      (u/ensure! (= (select-keys artifact [:category :forms :interface :dependencies])
                     (select-keys (get-in loaded [:artifacts (:hash artifact)]) [:category :forms :interface :dependencies]))
                 "Approved initial capability changed across export" {}))
    {:selector selector :library original-library :bundle-hash (u/hash-value (:manifest loaded))}))

(defn usage-status [value]
  (try (assoc (accounting/usage! value) :status :complete)
       (catch Exception e
         {:status :unresolved :error (.getMessage e) :usd nil
          :known-usd (reduce + 0.0 (keep (fn [[_ request]]
                                         (let [usd (get-in request [:response :usd])]
                                           (when (and (= :complete (:status request)) (accounting/finite-nonnegative? usd)) usd)))
                                       (:provider-requests value)))
          :unresolved-reservations (:reserved value)})))

(defn transfer-summary [rows acquisition-usd]
  (into {} (for [[condition group] (group-by :condition rows)]
             (let [verified (count (filter #(and (= :scored (:outcome %)) (= :complete (get-in % [:metrics :status]))) group))
                   accounted? (every? #(or (= :not-dispatched (:outcome %)) (= :complete (get-in % [:usage :status]))) group)
                   inference (when accounted? (reduce + 0.0 (keep :usd group)))
                   acquisition (if (= :model-authored-selection condition) acquisition-usd 0.0)
                   total (when inference (+ acquisition inference))]
               [condition {:planned (count group) :attempted (count (remove #(= :not-dispatched (:outcome %)) group))
                           :verified-complete verified :paired-success-rate (/ verified (count group))
                           :model-cost-usd-equivalent inference :acquisition-usd-equivalent acquisition
                           :inference-calls (when accounted? (reduce + 0 (keep #(get-in % [:usage :calls]) group)))
                           :input-tokens (when accounted? (reduce + 0 (keep #(get-in % [:usage :input-tokens]) group)))
                           :output-tokens (when accounted? (reduce + 0 (keep #(get-in % [:usage :output-tokens]) group)))
                           :simulated-makespans (mapv #(get-in % [:metrics :makespan]) group)
                           :artifact-invocations (apply merge-with + {} (keep :invocations group))
                           :total-usd-equivalent total
                           :measured-usd-per-planned-task (when total (/ total (count group)))
                           :measured-usd-per-verified-solution (when (and total (pos? verified)) (/ total verified))
                           :infrastructure-failures (count (filter gate/infrastructure-failure? group))
                           :algorithm-failures (count (filter #(and (:failure-stage %) (not (gate/infrastructure-failure? %))) group))
                           :unattempted (count (filter #(= :not-dispatched (:outcome %)) group))}]))))

(defn transfer! [root plan mode delegate phase library selector acquisition-usd]
  (u/ensure! (#{:heldout :coldboot} phase) "Unknown transfer split" {})
  (let [proposal (:proposal plan) account (phase! root proposal mode phase delegate)
        worlds (get-in plan [:splits phase])
        conditions (cond-> (conj (:controls proposal) :model-authored-selection)
                     (= phase :coldboot) (conj :selector-removed))
        slots (vec (for [[index world] (map-indexed vector worlds) condition conditions]
                     {:condition condition :case-index index :case (u/hash-value world)}))
        _ (u/write-edn! (str root "/planned-slots.edn") {:slots slots :stop-on (:stop-on proposal) :retries 0})
        task-ledgers (atom []) stopped (atom nil)
        rows (mapv
               (fn [{:keys [case-index condition] :as slot}]
                 (if @stopped
                   (assoc slot :outcome :not-dispatched :reason @stopped :usd nil)
                   (let [world (nth worlds case-index) directory (str root "/" case-index "-" (name condition))
                         choose (if (= condition :model-authored-selection)
                                  (fn [ctx public]
                                    (a/save! (:registry ctx) selector)
                                    (executable/invoke! (:registry ctx) selector [public]
                                                        (:deadline-ms (limits/from-run (ledger ctx)))))
                                  (control library (if (= condition :selector-removed) :applicability-guard condition)))
                         result (try
                                  (let [row (execute! directory proposal mode library (:provider account) world choose)]
                                    (swap! task-ledgers conj (:ledger row))
                                    (merge slot (gate/verified-row! world row 2)
                                           {:outcome :scored :trace (str directory "/result.edn")
                                            :usage (usage-status (:ledger row)) :wall-ms (:wall-ms row)}))
                                  (catch Exception e
                                    (merge slot {:outcome :unverified :failure-stage :verification-or-accounting
                                                 :failure-kind :unresolved :error (.getMessage e) :usd nil
                                                 :trace (str directory "/result.edn")
                                                 :usage {:status :unresolved}})))]
                     (when (or (gate/infrastructure-failure? result) (not= :complete (get-in result [:usage :status])))
                       (reset! stopped (select-keys result [:condition :case-index :failure-stage :failure-kind :error])))
                     (u/write-edn! (str directory "/verified.edn") result)
                     result))) slots)
        phase-usage (usage-status (ledger account))
        reconciliation (try (accounting/reconcile-phase! (ledger account) @task-ledgers) :matched
                            (catch Exception e {:error (.getMessage e)}))
        report {:version tasks/version :phase phase :evidence-category (if (= :fixture mode) :FIXTURE :HELD-OUT-EXPERIMENT)
                :plan-hash (:plan-hash plan) :process-id (.pid (java.lang.ProcessHandle/current))
                :rows rows :summary (transfer-summary rows acquisition-usd) :usage phase-usage
                :stopped @stopped :reconciliation reconciliation :planned-slots (count slots)
                :ledger (ledger account) :local-compute-price :UNKNOWN
                :cost-note "Acquisition is shown in each independent panel; do not add it twice across panels. No assumed future successes."
                :ablation-note "Selector removal uses the strong deterministic applicability guard with the same approved capabilities."
                :harness-improvement :REQUIRES-INDEPENDENT-INTERPRETATION}]
    (u/write-edn! (str root "/transfer.edn") report) report))

(defn preflight! [plan]
  (validate-proposal! (:proposal plan))
  (experiment/assert-frozen-source! (:source plan))
  (u/ensure! (= (:worker-image plan) (:image (isolation/require-tested!))) "Worker image differs from frozen plan" {})
  ;; prepare-provider! performs a local subscription contract/auth-status check,
  ;; never a model call. The adapter is not invoked by this function.
  (let [prepared (live/prepare-provider! {:model "claude-sonnet-5-5" :provider :claude-code-subscription
                                        :input-rate 2.0 :output-rate 10.0})]
    {:status :PREFLIGHT-ONLY :model (:model prepared) :transport (:transport prepared)
     :model-calls 0 :selector-learning :UNPROVEN}))

(defn offline-controls! [root]
  (u/ensure! (not (.exists (io/file root))) "Offline control destination already exists" {})
  (let [proof (isolation/require-tested!) proposal (u/read-file proposal-path) library (tasks/library)
        cpu (tasks/world 981101 {:structure :chain :size 4})
        mixed (tasks/world 981102 {:structure :fanout :size 5 :resource :license :omit-memory true})
        compose {:route :compose :hashes [(:rank library) (:pack library)]}
        slots [["cpu-retained" cpu {:route :reuse :hash (:retained library)}]
               ["cpu-compute" cpu {:route :compute}] ["cpu-compose" cpu compose]
               ["mixed-retained" mixed {:route :reuse :hash (:retained library)}]
               ["mixed-compose" mixed compose] ["mixed-adapt" mixed {:route :adapt}]
               ["mixed-delegate" mixed {:route :delegate}]]
        source (:source (first (filter #(= (:hash %) (:compute library)) (:artifacts library))))
        turns [{:op :policy/use :source source} {:op :done :summary "SCRIPTED FIXTURE. No model inference."}]
        scripted (provider/->FixtureProvider (atom {"generation" turns "policy-child" turns}))
        account (phase! root proposal :fixture :acquisition scripted)
        manifest {:version tasks/version :evidence-category :FIXTURE :source (experiment/manifest proposal)
                  :proof proof :library-hash (:hash library) :slots (mapv first slots)
                  :model-calls 0 :billing-usd 0 :fixture-provider-turns-expected 4}
        _ (u/write-edn! (str root "/manifest.edn") manifest)
        rows (mapv (fn [[id world decision]]
                     (let [row (execute! (str root "/" id) proposal :fixture library (:provider account) world
                                        (fn [_ _] decision))]
                       (gate/verified-row! world row 2)
                       (assoc row :slot id))) slots)
        ;; A separate SCI process must execute a selector too. This selector is
        ;; explicitly developer-authored; persistence is not learned behavior.
        selector (a/make-artifact {:category :analysis :interface {:name "select-route" :arity 1}
                                  :source (str "(fn [input] " (pr-str compose) ")")
                                  :dependencies [] :parent nil :author "scripted-selector-control"
                                  :provenance :developer-fixture})
        registry (str root "/selector-control") _ (a/save! registry selector)
        selected (executable/invoke! registry selector [(gate/public-input mixed (:registry library))]
                                     (+ (limits/now-ms) 120000))
        expected? (fn [row]
                    (if (= "mixed-retained" (:slot row))
                      (and (= :execution (:failure-stage row)) (= :code-rejection (:failure-kind row)))
                      (and (nil? (:failure-stage row)) (= :complete (get-in row [:episode :metrics :status])))))
        composition-rows (filter #(.endsWith ^String (:slot %) "compose") rows)
        passed (and (every? expected? rows) (= compose selected)
                    (every? #(and (pos? (get (:invocations %) (:rank library) 0))
                                   (pos? (get (:invocations %) (:pack library) 0))) composition-rows))
        report {:version tasks/version :evidence-category :FIXTURE :status (if passed :passed :failed)
                :model-calls 0 :usage (accounting/reconcile-phase! (ledger account) (mapv :ledger rows))
                :selector selector :selected selected
                :rows (mapv #(select-keys % [:slot :artifact :failure-stage :failure-kind :invocations :stages :wall-ms :evidence-root]) rows)
                :completions (mapv #(vector (:slot %) (get-in % [:episode :metrics :status])) rows)
                :claim "Real isolated execution and scripted provider controls. No model-authored selector or learned advantage."}]
    (u/write-edn! (str root "/controls.edn") report) report))

(defn live-transfer! [root plan phase prepared]
  (let [acquisition (u/read-file (str root "/acquisition/transfer-manifest.edn"))
        promotion (:promotion acquisition)
        restored (cold-library (str root "/acquisition/executable-library") (tasks/library) (:candidate promotion))]
    (u/ensure! (and (= (:plan-hash plan) (:plan-hash acquisition))
                    (not= (:process-id acquisition) (.pid (java.lang.ProcessHandle/current)))
                    (= (:bundle-hash promotion) (:bundle-hash restored)))
               "Transfer requires a fresh process and the exact accepted executable bundle" {})
    ;; Only scalar costs and source identities cross this controller boundary.
    ;; No authoring history is loaded into the fresh process.
    (transfer! (str root "/" (name phase)) plan :live (:adapter prepared) phase
               (:library restored) (:selector restored) (:acquisition-usd acquisition))))

(defn -main [& [command root]]
  (try
    (u/ensure! (seq root) "Provide a new output directory or frozen plan directory" {})
    (case command
      "plan" (println (u/json-str (select-keys (plan! root) [:plan-hash :status :conditions])))
      "controls" (let [result (offline-controls! root)]
                   (println (u/json-str (select-keys result [:status :model-calls :usage :completions])))
                   (u/ensure! (= :passed (:status result)) "Offline controls failed; preserve evidence before a new version" {}))
      "preflight" (println (u/json-str (preflight! (load-plan! root))))
      "acquire" (let [plan (load-plan! root) _ (authorize! plan (System/getenv))
                      _ (isolation/require-tested!)
                      prepared (live/prepare-provider! {:model "claude-sonnet-5-5" :provider :claude-code-subscription
                                                       :input-rate 2.0 :output-rate 10.0})]
                  (println (u/json-str (select-keys (acquire! (str root "/acquisition") plan :live (:adapter prepared))
                                                   [:evidence-category :usage :candidates :promotion]))))
      ("heldout" "coldboot")
      (let [plan (load-plan! root) _ (authorize! plan (System/getenv)) _ (isolation/require-tested!)
            prepared (live/prepare-provider! {:model "claude-sonnet-5-5" :provider :claude-code-subscription
                                             :input-rate 2.0 :output-rate 10.0})]
        (println (u/json-str (select-keys (live-transfer! root plan (keyword command) prepared)
                                         [:phase :evidence-category :usage :summary]))))
      (u/fail "Supported commands: controls, plan, preflight, acquire, heldout, coldboot" {}))
    (catch Exception e (binding [*out* *err*] (println (u/json-str {:error (.getMessage e)}))) (System/exit 2)))
  (shutdown-agents))
