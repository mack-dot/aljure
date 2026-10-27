(ns repl-lab.selector-acquisition-test
  (:require [clojure.test :refer :all] [repl-lab.selector-acquisition :as acquisition]
            [repl-lab.selector-tasks :as tasks] [repl-lab.selector-accounting :as accounting]
            [repl-lab.selector-gate :as gate] [repl-lab.controller :as c] [repl-lab.provider :as p]
            [repl-lab.artifact :as a] [repl-lab.util :as u] [repl-lab.sim :as sim]
            [repl-lab.fixtures :as f] [repl-lab.executable :as executable]
            [repl-lab.bundle :as bundle] [repl-lab.runtime-test :as rt] [clojure.edn :as edn]
            [repl-lab.store :as store] [repl-lab.execution :as execution]))

(def proposal (u/read-file acquisition/proposal-path))
(defn initial-ledger []
  {:id "fixture" :started-ms 1 :status :running :config {:mode :fixture}
   :sessions {"root" {:status :complete}} :provider-requests {} :events []
   :reserved {:calls 0 :tokens 0 :usd 0.0} :spent {:calls 0 :tokens 0 :usd 0.0}})
(defn receipt-ledger [usd]
  (let [response {:model "fixture" :usage {:input_tokens 10 :output_tokens 5} :tokens 15 :usd usd}]
    (-> (initial-ledger)
        (assoc :provider-requests {"r" {:session "root" :status :complete :response response}})
        (assoc :events [{:type :provider-result :payload (assoc (select-keys response [:model :tokens :usd]) :request-id "r")}])
        (assoc :spent {:calls 1 :tokens 15 :usd usd}))))

(deftest strict-ledgers-reject-unknown-missing-and-inconsistent-usage
  (is (thrown? Exception (accounting/usage! {})))
  (is (= 0 (:calls (accounting/usage! (initial-ledger)))))
  (is (= {:calls 1 :tokens 15 :input-tokens 10 :output-tokens 5 :usd 0.2}
         (accounting/usage! (receipt-ledger 0.2))))
  (doseq [ledger [(assoc (receipt-ledger 0.2) :events [])
                  (assoc-in (receipt-ledger 0.2) [:spent :usd] 0)
                  (assoc-in (receipt-ledger 0.2) [:reserved :usd] 1)
                  (assoc-in (receipt-ledger 0.2) [:provider-requests "r" :response :tokens] 16)
                  (assoc-in (receipt-ledger 0.2) [:provider-requests "r" :status] :unknown)
                  (assoc-in (receipt-ledger 0.2) [:config :mode] :live)]]
    (is (thrown? Exception (accounting/usage! ledger)))))

(deftest new-panel-separates-public-contracts-from-hidden-evaluation
  (let [library (tasks/library) splits (tasks/generate-splits (range 960001 960015))
        worlds (mapcat val splits)]
    (is (= 14 (count worlds) (count (set (map u/hash-value worlds)))))
    (is (every? #(and (sim/feasible? %) (empty? (sim/workload-errors %))) worlds))
    (is (thrown? Exception (tasks/generate-splits (repeat 12 1))))
    (doseq [world worlds]
      (let [public (gate/public-input world (:registry library))]
        (is (= #{:observation :skills} (set (keys public))))
        (is (not-any? #(contains? public %) [:seed :faults :actual :hidden-outcomes]))
        (is (not-any? #(contains? % :actual) (get-in public [:observation :jobs])))))
    (is (= :reuse (:route (tasks/guard library (gate/public-input (first (:learning splits)) (:registry library))))))
    (is (= :compose (:route (tasks/guard library (gate/public-input (last (:learning splits)) (:registry library))))))
    (is (= :compose (:route (tasks/guard library (gate/public-input (second (:learning splits)) (:registry library))))))
    (let [composition (tasks/composed library [(:rank library) (:pack library)])]
      (is (= [(:rank library) (:pack library)] (:dependencies composition)))
      (is (= '(fn [observation memory] (pack-ranked (rank-jobs observation) (:workers observation) memory)) (:forms composition))))
    (is (thrown? Exception (tasks/composed library [(:pack library) (:rank library)])))
    (is (thrown? Exception (gate/decision! {:route :compose :hashes [(:rank library) "unapproved"]}
                                         (set (map :hash (:artifacts library))) 2)))))

(deftest phase-budget-covers-roots-children-and-retains-unknown-reservations
  (let [root (rt/temp-root) library (tasks/library)
        delegate (p/->FixtureProvider (atom {"root" [{:op :done :summary "FIXTURE"}]
                                             "child" [{:op :done :summary "FIXTURE"}]}))
        account (acquisition/phase! root proposal :fixture :acquisition delegate)
        ctx (acquisition/context! (str root "/task") (acquisition/config proposal :fixture :task) library (:provider account))]
    (c/session! (:store ctx) (:run ctx) "root" nil)
    (p/invoke! (:provider ctx) (:store ctx) (:run ctx) "root" [])
    (c/session! (:store ctx) (:run ctx) "child" "root")
    (p/invoke! (:provider ctx) (:store ctx) (:run ctx) "child" [])
    (is (= 2 (:calls (accounting/usage! (acquisition/ledger ctx)))))
    (is (= 2 (:calls (accounting/usage! (acquisition/ledger account)))))
    (is (= #{"root" "child"} (set (map #(get-in % [:response :origin-session]) (vals (:provider-requests (acquisition/ledger account)))))))
    (is (thrown? Exception (p/invoke! (:provider ctx) (:store ctx) (:run ctx) "root" [])))
    (is (= 1 (get-in (acquisition/ledger account) [:reserved :calls])))
    (is (thrown? Exception (accounting/usage! (acquisition/ledger account))))
    (is (thrown? Exception (p/invoke! (:provider ctx) (:store ctx) (:run ctx) "child" [])))))

(deftest v2-gate-independent-replay-provenance-and-acquisition-cost
  (let [world (tasks/world 971001 {:structure :independent :size 3})
        candidate (a/make-artifact {:category :analysis :interface {:name "select-route" :arity 1}
                                   :source "(fn [input] {:route :compute})" :dependencies [] :parent nil
                                   :author "scripted-fixture" :provenance :developer-fixture})
        row (fn [usd] {:episode (sim/run-episode world f/packed {}) :ledger (receipt-ledger usd)})
        options {:root (rt/temp-root) :candidate candidate :mode :fixture :registry []
                 :authoring-ledger (receipt-ledger 0.1) :development-worlds [world]
                 :config (assoc (acquisition/config proposal :fixture :task) :development-case-hashes [(u/hash-value world)])
                 :execute-route (fn [& _] (row 0.01))
                 :control-executors (into {} (for [name (:controls proposal)] [name (fn [& _] (row 0.2))]))}]
    (with-redefs [executable/invoke! (fn [& _] {:route :compute})]
      (let [receipt (gate/adjudicate! options)]
        (is (= :fixture-accepted (:status receipt)) (pr-str receipt))
        (is (< (Math/abs (- 1.11 (:acquisition-usd receipt))) 1e-9))
        (is (= :fixture-rejected (:status (gate/finalize-acquisition receipt 100.0))))
        (is (thrown? Exception (acquisition/promote! (rt/temp-root) (tasks/library) candidate receipt (initial-ledger)))))
      (is (= :validation-error (:status (gate/adjudicate! (assoc options :mode :live)))))
      (is (= :validation-error (:status (gate/adjudicate! (assoc options :authoring-ledger {})))))
      (is (= :validation-error (:status (gate/adjudicate! (assoc options :execute-route
                                          (fn [& _] (assoc-in (row 0) [:episode :metrics :score] -100)))))))
      (is (= :unverified-infrastructure (:status (gate/adjudicate! (assoc options :execute-route
                                          (fn [& _] (assoc (row 0) :failure-stage :startup))))))))))

(deftest scripted-acquisition-uses-native-staging-and-independent-rejection
  (let [root (rt/temp-root) library (tasks/library)
        artifact (a/make-artifact {:category :analysis :source "(fn [input] {:route :compute})"
                                  :interface {:name "select-route" :arity 1} :dependencies [] :parent nil
                                  :author "author" :provenance :developer-fixture})
        submit (assoc (select-keys artifact [:category :source :interface :dependencies :parent]) :op :artifact/submit)
        provider (p/->FixtureProvider
                   (atom {"author" [submit {:op :development/evaluate :hash (:hash artifact)} {:op :done :summary "FIXTURE"}]
                          "selection" (vec (repeat 3 {:op :done :summary "{:route :compute}"}))
                          "generation" (vec (mapcat identity (repeat 3 [{:op :policy/use :source (:source f/packed-policy)}
                                                                         {:op :done :summary "FIXTURE"}])))}))
        plan {:proposal proposal :plan-hash "fixture-not-live-plan" :splits (tasks/generate-splits (range 972001 972015))}]
    ;; Trusted known-correct fixture evaluates the existing simulator. No generated
    ;; code runs in this JVM. Actual SCI path is a separate, explicit control.
    (with-redefs [executable/invoke! (fn [& _] {:route :compute})
                  acquisition/isolated-policy! (fn [_ target world options]
                                                {:episode (sim/run-episode world f/packed options)
                                                 :invocations {(:hash target) 1} :failure-stage nil})]
      (let [result (acquisition/acquire! root plan :fixture provider)]
        (is (= :FIXTURE (:evidence-category result)))
        (is (nil? (:promotion result)))
        (is (= :fixture-rejected (get-in result [:candidates 0 :status])))
        (is (= 12 (get-in result [:usage :calls])))
        (is (zero? (get-in result [:usage :usd])))
        (is (= :UNPROVEN (:harness-improvement result)))))))

(deftest cold-export-keeps-only-approved-code-and-preserves-public-identities
  (let [root (rt/temp-root) library (tasks/library)
        selector (a/make-artifact {:category :analysis :source (str "(fn [input] {:route :reuse :hash " (pr-str (:retained library)) "})")
                                  :interface {:name "select-route" :arity 1} :dependencies [] :parent nil
                                  :author "fixture-old-conversation" :provenance :developer-fixture})
        workflow (a/make-artifact (-> (:workflow library) (select-keys [:category :source :interface :dependencies :provenance])
                                     (update :dependencies conj (:hash selector)) (assoc :author "fixture" :parent nil)))]
    (acquisition/install! (str root "/registry") library)
    (a/save! (str root "/registry") selector) (a/save! (str root "/registry") workflow)
    (bundle/export! (str root "/registry") (str root "/export") (:hash workflow) :synthetic-fixture)
    (let [restored (acquisition/cold-library (str root "/export") library (:hash selector))]
      (is (= (:forms selector) (get-in restored [:selector :forms])))
      (is (not= (:author selector) (get-in restored [:selector :author])))
      (is (= (:retained library) (get-in restored [:library :retained])))
      (doseq [file (file-seq (clojure.java.io/file root "export")) :when (.isFile file)]
        (is (not (.contains (slurp file) "fixture-old-conversation")))))))

(deftest live-authorization-does-not-reuse-prior-campaign-approval
  (let [plan {:plan-hash "new-selector-plan" :proposal proposal}]
    (is (thrown? Exception (acquisition/authorize! plan {})))
    (is (thrown? Exception (acquisition/authorize! plan {"LIVE" "1" "MODEL" "claude-sonnet-5-5" "MAX_USD" "35"
                                                       "INFERENCE_PROVIDER" "claude-subscription" "SELECTOR_APPROVED_PLAN" "prior-learning-plan"})))
    (is (acquisition/authorize! plan {"LIVE" "1" "MODEL" "claude-sonnet-5-5" "MAX_USD" "57"
                                     "INFERENCE_PROVIDER" "claude-subscription" "SELECTOR_APPROVED_PLAN" "new-selector-plan"}))))

(deftest instrumentation-uses-one-edn-form-and-preserves-episodes-on-trace-failure
  ;; Exact EDN contract from worker/safe-read. No generated code is evaluated in
  ;; this host test. Real SCI execution is checked separately by controls-v3.
  (let [parse (fn [source]
                (with-open [reader (java.io.PushbackReader. (java.io.StringReader. source))]
                  (let [options {:eof ::eof :readers {} :default (fn [& _] (throw (ex-info "tag" {})))}
                        form (edn/read options reader)]
                    (is (= ::eof (edn/read options reader))) form)))
        target (first (:artifacts (tasks/library)))]
    (is (nil? (last (parse acquisition/initialize-invocations))))
    (is (nil? (last (parse (acquisition/instrument-source target)))))
    (is (= '(deref selector-invocations) (parse acquisition/read-invocations)))
    (is (thrown? Exception (parse "@selector-invocations")))
    (let [world (tasks/world 982001 {:structure :independent :size 3})
          episode (sim/run-episode world f/packed {})]
      (with-redefs [execution/require-tested! (fn [& _] true)
                    execution/backend (fn [_] (reify execution/ExecutionBackend
                                                (open! [_ _] :fixture-worker)
                                                (close! [_ _] nil)
                                                (evaluate! [_ _ source _]
                                                  (cond (= source "(+ 20 22)") 42
                                                        (= source acquisition/read-invocations) (throw (ex-info "fixture tracing failure" {}))
                                                        :else nil))))
                    executable/load! (fn [& _] nil)
                    a/dependency-closure (fn [& _] [])
                    sim/run-episode (fn [& _] episode)]
        (let [row (acquisition/isolated-policy! "unused" target world {:deadline-ms (+ 10000 (System/currentTimeMillis))})]
          (is (= (:final-hash episode) (get-in row [:episode :final-hash])))
          (is (= :instrumentation (:failure-stage row)))
          (is (gate/infrastructure-failure? row)))))))

(deftest transfer-retains-failed-and-undispatched-slots-and-distinguishes-code-errors
  (let [library (tasks/library) world (tasks/world 983001 {:structure :independent :size 3})
        plan {:proposal proposal :plan-hash "fixture" :splits {:heldout [world]}}
        root (rt/temp-root) state (atom {}) calls (atom 0)
        episode (sim/run-episode world f/packed {})]
    ;; Existing store CAS semantics, in memory for this control. No worker/model.
    (with-redefs [store/transact! (fn [_ id f] (get (swap! state update id f) id))
                  store/read-value (fn [_ id] (get @state id))
                  acquisition/execute! (fn [& _]
                                         (swap! calls inc)
                                         {:episode episode :ledger {} :failure-stage nil})]
      (let [report (acquisition/transfer! root plan :fixture nil :heldout library nil 2.0)]
        (is (= 1 @calls))
        (is (= 6 (count (:rows report)) (:planned-slots report)))
        (is (= :unverified (get-in report [:rows 0 :outcome])))
        (is (= 5 (count (filter #(= :not-dispatched (:outcome %)) (:rows report)))))
        (is (every? #(zero? (:verified-complete %)) (vals (:summary report))))
        (is (.isFile (clojure.java.io/file root "transfer.edn")))))
    (let [summary (acquisition/transfer-summary
                    [{:condition :model-authored-selection :outcome :scored
                      :failure-stage :execution :failure-kind :code-rejection :usd 0.1
                      :usage {:status :complete :calls 1 :input-tokens 1 :output-tokens 1}
                      :metrics {:status :policy-error}}
                     {:condition :model-authored-selection :outcome :not-dispatched}] 2.0)]
      (is (zero? (get-in summary [:model-authored-selection :infrastructure-failures])))
      (is (= 1 (get-in summary [:model-authored-selection :algorithm-failures])))
      (is (= 2.1 (get-in summary [:model-authored-selection :total-usd-equivalent])))
      (is (nil? (get-in summary [:model-authored-selection :measured-usd-per-verified-solution]))))))

(deftest route-contract-errors-are-not-infrastructure-and-unknown-outcomes-still-block
  (let [library (tasks/library) world (tasks/world 984001 {:structure :independent :size 3})
        state (atom (initial-ledger)) ctx {:registry (rt/temp-root) :provider nil}]
    (with-redefs [acquisition/context! (fn [& _] ctx)
                  acquisition/public-context! (fn [& _] nil)
                  acquisition/ledger (fn [& _] @state)
                  acquisition/session! (fn [& _]
                                         (swap! state assoc-in [:sessions "generation" :status] :complete)
                                         {:summary "Fixture done without a policy."})]
      (doseq [decision [{:route :unknown} {:route :reuse :hash "not-approved"}
                        {:route :compose :hashes [(:pack library) (:rank library)]}
                        {:route :synthesize}]]
        (let [row (acquisition/execute! (rt/temp-root) proposal :fixture library nil world (fn [& _] decision))]
          (is (= :algorithm-or-contract (:failure-kind row)))
          (is (not (gate/infrastructure-failure? row)))))
      (swap! state assoc-in [:reserved :calls] 1)
      (let [row (acquisition/execute! (rt/temp-root) proposal :fixture library nil world
                                     (fn [& _] {:route :unknown}))]
        (is (= :unresolved (:failure-kind row)))
        (is (gate/infrastructure-failure? row)))
      (reset! state (initial-ledger))
      (let [row (acquisition/execute! (rt/temp-root) proposal :fixture library nil world
                                     (fn [& _] (throw (ex-info "Worker terminated without result" {}))))]
        (is (= :infrastructure-or-unresolved (:failure-kind row)))
        (is (gate/infrastructure-failure? row)))
      (swap! state update :events conj {:type :tool-result :payload {:op :repl/eval :status :error :error "Worker response timeout"}})
      (let [row (acquisition/execute! (rt/temp-root) proposal :fixture library nil world
                                     (fn [& _] {:route :synthesize}))]
        (is (= :unresolved (:failure-kind row)))
        (is (gate/infrastructure-failure? row))))))
