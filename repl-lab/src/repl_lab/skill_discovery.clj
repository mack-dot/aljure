(ns repl-lab.skill-discovery
  "Four-condition OFFLINE control. There is deliberately no live-provider path."
  (:refer-clojure :exclude [run!])
  (:require [clojure.java.io :as io] [repl-lab.util :as u] [repl-lab.artifact :as a]
            [repl-lab.skills :as skills] [repl-lab.fixtures :as f] [repl-lab.workloads :as w]
            [repl-lab.runtime :as runtime] [repl-lab.controller :as c] [repl-lab.provider :as p]
            [repl-lab.experiment :as experiment] [repl-lab.sim :as sim] [repl-lab.records :as records]
            [repl-lab.execution :as execution] [repl-lab.executable :as executable]
            [repl-lab.isolation :as isolation] [repl-lab.limits :as limits]
            [repl-lab.policy-diagnostic :as diagnostic]))

(def ^:dynamic *protocol-path* "config/skill-discovery-v2.edn")
(defn protocol [] (u/read-file *protocol-path*))
(defn cases []
  (mapv (fn [seed size extra?]
          (let [world (w/generate seed {:size size :structure :layered :fault-count 1})]
            (if-not extra? world
              ;; Existing simulator already checks arbitrary resource keys. No scorer change.
              (-> world (update :jobs #(mapv (fn [j] (assoc-in j [:resources :gpu] 1)) %))
                  (update :workers #(mapv (fn [worker] (if (= "w1" (:id worker)) worker
                                                         (assoc-in worker [:capacity :gpu] 2))) %))))))
        (:seeds (protocol)) (:sizes (protocol)) (:extra-resource (protocol))))

(def selector-fixture
  (a/make-artifact
    {:category :analysis :interface {:name "select-route" :arity 1} :dependencies [] :parent nil
     :author "developer-offline-control" :provenance :developer-fixture
     :source "(fn [observation] (let [extra (some (fn [j] (some (fn [k] (not (contains? #{:cpu :mem} k))) (keys (:resources j)))) (:jobs observation))] {:route (if extra (if (even? (count (:jobs observation))) :compute :delegate) :reuse)}))"}))

(defn instructions [] (str (slurp "resources/base-instructions.txt") "\n" (slurp "resources/skill-discovery-v2.txt")))
(defn applicable? [observation]
  ;; Fixed control from the reviewed contract. It recognizes any extra resource,
  ;; not the spelling "gpu". This is deliberately not a learned strategy.
  (every? #(every? #{:cpu :mem} (keys (:resources %))) (:jobs observation)))
(defn task [root policy arm]
  {:task "Complete the scheduling workload. Select, compute, delegate, adapt or synthesize as needed. The approved library is frozen."
   :policy (:hash policy) :context-handles ["jobs" "workers" "observation"]
   ;; Only initial disclosure differs. Every condition can request the same metadata/source.
   :skills (if (= arm :opaque-hash) [{:hash (:hash policy)}]
               (mapv skills/compact (skills/inventory root (:hash policy))))})

(defn scripts [arm policy observation route]
  (let [query {:op :context/query :handle "observation" :query {:limit 1}}
        select {:op :policy/select :hash (:hash policy)}
        synth {:op :policy/use :source (:source f/packed-policy)}
        done {:op :done :summary "OFFLINE scripted control; not a model decision."}
        extra? (not (applicable? observation))]
    (case arm
      :opaque-hash {"root" [query synth done]}
      :applicability-guard {"root" [query synth done]}
      :descriptive-discovery {"root" [{:op :skills/list}
                                      {:op :skills/describe :hash (:hash policy)} query
                                      (if extra? synth select) done]}
      :model-authored-selection
      (case route
        :reuse {"root" [select done]}
        :compute {"root" [query {:op :repl/eval :source "(mapv (fn [j] (vec (keys (:resources j)))) jobs)"
                                :bindings {:jobs (:jobs observation)}} synth done]}
        :delegate {"root" [query {:op :agent/call :id "resource-check" :task "Check resource compatibility."
                                 :context (mapv :resources (:jobs observation))} synth done]
                   "resource-check" [{:op :done :summary "Fixture: the retained CPU/memory policy needs adaptation for GPU constraints."}]}))))

(defn isolated! [target arguments world deadline]
  ;; Startup readiness, loading, and function execution have distinct evidence.
  (let [backend (execution/backend :clojure) worker (atom nil) phase (atom :startup)
        invocations (atom 0) successful (atom 0) stages (atom []) error (atom nil)
        cleanup (atom nil) begin (System/nanoTime)
        mark! #(swap! stages conj {:phase % :elapsed-ms (/ (- (System/nanoTime) begin) 1e6)})
        result (try
                 (reset! worker (execution/open! backend deadline))
                 (u/ensure! (= 42 (execution/evaluate! backend @worker "(+ 20 22)" {})) "Readiness failed" {})
                 (mark! :startup-ready) (reset! phase :code-loading)
                 (executable/load! backend @worker target []) (mark! :code-loaded)
                 (reset! phase :execution)
                 (let [call (fn [args]
                              (swap! invocations inc)
                              (try (let [v (executable/call! backend @worker target args)]
                                     (swap! successful inc) v)
                                   (catch Exception e (reset! error (diagnostic/exception-data e)) (throw e))))]
                   (if world (sim/run-episode world #(call [%1 %2]) {:deadline-ms deadline :event-budget 10000})
                       {:value (call arguments)}))
                 (catch Exception e (reset! error (diagnostic/exception-data e))
                   (if world (sim/execution-failure world (.getMessage e)) {}))
                 (finally
                   (when @worker (try (execution/close! backend @worker)
                                      (catch Exception e (reset! cleanup (diagnostic/exception-data e)))))
                   (mark! :cleanup-finished)))
        failed? (or @error (and world (not= :complete (get-in result [:metrics :status]))))]
    {:result result :artifact (:hash target) :stages @stages
     :failure-stage (cond @cleanup :cleanup @error @phase (= :wall-budget (get-in result [:metrics :status])) :execution failed? :algorithm)
     :failure-kind (cond @error (diagnostic/error-kind @error)
                         (= :wall-budget (get-in result [:metrics :status])) :task-time-limit)
     :exception @error :cleanup-error @cleanup
     :attempted-invocations @invocations :successful-invocations @successful
     :supervisor-pid (some-> @worker :process .pid)
     :worker-stderr (when-let [errors (:errors @worker)] (deref errors 5000 "Diagnostics unavailable"))
     :wall-ms (/ (- (System/nanoTime) begin) 1e6)}))

(defn episode! [root config world {:keys [arm id] :as slot} policy]
  (let [store (str root "/sessions/" id ".sqlite") observation (sim/observe (sim/initial-state world) nil)
        _ (c/create-run! store id config (:hash policy)) _ (c/session! store id "root" nil)
        deadline (:deadline-ms (limits/from-run (c/get-run store id)))
        _ (doseq [[handle rows] [["jobs" (:jobs observation)] ["workers" (:workers observation)] ["observation" [observation]]]]
            (c/put-context! store id handle rows))
        select-result (when (= arm :model-authored-selection) (isolated! selector-fixture [observation] nil deadline))
        _ (when select-result (u/write-edn! (str root "/selectors/" id ".edn") select-result))
        route (get-in select-result [:result :value :route])
        env {:store store :run id :registry root :workers (atom {}) :provenance :synthetic-fixture
             :base-instructions (instructions) :allow-learning false}
        outcome (try (if (:failure-stage select-result) {:error "Selector worker failed"}
                  (if (or (= arm :deterministic-reuse) (and (= arm :applicability-guard) (applicable? observation)))
                    (do (runtime/broker! env "root" {:op :policy/select :hash (:hash policy)})
                        (c/finish-session! store id "root" :complete {:summary "Deterministic reuse control"}) {})
                    (runtime/run-session!
                      (assoc env :provider (p/->FixtureProvider (atom (scripts arm policy observation route))))
                      "root" (task root policy arm))))
                  (catch Exception e {:error (.getMessage e) :exception (diagnostic/exception-data e)
                                      :failure-stage (if (re-find #"cleanup|termination" (.getMessage e)) :cleanup :agent)}))
        ledger (c/get-run store id)
        tool-failures (filterv #(and (= :tool-result (:type %)) (= :error (get-in % [:payload :status]))) (:events ledger))
        selected (runtime/selected-policy root ledger "root" policy)
        _ (a/save! root selected)
        execution (if (or (:error outcome) (seq tool-failures))
                    {:result (sim/execution-failure world (or (:error outcome) "Offline control tool failure; see events"))
                     :failure-stage (or (:failure-stage select-result) (:failure-stage outcome)
                                        (when (seq tool-failures) :agent-tool-unresolved) :agent)
                     :exception (or (:exception select-result) (:exception outcome))
                     :attempted-invocations 0 :successful-invocations 0}
                    (isolated! selected nil world deadline))
        events (:events ledger)
        tool-calls (map #(get-in % [:payload :command :op]) (filter #(= :tool-call (:type %)) events))
        fixture-calls (count (filter #(= :fixture-provider-call (:type %)) events))
        meta (merge slot (dissoc execution :result)
                    {:evidence-category :FIXTURE :selector-status (when select-result :developer-fixture-stand-in)
                     :selector route :selector-execution (dissoc select-result :result)
                     :selected-artifact (:hash selected) :artifact (:hash selected)
                     :verified-completion (and (= :complete (get-in execution [:result :metrics :status]))
                                               (nil? (:failure-stage execution)))
                     :retained-invocations (if (= (:hash policy) (:hash selected)) (:successful-invocations execution) 0)
                     :discovery {:inventory-exposed (and (pos? fixture-calls) (not= arm :opaque-hash))
                                 :list-requests (count (filter #{:skills/list} tool-calls))
                                 :describe-requests (count (filter #{:skills/describe} tool-calls))
                                 :source-requests (count (filter #{:artifact/inspect} tool-calls))}
                     :tool-counts (frequencies tool-calls) :tool-failures tool-failures
                     :fixture-provider-calls fixture-calls
                     :task-wall-ms (- (limits/now-ms) (:started-ms ledger))
                     :inference {:model-calls 0 :input-tokens 0 :output-tokens 0 :usd-equivalent 0}
                     :ledger-usage {:spent (:spent ledger) :reserved (:reserved ledger)}
                     :local-compute-usd nil :total-economic-usd nil
                     :execution-limits {:deadline-ms deadline :wall-ms 120000 :event-budget 10000}})
        record (records/save-episode! root id world (:result execution) meta)]
    (records/write-events! (str root "/sessions/" id ".jsonl") events)
    (u/write-json! (str root "/episodes/" id ".summary.json") (dissoc record :world :records :timeline :attempts))
    (println (u/json-str (select-keys record [:id :failure-stage :metrics :retained-invocations :fixture-provider-calls])))
    (flush) record))

(defn summarize [slots records]
  (into {} (for [arm (:conditions (protocol))
                 :let [rows (filter #(= arm (:arm %)) records)
                       complete (filter :verified-completion rows)
                       acquisition (:historical-acquisition (protocol))]]
             [arm {:planned (count (filter #(= arm (:arm %)) slots)) :attempted (count rows)
                   :complete (count complete) :failure-stages (frequencies (keep :failure-stage rows))
                   :mean-completed-makespan (when (seq complete) (/ (reduce + (map #(get-in % [:metrics :makespan]) complete)) (double (count complete))))
                   :retained-invocations (reduce + (map :retained-invocations rows))
                   :fixture-provider-calls (reduce + (map :fixture-provider-calls rows))
                   :model-calls 0 :input-tokens 0 :output-tokens 0 :new-inference-usd-equivalent 0
                   :historical-acquisition-amortized (when (seq complete)
                       {:known-equivalent-per-verified-solution (/ (:known-usd-equivalent acquisition) (count complete))
                        :uncertain-reservation-per-verified-solution (/ (:uncertain-reserved-usd-equivalent acquisition) (count complete))
                        :scope (:scope acquisition) :interpretation :bookkeeping-only-not-live-efficiency})
                   :total-economic-usd nil}])))

(defn run! [root]
  (u/ensure! (and (seq root) (.startsWith root "var/diagnostics/")) "Use a new var/diagnostics/ path" {})
  (u/ensure! (not (.exists (io/file root))) "Output exists; offline controls cannot be overwritten or retried" {})
  (let [spec (protocol) config (-> (u/read-file "config/experiment.edn")
                                  (assoc :mode :fixture :provenance :synthetic-fixture)
                                  (update :limits merge (:task-limits spec)))
        check (isolation/require-tested!) worlds (cases)
        _ (when-let [image (:required-image spec)]
            (u/ensure! (= image (:image check)) "Worker differs from versioned profile" {}))
        old-worlds (set (map u/hash-value (mapcat val (u/read-file "var/runs/model-1793062055972/sealed-splits.edn"))))
        _ (u/ensure! (not-any? old-worlds (map u/hash-value worlds)) "Worlds overlap prior sealed experiment" {})
        _ (u/ensure! (= (.getCanonicalPath (io/file root "workers"))
                       (some-> (System/getenv "REPL_LAB_WORKER_AUDIT_DIR") io/file .getCanonicalPath))
                     "Set REPL_LAB_WORKER_AUDIT_DIR to this run's workers directory" {})
        policy (a/load! diagnostic/retained-registry diagnostic/retained-hash)
        arms (:conditions spec)
        slots (vec (for [index (range (count worlds)) offset (range (count arms))
                         :let [arm (nth arms (mod (+ index offset) (count arms)))]]
                     {:id (str (name arm) "-" index) :index index :arm arm}))
        snapshot (assoc (experiment/manifest config) :protocol spec :isolation check :plan slots
                        :world-hashes (mapv u/hash-value worlds) :prompt-hash (u/sha (instructions))
                        :model {:requested "claude-sonnet-5-5" :returned "fixture-script-v1"
                                :provider :fixture :requested-role :future-live-pin-only}
                        :capability-hash (u/hash-value runtime/schemas))]
    (u/ensure! (.mkdirs (io/file root)) "Could not exclusively create output directory" {})
    (a/save! root policy) (a/save! root selector-fixture)
    (u/write-edn! (str root "/manifest.edn") snapshot) (u/write-json! (str root "/manifest.json") snapshot)
    (u/write-edn! (str root "/worlds.edn") worlds)
    (u/write-json! (str root "/catalog.json") (skills/inventory root (:hash policy)))
    (loop [todo slots results []]
      (let [slot (first todo)
            record (when slot (episode! root config (worlds (:index slot)) slot policy))
            results (cond-> results record (conj record))
            stop? (and record (or (#{:startup :cleanup :agent-tool-unresolved} (:failure-stage record))
                                 (#{:startup :cleanup} (get-in record [:selector-execution :failure-stage]))
                                 (let [q (io/file "var/isolation-quarantine")] (and (.exists q) (seq (.listFiles q))))))
            report {:evidence-category :FIXTURE :status (cond stop? :stopped-unhealthy (next todo) :running :else :complete)
                    :model-authored-selector :NOT-RUN-NO-INFERENCE-AUTHORIZED
                    :planned (count slots) :attempted (count results) :unattempted (vec (rest todo))
                    :conditions (summarize slots results)
                    :cases (mapv #(dissoc % :world :records :timeline :attempts) results)}]
        (experiment/assert-frozen-source! snapshot)
        (u/write-json! (str root "/report.json") report)
        (if (and (next todo) (not stop?)) (recur (rest todo) results)
            (select-keys report [:status :planned :attempted :conditions]))))))

(defn -main [action root]
  (try
    (u/ensure! (#{"fixtures" "fixtures-v3" "fixtures-v4"} action) "Only fixtures are implemented. Live selection needs separate authorization and an independently accepted model-authored selector." {})
    (binding [*protocol-path* (case action "fixtures-v4" "config/skill-discovery-v4.edn"
                                         "fixtures-v3" "config/skill-discovery-v3.edn" "config/skill-discovery-v2.edn")]
      (println (u/json-str (run! root)))) (shutdown-agents)
    (catch Exception e (println (u/json-str {:error (.getMessage e) :data (ex-data e)}))
      (shutdown-agents) (System/exit 2))))
