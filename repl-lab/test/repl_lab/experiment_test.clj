(ns repl-lab.experiment-test
  (:require [clojure.test :refer :all] [repl-lab.runtime-test :refer [fixture temp-root config]]
            [repl-lab.controller :as c] [repl-lab.runtime :as runtime] [repl-lab.provider :as provider]
            [repl-lab.artifact :as a] [repl-lab.bundle :as bundle] [repl-lab.fixtures :as f]
            [repl-lab.experiment :as experiment] [repl-lab.util :as u] [repl-lab.live :as live]
            [repl-lab.evaluation :as evaluation] [repl-lab.sim :as sim] [repl-lab.workloads :as workloads]))

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

(deftest frozen-has-temporary-code-and-no-cross-task-retention
  (let [root (temp-root)
        p (provider/->FixtureProvider
            (atom {"root" [{:op :policy/use :source (:source f/packed-policy)}
                            {:op :done :summary "Use temporary fixture policy"}
                            {:op :done :summary "Fresh task uses approved initial policy"}]
                   "analyst" [{:op :done :summary "Selected context received"}
                              {:op :done :summary "Selected context received"}]}))
        env {:root root :id "parity" :config config :provider p :provenance :synthetic-fixture
             :execute (fn [artifact world]
                        (sim/run-episode world (cond (= (:forms artifact) f/packed-form) f/packed
                                                    (= (:forms artifact) f/serial-form) f/serial
                                                    :else (throw (ex-info "Unknown trusted test fixture" {}))) {}))}
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
