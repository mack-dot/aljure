(ns repl-lab.elastic-test
  "Asynchronous children, phase A: the controller ledger state machine and the
  executor. Offline: scripted providers, stub workers and the real SQLite
  compare-and-set store. No network, credentials, model calls or Docker."
  (:require [clojure.test :refer :all] [repl-lab.elastic :as e] [repl-lab.controller :as c]
            [repl-lab.util :as u] [repl-lab.model-protocol :as wire] [repl-lab.runtime :as runtime]
            [repl-lab.external-task :as external]))

(def base-config (u/read-file "config/experiment.edn"))
(def on {:max-depth 2 :max-active 3 :max-children 6 :child-calls 4 :child-tokens 4000 :child-usd 1.0
         :child-wall-ms 60000 :root-floor {:calls 2} :result-chars 16})

(defn- temp-root []
  (str (java.nio.file.Files/createTempDirectory "repl-lab-elastic-" (make-array java.nio.file.attribute.FileAttribute 0))))
(defn fixture
  ([] (fixture on {}))
  ([elastic limits]
   (let [store (str (temp-root) "/controller.sqlite")
         config (cond-> (update base-config :limits merge limits)
                  elastic (assoc-in [:contract :elastic-children] elastic))]
     (c/create-run! store "run" config "initial")
     (c/session! store "run" "root" nil)
     (c/put-context! store "run" "context" [{:line 0 :text "a"}])
     (c/put-context! store "run" "other" [{:line 0 :text "b"}])
     store)))
(defn- ledger [store] (c/get-run store "run"))
(defn- state [store id] (:state (e/child (ledger store) id)))
(defn- denial [f] (try (f) nil (catch clojure.lang.ExceptionInfo x (or (:elastic-denied (ex-data x)) (.getMessage x)))))
(defn- events [r kind] (filter #(= kind (:type %)) (:events r)))
(defn- running! [store caller id & [spec]]
  (e/spawn! store "run" caller (merge {:id id :task "subtask"} spec))
  (e/start! store "run" id))
(defn- receipt [tokens] {:tokens tokens :usd 0.0 :model "fixture"})
(defn- held-zero? [r] (every? #(= {:calls 0 :tokens 0 :usd 0.0} (:held %)) (vals (e/children r))))

(deftest off-by-default-writes-nothing-and-changes-no-model-interface
  (let [store (fixture nil {}) before (ledger store)]
    (doseq [f [#(e/spawn! store "run" "root" {:id "a" :task "t"}) #(e/start! store "run" "a")
               #(e/admit-call! store "run" "a" "q1" 10 0.0) #(e/cancel! store "run" "root" "a")
               #(e/collect! store "run" "root" "a") #(e/status store "run" "root" "a") #(e/expire! store "run")]]
      (is (= "Elastic execution is disabled" (denial f))))
    (e/recover! store "run")
    ;; No denial event, no :elastic key, no other change.
    (is (= before (ledger store)))
    (is (nil? (:elastic (ledger store)))))
  ;; Phase A exposes nothing to the model, even with the switch on.
  (let [config {:response-envelope wire/tool-envelope-version :sci-surface :assisted :sci-results :bounded}
        with (assoc-in config [:contract :elastic-children] on)]
    (is (= (wire/tool-definitions config) (wire/tool-definitions with)))
    (is (= ["context_metadata" "context_query" "repl_eval" "agent_call" "done"] (mapv :name (wire/tool-definitions with))))
    (is (= (external/instructions config) (external/instructions with)))
    (is (not-any? #{:agent/spawn :agent/collect :agent/status} (keys runtime/schemas)))))

(deftest settings-are-explicit-and-validated
  (doseq [bad [{:unknown 1} {:max-depth 3} {:max-active 0} {:child-usd -1} {:profiles #{:fast}}
               {:root-floor {:calls -1}} {:root-floor {:memory 1}} {:result-chars 100000} []]]
    (let [store (fixture bad {})]
      (is (= "Invalid elastic settings" (denial #(e/spawn! store "run" "root" {:id "a" :task "t"}))) (pr-str bad))
      (is (empty? (events (ledger store) :elastic-denied)))))
  ;; A partial map takes the documented defaults.
  (let [store (fixture {:max-active 1} {})]
    (is (= :spawned (:state (e/spawn! store "run" "root" {:id "a" :task "t"}))))
    (is (= (:child-calls e/defaults) (get-in (e/child (ledger store) "a") [:quota :calls])))))

(deftest spawn-admission-refuses-escapes-amplification-and-limits
  (let [store (fixture)]
    (testing "malformed or out-of-contract specs, each recorded as a denial"
      (doseq [[spec reason] [[{:id "a" :task "t" :shell "rm -rf /"} :spec-schema]
                             [{:id "a" :task "t" :env {"ANTHROPIC_API_KEY" "x"}} :spec-schema]
                             [{:id "../etc" :task "t"} :child-id]
                             [{:id "A" :task "t"} :child-id]
                             [{:id "root" :task "t"} :child-id]
                             [{:id "a" :task ""} :task-size]
                             [{:id "a" :task (apply str (repeat 8193 "x"))} :task-size]
                             [{:id "a" :task "t" :context ["/work/context.txt"]} :context]
                             [{:id "a" :task "t" :profile "claude-opus-5-5"} :unauthorized-profile]
                             [{:id "a" :task "t" :profile :max-effort} :unauthorized-profile]
                             [{:id "a" :task "t" :quota {:calls 5}} :quota-schema]
                             [{:id "a" :task "t" :quota {:gpu 1}} :quota-schema]]]
        (is (= reason (denial #(e/spawn! store "run" "root" spec))) (pr-str spec)))
      (is (= :caller-not-active (denial #(e/spawn! store "run" "stranger" {:id "a" :task "t"}))))
      (is (= 13 (count (events (ledger store) :elastic-denied))))
      (is (empty? (e/children (ledger store)))))
    (testing "a retried spawn is idempotent; a changed one is refused"
      (let [first (e/spawn! store "run" "root" {:id "a" :task "t" :context ["context"]})
            events-before (count (:events (ledger store)))]
        (is (= first (e/spawn! store "run" "root" {:id "a" :task "t" :context ["context"]})))
        (is (= events-before (count (:events (ledger store)))))
        (is (= :conflicting-duplicate (denial #(e/spawn! store "run" "root" {:id "a" :task "other"}))))))
    (testing "depth, nesting, context and quota inheritance"
      (is (= :caller-not-running (denial #(e/spawn! store "run" "a" {:id "b" :task "t"}))))
      (e/start! store "run" "a")
      (is (= :context-amplification (denial #(e/spawn! store "run" "a" {:id "b" :task "t" :context ["other"]}))))
      (is (= 2 (:depth (e/spawn! store "run" "a" {:id "b" :task "t" :context ["context"] :quota {:calls 2}}))))
      ;; A nested default wall time shrinks to the parent's; asking for more is refused.
      (let [r (ledger store)]
        (is (<= (:deadline-ms (e/child r "b")) (:deadline-ms (e/child r "a")))))
      (is (= :quota-exceeds-parent (denial #(e/spawn! store "run" "a" {:id "c" :task "t" :quota {:wall-ms 60000}}))))
      (e/start! store "run" "b")
      (is (= :depth (denial #(e/spawn! store "run" "b" {:id "c" :task "t"}))))
      ;; Quotas are ceilings, not escrow: a sibling of b may ask for up to a's
      ;; remaining quota, which a's own call in flight then reduces.
      (is (= :quota-schema (denial #(e/spawn! store "run" "a" {:id "c" :task "t" :quota {:calls 5}}))))
      (e/admit-call! store "run" "a" "qa" 10 0.0)
      (is (= :quota-exceeds-parent (denial #(e/spawn! store "run" "a" {:id "c" :task "t" :quota {:calls 4}})))))
    (testing "active and total limits"
      (e/spawn! store "run" "root" {:id "d" :task "t"})
      (is (= :active-limit (denial #(e/spawn! store "run" "root" {:id "e" :task "t"}))))
      (doseq [id ["d" "e" "f" "g"]]
        (when-not (= "d" id) (e/spawn! store "run" "root" {:id id :task "t"}))
        (e/cancel! store "run" "root" id))
      (is (= :child-limit (denial #(e/spawn! store "run" "root" {:id "h" :task "t"})))))))

(deftest quotas-bound-subtrees-and-the-root-keeps-its-floor
  (let [store (fixture on {:calls 12})]
    (running! store "root" "a" {:quota {:calls 3}})
    (running! store "a" "b" {:quota {:calls 2}})
    ;; b's calls count against a's quota as well as its own.
    (e/admit-call! store "run" "b" "b1" 10 0.0) (e/settle-call! store "run" "b1" (receipt 7))
    (e/admit-call! store "run" "b" "b2" 10 0.0) (e/settle-call! store "run" "b2" (receipt 7))
    (is (= :child-quota (denial #(e/admit-call! store "run" "b" "b3" 10 0.0))))
    (e/admit-call! store "run" "a" "a1" 10 0.0) (e/settle-call! store "run" "a1" (receipt 7))
    (is (= :child-quota (denial #(e/admit-call! store "run" "a" "a2" 10 0.0))))
    (let [r (ledger store)]
      (is (= {:calls 3 :tokens 21 :usd 0.0} (:used (e/child r "a"))))
      (is (= {:calls 2 :tokens 14 :usd 0.0} (:used (e/child r "b"))))
      (is (= 3 (get-in r [:spent :calls]))) (is (= 0 (get-in r [:reserved :calls]))) (is (held-zero? r))
      (is (= :request-id-reused (denial #(e/admit-call! store "run" "a" "b1" 10 0.0))))))
  (testing "children stop at the floor; the root's own calls still pass"
    (let [store (fixture (assoc on :child-calls 20 :max-active 3) {:calls 6})]
      (running! store "root" "a")
      (dotimes [i 4] (e/admit-call! store "run" "a" (str "q" i) 10 0.0))
      (is (= :run-budget (denial #(e/admit-call! store "run" "a" "q4" 10 0.0))))
      (dotimes [i 4] (e/settle-call! store "run" (str "q" i) (receipt 1)))
      (is (= :run-budget (denial #(e/spawn! store "run" "root" {:id "b" :task "t"}))))
      (dotimes [i 2] (c/reserve! store "run" (str "root-" i) "root" 10 0.0)
                     (c/reconcile! store "run" (str "root-" i) {:tokens 1 :usd 0.0}))
      (is (thrown-with-msg? Exception #"Global provider budget exhausted" (c/reserve! store "run" "root-2" "root" 10 0.0)))))
  (testing "a receipt above its reservation fails the child, halts, and stops the run"
    (let [store (fixture)]
      (running! store "root" "a")
      (e/admit-call! store "run" "a" "q" 10 0.0)
      (e/settle-call! store "run" "q" (receipt 11))
      (let [r (ledger store)]
        (is (= [:failed :budget-overrun] ((juxt :state :reason) (e/child r "a"))))
        (is (= :budget-overrun (:status r)))
        (is (= :budget-overrun (get-in r [:elastic :halted :reason])))))))

(defn- hammer
  "Each child admits and settles calls as fast as it can until refused. Returns
  the number of calls the ledger settled."
  [store ids]
  (let [workers (doall (for [id ids]
                         (future (loop [n 0]
                                   (let [q (str id "-" n)
                                         ok (try (e/admit-call! store "run" id q 50 0.01) true (catch Exception _ false))]
                                     (when ok
                                       ;; The call happened, so settling must eventually succeed,
                                       ;; even when compare-and-set contention refuses an attempt.
                                       (loop [] (when-not (try (e/settle-call! store "run" q {:tokens 50 :usd 0.01}) true
                                                               (catch Exception _ false))
                                                  (recur)))
                                       (recur (inc n))))))))]
    (run! deref workers)
    (count (filter #(= :complete (:status %)) (vals (get-in (ledger store) [:elastic :requests]))))))

(deftest concurrent-children-never-overspend-the-shared-budget
  (doseq [serialize [true false]]
    (testing (str "in-process write lock " (if serialize "on" "off; compare-and-set alone"))
      (let [store (fixture (assoc on :max-active 4 :child-calls 20 :root-floor {:calls 4}) {:calls 40 :tokens 1000000})
            ids ["a" "b" "c" "d"]]
        (doseq [id ids] (running! store "root" id))
        (let [settled (binding [e/*serialize-writes* serialize] (hammer store ids))
              r (ledger store)]
          (if serialize (is (= 36 settled)) (is (<= 1 settled 36)))
          (is (= settled (get-in r [:spent :calls])))
          (is (= (* 50 settled) (get-in r [:spent :tokens])))
          (is (= {:calls 0 :tokens 0} (select-keys (:reserved r) [:calls :tokens])))
          (is (= settled (reduce + (map #(get-in % [:used :calls]) (vals (e/children r))))))
          (is (held-zero? r))
          (is (<= (+ (get-in r [:spent :calls]) 4) 40)))))))

(deftest cancellation-cascades-waits-for-calls-in-flight-and-is-ancestor-only
  (let [store (fixture (assoc on :max-active 6 :max-depth 3) {:recursion-depth 3})]
    (running! store "root" "a")
    (running! store "a" "b")
    (running! store "b" "c")
    (is (= :depth (denial #(e/spawn! store "run" "c" {:id "z" :task "t"}))))
    (is (= :not-ancestor (denial #(e/cancel! store "run" "b" "a"))))
    (is (= :not-ancestor (denial #(e/cancel! store "run" "stranger" "c"))))
    (e/cancel! store "run" "root" "a")
    (is (= [:cancelled :cancelled :cancelled] (mapv #(state store %) ["a" "b" "c"])))
    (is (= ["a" "b" "c"] (get-in (last (events (ledger store) :elastic-cancel-requested)) [:payload :ids])))
    (testing "a call in flight is never interrupted; the child ends when it settles"
      (running! store "root" "d")
      (e/admit-call! store "run" "d" "qd" 10 0.0)
      (e/cancel! store "run" "root" "d")
      (is (= :cancelling (state store "d")))
      (is (= :not-running (denial #(e/admit-call! store "run" "d" "qd2" 10 0.0))))
      (e/settle-call! store "run" "qd" (receipt 9))
      (is (= :cancelled (state store "d")))
      (is (= 9 (get-in (ledger store) [:spent :tokens]))))
    (testing "cancelling a stopped child changes nothing"
      (let [before (mapv #(state store %) ["a" "b" "c" "d"])]
        (e/cancel! store "run" "root" "d")
        (is (= before (mapv #(state store %) ["a" "b" "c" "d"])))))))

(deftest an-unknown-outcome-holds-its-reservation-and-halts-only-new-elastic-work
  (let [store (fixture)]
    (running! store "root" "a")
    (running! store "root" "b")
    (e/admit-call! store "run" "a" "qa" 100 0.0)
    (e/admit-call! store "run" "b" "qb" 100 0.0)
    (e/call-unknown! store "run" "qa")
    (let [r (ledger store)]
      (is (= :unknown (state store "a")))
      ;; Unlike the run-global c/recover!, a sibling's call in flight is untouched.
      (is (= :pending (get-in r [:elastic :requests "qb" :status])))
      (is (= {:calls 2 :tokens 200} (select-keys (:reserved r) [:calls :tokens])))
      (is (= :provider-outcome-unknown (get-in r [:elastic :halted :reason]))))
    (is (= :halted (denial #(e/spawn! store "run" "root" {:id "c" :task "t"}))))
    (e/settle-call! store "run" "qb" (receipt 40))
    (is (= :halted (denial #(e/admit-call! store "run" "b" "qb2" 10 0.0))))
    (testing "operator resolution from a receipt charges it and fails the child"
      (e/settle-call! store "run" "qa" (receipt 60))
      (let [r (ledger store)]
        (is (= [:failed :resolved-unknown] ((juxt :state :reason) (e/child r "a"))))
        (is (= {:calls 0 :tokens 0} (select-keys (:reserved r) [:calls :tokens])))
        (is (= 100 (get-in r [:spent :tokens])))
        (is (some? (get-in r [:elastic :halted]))))))
  (testing "a call provably never sent is released without charge"
    (let [store (fixture)]
      (running! store "root" "a")
      (e/admit-call! store "run" "a" "q" 100 0.0)
      (e/release-call! store "run" "q")
      (let [r (ledger store)]
        (is (= :not-dispatched (get-in r [:elastic :requests "q" :status])))
        (is (= 0 (get-in r [:reserved :calls]) (get-in r [:spent :calls])))
        (is (= :running (state store "a")))))))

(deftest restart-recovery-is-conservative-idempotent-and-never-retries
  (let [store (fixture (assoc on :max-active 4) {})]
    (running! store "root" "a")
    (e/admit-call! store "run" "a" "qa" 100 0.0)
    (running! store "root" "b")
    (e/spawn! store "run" "root" {:id "c" :task "t"})
    (running! store "root" "d")
    (c/update-run! store "run" #(e/worker-lease % "d" :open 0))
    (e/finish! store "run" "d" :completed {:summary "done"})
    ;; The controller process dies here. A new one opens the durable ledger.
    (e/recover! store "run")
    (let [r (ledger store)]
      (is (= {"a" :unknown "b" :orphaned "c" :orphaned "d" :completed}
             (into {} (map (fn [[k v]] [k (:state v)]) (e/children r)))))
      (is (= :unknown (get-in r [:elastic :requests "qa" :status])))
      (is (= 100 (get-in r [:reserved :tokens])))
      (is (= :unconfirmed (:worker (e/child r "d"))))
      (is (= :controller-restart (get-in r [:elastic :halted :reason])))
      ;; Nothing is retried: still the one admitted call.
      (is (= 1 (count (events r :elastic-call-admitted))))
      (e/recover! store "run")
      (is (= r (ledger store))))))

(deftest deadlines-terminal-monotonicity-and-bounded-collection
  (let [store (fixture (assoc on :child-wall-ms 1000) {})
        t0 (System/currentTimeMillis)
        r (-> (ledger store) (e/spawn "root" {:id "a" :task "t"} t0) (e/start "a" t0)
              (e/spawn "root" {:id "b" :task "t"} t0) (e/start "b" t0)
              (e/admit-call "b" "qb" 10 0.0 (+ t0 10)))]
    (is (= :child-deadline (denial #(e/admit-call r "a" "late" 10 0.0 (+ t0 1000)))))
    (let [r (e/expire r (+ t0 1000))]
      (is (= :timed-out (:state (e/child r "a"))))
      (is (= :cancelling (:state (e/child r "b"))))
      (let [r (e/settle-call r "qb" (receipt 5) (+ t0 1100))
            r (e/finish r "a" :completed {:summary "too late"} (+ t0 1200))]
        (is (= :timed-out (:state (e/child r "b"))))
        (is (= :timed-out (:state (e/child r "a"))))
        (is (nil? (:result (e/child r "a"))))
        (is (= 1 (count (events r :elastic-late-result-discarded))))))
    (is (= "Child finished with a provider call in flight"
           (denial #(e/finish r "b" :completed {:summary "x"} (+ t0 20))))))
  (let [store (fixture)]
    (running! store "root" "a")
    (running! store "a" "b")
    (is (= {:status :pending :state :running} (select-keys (e/collect! store "run" "root" "a") [:status :state])))
    (is (= :not-parent (denial #(e/collect! store "run" "root" "b"))))
    (is (= :not-parent (denial #(e/status store "run" "b" "a"))))
    (e/cancel! store "run" "a" "b")
    (e/finish! store "run" "a" :completed {:summary "twenty-six characters long"})
    (e/finish! store "run" "a" :failed {:error "second end"})
    (let [v (e/collect! store "run" "root" "a")]
      (is (= :completed (:state v)))
      (is (= {:summary "twenty-six chara" :chars 26 :sha256 (u/sha "twenty-six characters long") :truncated true} (:result v)))
      (is (true? (:collected v)))
      (is (= v (e/collect! store "run" "root" "a")))
      (is (= 1 (count (events (ledger store) :elastic-collected)))))))

;; ---------------------------------------------------------------------------
;; Executor, with stub workers and scripted providers.

(defn- executor [store]
  (let [opened (atom []) closed (atom [])]
    {:store store :run "run" :tasks (atom {}) :leases (atom {}) :opened opened :closed closed
     :open-worker (fn [id] (swap! opened conj id) {:worker id})
     :close-worker (fn [w] (swap! closed conj (:worker w)))}))
(defn- scripted [tokens] (fn [] (receipt tokens)))

(deftest the-executor-runs-children-concurrently-and-always-closes-their-workers
  (let [store (fixture (assoc on :max-active 3) {}) env (executor store)]
    (doseq [id ["ok" "boom" "greedy"]] (e/spawn! store "run" "root" {:id id :task (str id " task")}))
    (e/launch! env "ok" (fn [{:keys [call! task]}] (call! 10 0.0 (scripted 5)) (call! 10 0.0 (scripted 5)) {:summary (str "did " task)}))
    (e/launch! env "boom" (fn [{:keys [call!]}] (call! 10 0.0 (scripted 5)) (throw (ex-info "model program failed" {}))))
    (e/launch! env "greedy" (fn [{:keys [call!]}] (loop [] (call! 10 0.0 (scripted 5)) (recur))))
    (is (= [:completed :failed :budget-exhausted] (mapv #(e/await-child env % 5000) ["ok" "boom" "greedy"])))
    (let [r (ledger store)]
      (is (= {"ok" :completed "boom" :failed "greedy" :budget-exhausted}
             (into {} (map (fn [[k v]] [k (:state v)]) (e/children r)))))
      (is (= "did ok task" (get-in (e/child r "ok") [:result :summary])))
      (is (= 7 (get-in r [:spent :calls])))
      (is (= (sort @(:opened env)) (sort @(:closed env)) ["boom" "greedy" "ok"]))
      (is (every? #(= :closed (:worker %)) (vals (e/children r))))
      (is (empty? @(:leases env))))))

(deftest executor-failure-modes-unknown-outcome-timeout-cancel-and-parent-exit
  (testing "a transport failure after dispatch is an unknown outcome, never retried"
    (let [store (fixture) env (executor store) attempts (atom 0)]
      (e/spawn! store "run" "root" {:id "a" :task "t"})
      (e/launch! env "a" (fn [{:keys [call!]}] (call! 10 0.0 #(do (swap! attempts inc) (throw (ex-info "connection reset" {}))))))
      (is (= :failed (e/await-child env "a" 5000)))
      (let [r (ledger store)]
        (is (= 1 @attempts))
        (is (= :unknown (state store "a")))
        (is (= 1 (get-in r [:reserved :calls])))
        (is (= :closed (:worker (e/child r "a"))))
        (is (= 1 (count (events r :elastic-late-result-discarded)))))))
  (testing "a receipt that cannot be charged is also unknown"
    (let [store (fixture) env (executor store)]
      (e/spawn! store "run" "root" {:id "a" :task "t"})
      (e/launch! env "a" (fn [{:keys [call!]}] (call! 10 0.0 (fn [] {:tokens -1 :usd 0.0}))))
      (e/await-child env "a" 5000)
      (is (= :unknown (state store "a")))))
  (testing "a refused dispatch is released and the body fails"
    (let [store (fixture) env (executor store)]
      (e/spawn! store "run" "root" {:id "a" :task "t"})
      (e/launch! env "a" (fn [{:keys [call!]}] (call! 10 0.0 #(throw (ex-info "admission refused" {:outcome :not-dispatched})))))
      (e/await-child env "a" 5000)
      (is (= [:failed 0] [(state store "a") (get-in (ledger store) [:reserved :calls])]))))
  (testing "the watchdog times out a hung child; its late result is discarded and its worker closed once"
    (let [store (fixture (assoc on :child-wall-ms 150) {}) env (executor store) release (promise)]
      (e/spawn! store "run" "root" {:id "a" :task "t"})
      (e/launch! env "a" (fn [_] @release {:summary "late"}))
      (Thread/sleep 300)
      (e/sweep! env)
      (is (= :timed-out (state store "a")))
      (is (= ["a"] @(:closed env)))
      (deliver release true)
      (e/await-child env "a" 5000)
      (is (= :timed-out (state store "a")))
      (is (= ["a"] @(:closed env)))))
  (testing "cancel during a call in flight: the call completes and is charged, then the child is cancelled"
    (let [store (fixture) env (executor store) reply (promise) in-call (promise)]
      (e/spawn! store "run" "root" {:id "a" :task "t"})
      (e/launch! env "a" (fn [{:keys [call!]}]
                           (call! 10 0.0 #(do (deliver in-call true) @reply))
                           (call! 10 0.0 (scripted 1))
                           {:summary "never"}))
      @in-call
      (e/cancel-child! env "root" "a")
      (is (= :cancelling (state store "a")))
      (deliver reply (receipt 8))
      (e/await-child env "a" 5000)
      (let [r (ledger store)]
        (is (= :cancelled (state store "a")))
        (is (= [1 8] [(get-in r [:spent :calls]) (get-in r [:spent :tokens])]))
        (is (nil? (:result (e/child r "a"))))
        (is (= ["a"] @(:closed env))))))
  (testing "parent exit leaves no active child and no open worker"
    (let [store (fixture (assoc on :max-active 3) {}) env (executor store) stuck (promise) idle (promise)]
      (e/spawn! store "run" "root" {:id "calling" :task "t"})
      (e/spawn! store "run" "root" {:id "idle" :task "t"})
      (e/spawn! store "run" "root" {:id "queued" :task "t"})
      (e/launch! env "calling" (fn [{:keys [call!]}] (call! 10 0.0 #(deref stuck)) {:summary "x"}))
      (e/launch! env "idle" (fn [{:keys [stopping?]}] (loop [] (when-not (stopping?) (Thread/sleep 10) (recur))) @idle {:summary "y"}))
      (Thread/sleep 100)
      (let [report (e/shutdown! env "root" 300)
            r (ledger store)]
        (is (= {:active [] :unknown ["calling"] :open-leases []} report))
        (is (= {"calling" :unknown "idle" :cancelled "queued" :cancelled}
               (into {} (map (fn [[k v]] [k (:state v)]) (e/children r)))))
        (is (= #{"calling" "idle"} (set @(:closed env))))
        (is (= :unknown (get-in r [:elastic :requests (first (keys (get-in r [:elastic :requests]))) :status])))
        (deliver stuck (receipt 1)) (deliver idle true)))))
