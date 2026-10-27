(ns repl-lab.experiment-test
  (:require [clojure.test :refer :all] [repl-lab.runtime-test :refer [fixture temp-root config]]
            [repl-lab.controller :as c] [repl-lab.runtime :as runtime] [repl-lab.provider :as provider]
            [repl-lab.artifact :as a] [repl-lab.bundle :as bundle] [repl-lab.fixtures :as f]
            [repl-lab.experiment :as experiment] [repl-lab.util :as u] [repl-lab.live :as live]
            [repl-lab.evaluation :as evaluation] [repl-lab.sim :as sim] [repl-lab.workloads :as workloads]
            [repl-lab.isolation :as isolation]))

(deftest recursive-transport-fixture-and-parent-consumption
  (let [[root store] (fixture)
        p (provider/->FixtureProvider
            (atom {"root" [{:op :agent/call :id "child" :task "Compute summary" :context [{:id "j1"}]}
                            {:op :done :summary "Consumed child summary"}]
                   "child" [{:op :done :summary "One selected job"}]}))
        result (runtime/run-session! {:store store :run "run" :registry root :provider p :workers (atom {}) :allow-learning false} "root" {})
        state (c/get-run store "run")]
    (is (= "Consumed child summary" (:summary result)))
    (is (= 3 (get-in state [:spent :calls])))
    (is (= "root" (get-in state [:sessions "child" :parent])))
    (is (some #(= :child-result-consumed (:type %)) (:events state)))
    (is (every? #(= :synthetic-fixture (get-in % [:payload :response :provenance]))
                (filter #(= :fixture-provider-call (:type %)) (:events state))))))

(deftest resumed-child-retains-worker-until-root-finishes
  (let [[root store] (fixture) opened (atom 0) closed (atom 0) workers (atom {})
        p (provider/->FixtureProvider
            (atom {"root" [{:op :agent/call :id "child" :task "First" :context []}
                            {:op :agent/call :id "child" :task "Resume" :context []}
                            {:op :done :summary "Task complete"}]
                   "child" [{:op :repl/eval :source "fixture write" :bindings {}}
                             {:op :done :summary "Binding set"}
                             {:op :repl/eval :source "fixture read" :bindings {}}
                             {:op :done :summary "Binding retained"}]}))]
    (with-redefs [isolation/open-session! (fn [_] (swap! opened inc) (atom nil))
                  isolation/evaluate! (fn [worker source _]
                                        (if (= source "fixture write") (reset! worker 42)
                                          (do (is (= 42 @worker)) @worker)))
                  isolation/close-session! (fn [_] (swap! closed inc))]
      (runtime/run-session! {:store store :run "run" :registry root :provider p :workers workers :allow-learning false} "root" {}))
    (is (= 1 @opened)) (is (= 1 @closed)) (is (empty? @workers))))

(deftest nested-subagents-message-without-root-forwarding
  (let [[root store] (fixture)
        p (provider/->FixtureProvider
            (atom {"root" [{:op :agent/call :id "a" :task "Delegate a selected subset" :context [{:id "selected"}]}
                            {:op :done :summary "Consumed delegated result"}]
                   "a" [{:op :agent/call :id "b" :task "Check selected evidence" :context [{:id "selected"}]}
                          {:op :message/receive} {:op :done :summary "Consumed message from b"}]
                   "b" [{:op :message/send :recipient "a" :correlation-id "analysis" :payload {:finding "Selected item checked"}}
                          {:op :done :summary "Direct message sent"}]}))]
    (runtime/run-session! {:store store :run "run" :registry root :provider p :workers (atom {}) :allow-learning false} "root" {})
    (let [ledger (c/get-run store "run")
          direct (filter #(and (= "b" (:sender %)) (= "a" (:recipient %))) (vals (:mailbox ledger)))]
      (is (= 7 (get-in ledger [:spent :calls])))
      (is (= 2 (get-in ledger [:sessions "b" :depth])))
      (is (= 1 (count direct)))
      (is (= :acked (:status (first direct))))
      (is (every? #(= :complete (:status %)) (vals (:sessions ledger)))))))

(deftest broker-fixed-authority-and-peer-messages
  (let [[root store] (fixture) env {:store store :run "run" :registry root :workers (atom {}) :allow-learning false}]
    (c/session! store "run" "a" "root") (c/session! store "run" "b" "root")
    (runtime/broker! env "a" {:op :message/send :recipient "b" :correlation-id "peer" :payload {:count 2}})
    (is (= "a" (:sender (first (:messages (runtime/broker! env "b" {:op :message/receive}))))))
    (is (thrown? Exception (runtime/broker! env "a" {:op :message/send :sender "root" :recipient "b" :correlation-id "bad" :payload {}})))
    (is (thrown? Exception (runtime/broker! env "root" {:op :artifact/promote :hash "x"})))
    (is (thrown? Exception (runtime/broker! env "root" {:op :artifact/submit :category :policy :source "(fn [a b] {})"
                                                       :interface {:name "decide" :arity 2} :dependencies [] :parent "initial"})))
    (is (thrown? Exception (runtime/broker! env "a" {:op :agent/cancel :id "b"})))))

(deftest bundle-whitelist-and-cold-resolution
  (let [root (temp-root) output (str root "/export")]
    (doseq [artifact [f/packed-policy f/improved-workflow]] (a/save! root artifact))
    (let [manifest (bundle/export! root output (:hash f/improved-workflow) :synthetic-fixture)
          loaded (bundle/load-bundle output)]
      (is (= 2 (:artifact-count manifest)))
      (is (= (:hash f/packed-policy) (:hash (experiment/bundle-policy loaded))))
      (let [fresh (evaluation/restore-library loaded)
            workflow (:active fresh) policy-hash (get-in workflow [:forms :strategy :policy])
            policy (get-in fresh [:by-hash policy-hash])]
        (is (= [policy-hash] (:dependencies workflow)))
        (is (= f/packed-form (:forms policy)))
        (is (= :developer-fixture (:provenance policy)))
        (doseq [artifact (vals (:by-hash fresh))] (a/save! root artifact))
        (is (= policy (a/load! root policy-hash))))
      (is (not (contains? (:artifacts loaded) (:hash f/initial-policy)))))
    (spit (str output "/transcript.txt") "not allowed")
    (is (thrown? Exception (bundle/load-bundle output))))
  (let [root (temp-root) output (str root "/export")]
    (doseq [artifact [f/packed-policy f/improved-workflow]] (a/save! root artifact))
    (bundle/export! root output (:hash f/improved-workflow) :synthetic-fixture)
    (spit (str output "/" (:hash f/packed-policy) ".edn") "{}")
    (is (thrown? Exception (bundle/load-bundle output))))
  (let [root (temp-root) output (str root "/export")]
    (doseq [artifact [f/packed-policy f/improved-workflow]] (a/save! root artifact))
    (bundle/export! root output (:hash f/improved-workflow) :synthetic-fixture)
    (let [loaded (bundle/load-bundle output)
          tampered (assoc-in loaded [:artifacts (:hash f/packed-policy) :forms] '(fn [a b] nil))]
      (is (thrown? Exception (experiment/bundle-policy tampered))))))

(deftest workflow-changes-actual-selection
  (let [[root store] (fixture) observed (atom nil)]
    (c/put-context! store "run" "jobs" [{:id "blocked" :ready false} {:id "ready" :ready true :estimate 2}])
    (runtime/workflow! store "run" f/improved-workflow "jobs" (fn [_ rows] (reset! observed rows) {:summary :fixture}))
    (is (= ["ready"] (mapv :id @observed)))
    (is (= :workflow-invoked (:type (last (:events (c/get-run store "run"))))))))

(deftest no-implicit-paid-calls
  (doseq [env [{} {"LIVE" "1"} {"LIVE" "1" "MODEL" "m" "MAX_USD" "0"}
               {"LIVE" "1" "MODEL" "m" "MAX_USD" "NaN"}
               {"LIVE" "1" "MODEL" "latest" "MAX_USD" "1"}]]
    (is (thrown? Exception (live/options env)))))

(deftest worker-limits-must-match-the-experiment
  (let [check {:ready true :limits {:memory_mb 256 :cpus 1 :pids 32 :scratch_mb 8 :wall_seconds 10 :output_bytes 65536}}]
    (is (:ready (isolation/verify-limits check (:isolation config))))
    (is (false? (:ready (isolation/verify-limits check (assoc (:isolation config) :memory-mb 512)))))))

(deftest recorded-provider-playback-requires-exact-input-and-never-charges-again
  (let [[_ store] (fixture) messages [{:role "user" :content "Labeled fixture input"}]
        original {:text "{:op :done :summary \"Recorded fixture\"}" :tokens 20 :usd 0.2 :model "fixture"}
        entries [{:session "root" :input-hash (u/hash-value messages) :response original :request-id "old"}]
        adapter (provider/->PlaybackProvider (atom entries))]
    (is (thrown? Exception (provider/invoke! adapter store "run" "root" [])))
    (let [response (provider/invoke! adapter store "run" "root" messages)]
      (is (= (:text original) (:text response)))
      (is (= :recorded-response-playback (:provenance response)))
      (is (= 0.2 (get-in response [:recorded-usage :usd])))
      (is (zero? (get-in (c/get-run store "run") [:spent :usd]))))
    (is (thrown? Exception (provider/invoke! adapter store "run" "root" messages)))))

(deftest frozen-has-temporary-code-and-no-cross-task-retention
  (let [root (temp-root)
        p (provider/->FixtureProvider
            (atom {"root" [{:op :policy/use :source (:source f/packed-policy)}
                            {:op :done :summary "Use temporary fixture policy"}
                            {:op :done :summary "Fresh task uses approved initial policy"}]
                   "analyst" [{:op :done :summary "Selected context received"}
                              {:op :done :summary "Selected context received"}]}))
        env {:root root :id "parity" :config config :provider p :provenance :synthetic-fixture
             :execute (fn [artifact world options]
                        (sim/run-episode world (cond (= (:forms artifact) f/packed-form) f/packed
                                                    (= (:forms artifact) f/serial-form) f/serial
                                                    :else (throw (ex-info "Unknown trusted test fixture" {}))) options))}
        world (workloads/generate 777 {:size 5})
        first (evaluation/episode! env "frozen" 0 world f/initial-workflow f/initial-policy)
        second (evaluation/episode! env "frozen" 1 world f/initial-workflow f/initial-policy)]
    (is (= :complete (get-in first [:metrics :status])))
    (is (not= (:hash f/initial-policy) (:artifact first)))
    (is (= (:hash f/initial-policy) (:artifact second)))
    (is (= (:world first) (:world second)))
    (is (= 3 (get-in first [:usage :spent :calls])))
    (is (= 2 (get-in second [:usage :spent :calls])))))

(deftest parser-depth-and-dispatch-limits
  (is (= {:mvn/version "1.11.3"} (u/read-edn "#:mvn{:version \"1.11.3\"}")))
  (is (thrown? Exception (a/parse-source (str (apply str (repeat 100 "(")) "x" (apply str (repeat 100 ")"))))))
  (is (thrown? Exception (a/parse-source "#_ #_ #_ 1 2 3 4")))
  (is (= '(fn [x] "#_ is a string") (a/parse-source "(fn [x] \"#_ is a string\")"))))

(defn trusted-execute [artifact world & extra]
  ;; This test never evaluates submitted source in the controller JVM.
  (sim/run-episode world (cond (= (:forms artifact) f/packed-form) f/packed
                              (= (:forms artifact) f/serial-form) f/serial
                              :else (throw (ex-info "Unknown trusted test fixture" {})))
                   (if (map? (last extra)) (last extra) {})))

(deftest development-run-honors-configured-event-budget
  (let [[root store] (fixture) seen (atom nil) world (workloads/generate 996 {:size 3})]
    (a/save! root f/initial-policy)
    (c/update-run! store "run" #(assoc-in % [:config :limits :event-budget] 2))
    (let [result (live/development-panel! store "run" root (:hash f/initial-policy) [world]
                                         (fn [artifact world dependencies options]
                                           (reset! seen options) (trusted-execute artifact world dependencies options)))]
      (is (= 2 (:event-budget @seen)))
      (is (= (+ (:started-ms (c/get-run store "run")) (get-in config [:limits :wall-ms])) (:deadline-ms @seen)))
      (is (= :event-budget (:status (first result))))
      (is (= 1 (:replayed (experiment/replay! root)))))))

(deftest final-arms-with-identical-libraries-have-identical-inputs-and-outcomes
  (let [root (temp-root) library (evaluation/fresh-initial-library) workflow (:active library)
        policy (get-in library [:by-hash (get-in workflow [:forms :strategy :policy])])
        p (provider/->FixtureProvider (atom {"root" (vec (repeat 2 {:op :done :summary "Use approved fixture"}))
                                            "analyst" (vec (repeat 2 {:op :done :summary "Selected fixture evidence"}))}))
        report (evaluation/paired! {:root root :id "equal" :config config :provider p :execute trusted-execute
                                     :provenance :synthetic-fixture}
                                    [(workloads/generate 997 {:size 3})] workflow policy)
        frozen (first (:raw-frozen report)) evolving (first (:raw-evolving report))
        inputs (fn [arm] (mapv #(get-in % [:payload :input])
                               (filter #(= :fixture-provider-call (:type %))
                                       (:events (c/get-run (str root "/sessions/" arm "-0.sqlite") (str "equal-" arm "-0"))))))]
    (is (= (:artifact frozen) (:artifact evolving)))
    (is (= (:workflow frozen) (:workflow evolving)))
    (is (= (:final-hash frozen) (:final-hash evolving)))
    (is (= (:usage frozen) (:usage evolving)))
    (is (= (inputs "frozen") (inputs "evolving")))
    (is (= [0] (get-in report [:paired :deltas])))
    (is (= 2 (:replayed (experiment/replay! root))))))

(deftest direct-skill-removal-keeps-failures-and-replay-evidence
  (let [root (temp-root) worlds [(workloads/generate 998 {:size 5 :structure :independent :fault-count 0})]
        retained (evaluation/code-panel! root "retained-code" worlds f/packed-policy trusted-execute)
        fallback (evaluation/code-panel! root "skill-removed" worlds f/initial-policy trusted-execute)
        failed (evaluation/code-panel! root "failed-code" worlds f/packed-policy
                                        (fn [& _] (throw (ex-info "Staged worker failure" {}))))]
    (is (= :complete (get-in retained [0 :metrics :status])))
    (is (= :complete (get-in fallback [0 :metrics :status])))
    (is (= :execution-failure (get-in failed [0 :metrics :status])))
    (is (zero? (:complete (experiment/summarize failed))))
    (is (= (mapv :case retained) (mapv :case fallback)))
    (is (= 3 (:replayed (experiment/replay! root))))))

(deftest development-records-replay-and-hide-controller-state
  (let [[root store] (fixture) world (workloads/generate 991 {:size 5})]
    (a/save! root f/initial-policy)
    (let [good (live/development-panel! store "run" root (:hash f/initial-policy) [world] trusted-execute)
          bad (live/development-panel! store "run" root (:hash f/initial-policy) [world]
                                      (fn [& _] (throw (ex-info "Test worker unavailable" {}))))
          ledger (c/get-run store "run") contexts (:contexts ledger)
          handles (map :handle (get contexts "trace-index"))]
      (is (= :complete (:status (first good))))
      (is (= :execution-failure (:status (first bad))))
      (is (= 2 (:replayed (experiment/replay! root))))
      (is (= 2 (count (set handles))))
      (is (nil? (:episode ledger)))
      (doseq [row (mapcat #(c/context-records store "run" (contexts %)) handles)]
        (is (not-any? #(contains? row %) [:world :before :after :seed :final-hash])))
      (is (= 2 (get-in ledger [:spent :evaluation-episodes]))))))

(deftest failed-evaluation-is-replayable
  (let [root (temp-root) world (workloads/generate 992 {:size 3})
        p (provider/->FixtureProvider (atom {"analyst" [{:op :done :summary "Fixture child"}]
                                            "root" [{:op :done :summary "Fixture root"}]}))
        record (evaluation/episode! {:root root :id "failure" :config config :provider p :provenance :synthetic-fixture
                                      :execute (fn [& _] (throw (ex-info "Test isolation failure" {})))}
                                     "frozen" 0 world f/initial-workflow f/initial-policy)]
    (is (= :execution-failure (get-in record [:metrics :status])))
    (is (= 1 (:replayed (experiment/replay! root))))
    (is (thrown? Exception (sim/replay world (assoc-in (:records record) [0 :after] "corrupt")
                                      (:final-hash record) :execution-failure)))))

(deftest paired-acquisition-matches-tools-and-retains-only-approved-code
  (let [root (temp-root)
        policy (a/make-artifact (assoc (dissoc f/packed-policy :hash :forms) :author "root"))
        workflow (a/make-artifact (assoc (dissoc f/improved-workflow :hash :forms)
                                   :author "root" :dependencies [(:hash policy)]
                                   :source (pr-str (assoc-in (:forms f/improved-workflow) [:strategy :policy] (:hash policy)))))
        submit (fn [artifact] (assoc (select-keys artifact [:category :source :interface :dependencies :parent]) :op :artifact/submit))
        propose [(submit policy) (submit workflow) {:op :done :summary "Scripted fixture proposal"}]
        p (provider/->FixtureProvider (atom {"root" (vec (concat propose propose
                                                      [{:op :done :summary "Fresh task"} {:op :done :summary "Fresh task"}]))
                                            "analyst" (vec (repeat 4 {:op :done :summary "Selected fixture context"}))}))
        env {:root root :id "matched" :config config :provider p :execute trusted-execute :provenance :synthetic-fixture}
        learning (mapv #(workloads/generate % {:size 5 :structure :independent :fault-count 0}) [100 101])
        development [(workloads/generate 200 {:size 5 :structure :independent :fault-count 0})]
        report (live/paired-acquisition! env learning development)
        task (fn [arm index] (first (filter #(and (= arm (:arm %)) (= index (:index %))) (:tasks report))))]
    (is (= :complete (:status report)))
    (is (= 4 (count (:tasks report))))
    (is (= (:hash workflow) (:active report)))
    (is (= (:hash f/initial-workflow) (:initial (task :frozen 1))))
    (is (= (:hash workflow) (:initial (task :evolving 1))))
    (is (= 1 (count (:promotions (task :frozen 0)))))
    (is (= 1 (count (:promotions (task :evolving 0)))))
    (is (= 12 (get-in report [:spent :calls])))
    (is (= 10 (:replayed (experiment/replay! root))))
    (doseq [item (:tasks report)]
      (let [ledger (c/get-run (str (:root item) "/controller.sqlite") (:id item))]
        (is (= config (:config ledger)))
        (is (some #(= :workflow-invoked (:type %)) (:events ledger)))
        (is (some #(= :child-result-consumed (:type %)) (:events ledger)))))
    (is (thrown? Exception (a/load! (:root (task :frozen 1)) (:hash policy))))
    (is (= report (live/paired-acquisition! env learning development)))
    (u/write-edn! (str root "/final-evaluation-seal.edn") {:reserved true})
    (is (thrown? Exception (live/paired-acquisition! env learning development)))))

(deftest interrupted-task-keeps-unknown-provider-reservation
  (let [root (temp-root) task-root (str root "/tasks/evolving-0") store (str task-root "/controller.sqlite")
        world (workloads/generate 993 {:size 3})]
    (doseq [artifact [f/initial-policy f/initial-workflow]] (a/save! task-root artifact))
    (c/create-run! store "recover-evolving-0" config (:hash f/initial-workflow))
    (c/session! store "recover-evolving-0" "root" nil)
    (c/reserve! store "recover-evolving-0" "uncertain" "root" 1000 0.01)
    (let [result (live/recorded-or-new-task! {:root root :id "recover" :config config :provenance :synthetic-fixture
                                             :execute (fn [& _] (throw (ex-info "Must not execute during recovery" {})))}
                                            :evolving 0 world [] f/initial-workflow)
          ledger (c/get-run store "recover-evolving-0")]
      (is (= :checkpointed (:status result)))
      (is (= :execution-failure (get-in result [:episode :metrics :status])))
      (is (= {:calls 1 :tokens 1000 :usd 0.01} (:reserved result)))
      (is (= :unknown (get-in ledger [:provider-requests "uncertain" :status])))
      (is (= 1 (:replayed (experiment/replay! root)))))))
