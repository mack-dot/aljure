(ns repl-lab.programs-test
  "The programmatic tool bridge, offline: the worker's bridge half (worker/src/repl_lab/bridge.clj)
  runs in a thread over pipes against the controller's real request loop (isolation/request!),
  with a Clojure function standing in for SCI evaluation. No Docker, no model."
  (:require [clojure.test :refer [deftest is testing]] [clojure.string :as str]
            [repl-lab.bridge :as bridge] [repl-lab.isolation :as isolation] [repl-lab.programs :as programs]
            [repl-lab.service-fixture :as service] [repl-lab.controller :as c] [repl-lab.util :as u]
            [repl-lab.model-protocol :as wire] [repl-lab.runtime :as runtime])
  (:import [java.io PipedInputStream PipedOutputStream InputStreamReader OutputStreamWriter BufferedReader BufferedWriter]))

;; ---- a fake worker: the real bridge, a scripted evaluator --------------------------------------

(defn- fake-session
  "A session whose worker thread reads {:source :bindings :tools} lines, evaluates source with
  evaluate (a fn of the source string that may call bridge/tool) under the request's grant, and
  prints {:value} or {:error} exactly as the SCI worker does."
  [evaluate]
  (let [to-worker (PipedOutputStream.) from-worker (PipedOutputStream.)
        worker-in (BufferedReader. (InputStreamReader. (PipedInputStream. to-worker 65536) "UTF-8"))
        worker-out (java.io.PrintWriter. (BufferedWriter. (OutputStreamWriter. from-worker "UTF-8")) true)
        thread (Thread. (fn []
                          (binding [*in* worker-in *out* worker-out]
                            (loop []
                              (when-let [line (read-line)]
                                (let [result (try (let [{:keys [source tools]} (bridge/safe-read line)
                                                        value (bridge/with-grant tools (evaluate source))]
                                                    (bridge/safe-read (pr-str {:value value})))
                                                  (catch Exception e {:error (or (.getMessage e) "failed")}))]
                                  (prn result) (flush))
                                (recur))))))]
    (.start thread)
    {:writer (BufferedWriter. (OutputStreamWriter. to-worker "UTF-8"))
     :reader (BufferedReader. (InputStreamReader. (PipedInputStream. from-worker 65536) "UTF-8"))
     :language :clojure :deadline-ms (+ (System/currentTimeMillis) 60000) :thread thread}))

(defn- stop! [session] (.close ^java.io.Writer (:writer session)) (.join ^Thread (:thread session) 2000))

(def fixture
  {:collections {"issues" (into {} (for [i (range 1 8)]
                                     [(str "i" i) {:status (if (odd? i) "stale" "open") :title (str "Issue " i)}]))}
   :faults {:fail-ids ["i6"] :uncertain-ids ["i3"]}})

(def spec {:tools [{:name "context_query" :max_calls 100}
                   {:name "service_list" :max_calls 100} {:name "service_get" :max_calls 100}
                   {:name "service_update" :max_calls 100 :approval "preapproved"}]
           :max_ops_per_program 20 :max_ops_per_task 50 :max_program_ms 30000 :direct_tools true})

(defn- env
  ([] (env fixture))
  ([fixture]
   (let [root (str (System/getProperty "java.io.tmpdir") "/programs-test-" (System/nanoTime))
         store (str root "/controller.sqlite") run "t"]
     (c/create-run! store run (merge (u/read-file "config/experiment.edn") {:response-envelope wire/tool-envelope-version}) nil)
     (c/session! store run "root" nil)
     (c/put-context-block! store run "context" [{:line 0 :text "alpha"} {:line 1 :text "beta"} {:line 2 :text "gamma"}])
     {:store store :run run :programs (programs/attach spec fixture)})))

(defn- events [env type] (filterv #(= type (:type %)) (:events (c/get-run (:store env) (:run env)))))

(defn- run-program [env session evaluate]
  (programs/run-program! env "root" "(program)" {} (fn [source bindings tools handler]
                                         (isolation/run-program! session source bindings tools handler))))

;; ---- tests -------------------------------------------------------------------------------------

(deftest a_program_performs_many_operations_and_returns_one_value
  (let [env (env)
        program (fn [_] ;; close every stale issue, skipping failures, and report
                  (let [stale (:items (bridge/tool "service_list" {:collection "issues" :where {:status "stale"}}))
                        closed (reduce (fn [acc {:keys [id]}]
                                         (try (bridge/tool "service_update" {:collection "issues" :id id :fields {:status "closed"}
                                                                             :idempotency-key (str "close-" id)})
                                              (conj acc id)
                                              (catch Exception e (conj acc [id (ex-message e)]))))
                                       [] stale)]
                    {:stale (count stale) :closed closed}))
        session (fake-session program)]
    (try
      (let [value (run-program env session program)]
        (is (= 4 (:stale value)))
        ;; i1, i5, i7 close; i3 is applied but uncertain (its error is kept, it is not retried).
        (is (= ["i1" "i5" "i7"] (filterv string? (:closed value))))
        (is (= 1 (count (filter vector? (:closed value)))))
        (is (re-find #"uncertain" (second (first (filter vector? (:closed value))))))
        (is (= "closed" (get-in (service/collections (get-in env [:programs :service])) ["issues" "i3" :status]))
            "the uncertain update was applied once")
        (let [ops (events env :program-op)]
          (is (= 5 (count ops)))
          (is (= [:allowed :allowed :uncertain :allowed :allowed] (mapv (comp :decision :payload) ops)))
          (is (every? #(= "root/program-1" (get-in % [:payload :origin])) ops)))
        (is (= :ok (get-in (first (events env :program-finished)) [:payload :status])))
        (is (= 5 (get-in (first (events env :program-finished)) [:payload :ops]))))
      (finally (stop! session)))))

(deftest denied_tools_budgets_and_malformed_input_are_errors_the_program_can_catch
  (let [env (env)
        program (fn [_]
                  [(try (bridge/tool "service_delete" {:id "i1"}) (catch Exception e (ex-message e)))
                   (try (bridge/tool "service_get" {:collection "issues"}) (catch Exception e (ex-message e)))
                   (try (bridge/tool "service_get" {:collection "issues" :id "i6"}) (catch Exception e (ex-message e)))
                   (try (bridge/tool "service_update" {:collection "issues" :id "i2" :fields {:status "x"}}) (catch Exception e (ex-message e)))
                   (:status (bridge/tool "service_get" {:collection "issues" :id "i2"}))])
        session (fake-session program)]
    (try
      (let [[denied malformed failed no-key ok] (run-program env session program)]
        (is (= "Tool is not authorized: service_delete" denied) "refused in the worker, never on the wire")
        (is (re-find #"service_get input takes" malformed))
        (is (re-find #"Service error 500 on i6" failed))
        (is (re-find #"idempotency-key" no-key))
        (is (= "open" ok))
        ;; Only requests that reached the controller are recorded; the unauthorized name never left
        ;; the worker. decision is the authorization; status is the outcome.
        (is (= [:allowed :allowed :denied :allowed] (mapv (comp :decision :payload) (events env :program-op))))
        (is (= [:error :error :error :ok] (mapv (comp :status :payload) (events env :program-op)))))
      (finally (stop! session)))))

(deftest an_effect_is_not_repeated_under_the_same_key_and_an_uncertain_one_never
  (let [env (env)
        program (fn [_]
                  (let [a (bridge/tool "service_update" {:collection "issues" :id "i1" :fields {:status "closed"} :idempotency-key "k1"})
                        b (bridge/tool "service_update" {:collection "issues" :id "i1" :fields {:status "reopened"} :idempotency-key "k1"})
                        c (try (bridge/tool "service_update" {:collection "issues" :id "i3" :fields {:status "closed"} :idempotency-key "k3"})
                               (catch Exception e (ex-message e)))
                        d (try (bridge/tool "service_update" {:collection "issues" :id "i3" :fields {:status "closed"} :idempotency-key "k3"})
                               (catch Exception e (ex-message e)))]
                    [(:status a) (:status b) c d]))
        session (fake-session program)]
    (try
      (let [[a b c d] (run-program env session program)]
        (is (= "closed" a))
        (is (= "closed" b) "the repeated key returns the first result; the second fields were not applied")
        (is (re-find #"uncertain" c))
        (is (re-find #"not repeated" d))
        (is (= [:allowed :deduplicated :uncertain :uncertain-not-retried] (mapv (comp :decision :payload) (events env :program-op))))
        (is (= 2 (:calls (service/snapshot (get-in env [:programs :service])))) "the service saw two updates and no retry"))
      (finally (stop! session)))))

(deftest the_program_operation_limit_is_enforced_in_the_worker_and_the_task_budget_by_the_controller
  (let [env (env (assoc-in fixture [:faults :rate-limit-every] 5))
        ;; Reads until the program limit stops them; a rate-limited read is counted and retried.
        program (fn [_] (loop [n 0 limited 0]
                          (let [r (try (bridge/tool "service_get" {:collection "issues" :id "i1"}) :ok
                                       (catch Exception e (ex-message e)))]
                            (cond (= :ok r) (recur (inc n) limited)
                                  (re-find #"rate limit" r) (recur (inc n) (inc limited))
                                  :else [n limited r]))))
        session (fake-session program)]
    (try
      (let [[n limited reason] (run-program env session program)]
        (is (= 20 n))
        (is (= 4 limited) "every 5th service call was refused; the program retried")
        (is (= "Program operation limit reached: 20" reason))
        ;; every attempt that reached the wire is recorded
        (is (= 20 (count (events env :program-op))))
        (is (= 4 (count (filter #(re-find #"rate limit" (str (get-in % [:payload :error]))) (events env :program-op))))))
      (let [second-run (run-program env session program)
            third-run (run-program env session program)]
        (is (= [20 4] (take 2 second-run)))
        ;; the task budget is 50: the third program gets 10 operations, then the controller refuses the rest
        (is (= [10 2] (take 2 third-run)))
        (is (= "Program operation limit reached: 10" (last third-run)))
        (is (= 3 (:programs @(get-in env [:programs :state]))))
        (is (= 50 (:ops @(get-in env [:programs :state])))))
      (finally (stop! session)))))

(deftest a_request_without_a_grant_cannot_use_the_bridge
  (let [env (env)
        session (fake-session (fn [_] (try (bridge/tool "service_get" {:collection "issues" :id "i1"}) (catch Exception e (ex-message e)))))]
    (try
      (is (= "No tool capabilities in this evaluation" (isolation/evaluate! session "(ignored)" {})))
      (is (= [] (events env :program-op)))
      (finally (stop! session)))))

(deftest a_large_result_is_refused_before_it_reaches_the_worker
  (let [big (into {} (for [i (range 400)] [(str "r" i) {:title (apply str (repeat 1500 "x"))}]))
        env (assoc-in (env) [:programs :service] (service/open {:collections {"big" big}}))
        program (fn [_] [(try (bridge/tool "service_list" {:collection "big" :limit 50}) :ok (catch Exception e (ex-message e)))
                         (count (:items (bridge/tool "service_list" {:collection "big" :limit 10})))])
        session (fake-session program)]
    (try
      (let [[refused ok] (run-program env session program)]
        (is (re-find #"Tool result too large" refused))
        (is (= 10 ok)))
      (finally (stop! session)))))

(deftest the_grant_refuses_what_the_bridge_does_not_enforce
  (is (thrown-with-msg? Exception #"Unknown tool" (programs/grant {:tools [{:name "shell"}]})))
  (is (thrown-with-msg? Exception #"preapproved" (programs/grant {:tools [{:name "service_update"}]})))
  (is (thrown-with-msg? Exception #"max-ops-per-task must be 1-20000" (programs/grant {:tools [{:name "service_get"}] :max_ops_per_task 50000})))
  (is (thrown-with-msg? Exception #"service fixture" (programs/attach {:tools [{:name "service_get"}]} nil)))
  (let [g (programs/grant {:tools [{:name "context_query"}]})]
    (is (= {:class :read :max-calls 1000} (get-in g [:tools "context_query"])))
    (is (true? (:program-tool g))) (is (false? (:direct-tools g)))))

(deftest model_tools_are_unchanged_without_the_switch_and_typed_with_it
  (let [plain (wire/tool-definitions {})
        with (wire/tool-definitions {:contract {:programs spec}})]
    (is (= ["context_metadata" "context_query" "repl_eval" "agent_call" "done"] (mapv :name plain)))
    (is (= (into (mapv :name plain) ["program_run" "context_query" "service_get" "service_list" "service_update"]) (mapv :name with)))
    (let [update-tool (first (filter #(= "service_update" (:name %)) with))]
      (is (= ["collection" "id" "fields" "idempotency-key"] (get-in update-tool [:input_schema :required])))
      (is (re-find #"an effect" (:description update-tool))))
    (is (re-find #"20 operations per program, 50 per task" (:description (first (filter #(= "program_run" (:name %)) with)))))
    ;; A direct tool call parses to one :tool/call command; program_run to :program/run.
    (let [response (fn [name input] {:stop-reason "tool_use" :content [{:type "tool_use" :id "x" :name name :input input}]})
          config {:contract {:programs spec} :response-envelope wire/tool-envelope-version}]
      (is (= {:op :tool/call :name "service_get" :input {:collection "issues" :id "i1"}}
             (wire/parse-response config (response "service_get" {:collection "issues" :id "i1"}) runtime/schemas)))
      (is (= {:op :program/run :source "(+ 1 2)"} (wire/parse-response config (response "program_run" {:source "(+ 1 2)"}) runtime/schemas)))
      (is (thrown? Exception (wire/parse-response {:response-envelope wire/tool-envelope-version}
                                                  (response "program_run" {:source "(+ 1 2)"}) runtime/schemas))
          "without the switch the tool does not exist"))))

(deftest a_direct_call_shares_the_authorization_and_the_record
  (let [env (env)]
    (is (= {:value {:status "stale" :title "Issue 1" :id "i1"}} (programs/direct! env "root" "service_get" {:collection "issues" :id "i1"})))
    (is (thrown-with-msg? Exception #"not authorized" (programs/direct! env "root" "context_metadata" {:handle "context"})))
    (is (= 1 (count (filter #(= :allowed (get-in % [:payload :decision])) (events env :program-op)))))
    (is (every? #(= "direct" (get-in % [:payload :origin])) (events env :program-op)))
    (is (thrown-with-msg? Exception #"Direct tools are not enabled"
                          (programs/direct! (assoc-in env [:programs :grant :direct-tools] false) "root" "service_get" {:collection "issues" :id "i1"})))))

(deftest context_tools_read_the_task_context_through_the_bridge
  (let [env (env)
        program (fn [_] [(:total (bridge/tool "context_query" {:handle "context" :limit 2 :select [:text]}))
                         (mapv :text (:records (bridge/tool "context_query" {:handle "context" :offset 1 :limit 2 :select [:text]})))])
        session (fake-session program)]
    (try (is (= [3 ["beta" "gamma"]] (run-program env session program)))
         (finally (stop! session)))))
