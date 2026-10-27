(ns repl-lab.skill-discovery-test
  (:require [clojure.test :refer :all] [repl-lab.skill-discovery :as d]
            [repl-lab.sim :as sim] [repl-lab.fixtures :as f]
            [repl-lab.execution :as execution] [repl-lab.executable :as executable]
            [repl-lab.limits :as limits]))

(deftest independent-fixture-evaluator-controls
  (doseq [world (d/cases)]
    (is (empty? (sim/workload-errors world)))
    (let [correct (sim/run-episode world f/packed {:event-budget 10000})
          incorrect (sim/run-episode world (fn [_ m] {:actions [{:op :dispatch :job "missing" :worker "missing"}] :memory m})
                                    {:event-budget 64})]
      (is (= :complete (get-in correct [:metrics :status])))
      (is (zero? (get-in correct [:metrics :accepted-invariant-violations])))
      (is (not= :complete (get-in incorrect [:metrics :status])))
      (is (pos? (get-in incorrect [:metrics :rejected-actions])))))
  (is (= [false false true true]
         (mapv #(contains? (:resources (first (:jobs %))) :gpu) (d/cases)))))

(deftest worker-stage-attribution
  ;; Host functions below are test doubles; no generated source is evaluated here.
  (let [world (first (d/cases)) deadline (+ 120000 (limits/now-ms)) closed (atom 0)
        backend (fn [evaluate] (reify execution/ExecutionBackend
                                (open! [_ _] {})
                                (evaluate! [_ _ source bindings] (evaluate source bindings))
                                (close! [_ _] (swap! closed inc))))]
    (with-redefs [execution/backend (fn [_] (backend (fn [& _] (throw (ex-info "Worker wall-time limit" {})))))]
      (let [r (d/isolated! f/initial-policy nil world deadline)]
        (is (= :startup (:failure-stage r)))
        (is (zero? (:attempted-invocations r)))))
    (with-redefs [execution/backend (fn [_] (backend (fn [& _] 42)))
                  executable/load! (fn [& _] (throw (ex-info "Worker rejected expression" {})))]
      (is (= :code-loading (:failure-stage (d/isolated! f/initial-policy nil world deadline)))))
    (with-redefs [execution/backend (fn [_] (backend (fn [& _] 42))) executable/load! (fn [& _] nil)
                  executable/call! (fn [& _] (throw (ex-info "Worker response timeout" {})))]
      (let [r (d/isolated! f/initial-policy nil world deadline)]
        (is (= :execution (:failure-stage r)))
        (is (= 1 (:attempted-invocations r)))
        (is (zero? (:successful-invocations r)))))
    (with-redefs [execution/backend (fn [_] (backend (fn [& _] 42))) executable/load! (fn [& _] nil)
                  executable/call! (fn [_ _ _ [observation memory]] {:actions [{:op :wait :ticks 50}] :memory memory})]
      (is (= :algorithm (:failure-stage (d/isolated! f/initial-policy nil world deadline)))))
    (is (= 4 @closed))))
