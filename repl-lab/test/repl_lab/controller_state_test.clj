(ns repl-lab.controller-state-test
  "Terminal-state and request-recovery invariants of the durable ledger, including
  racing finishes and a simulated process restart. Real SQLite store; no inference."
  (:require [clojure.test :refer :all] [repl-lab.controller :as c]
            [repl-lab.runtime-test :refer [temp-root config]]))

(defn- fresh-run []
  (let [store (str (temp-root) "/controller.sqlite")]
    (c/create-run! store "run" (update config :limits merge {:usd 10 :calls 20}) nil)
    (c/session! store "run" "root" nil)
    store))

(defn- status [store id] (get-in (c/get-run store "run") [:sessions id :status]))
(defn- events [store kind] (filter #(= kind (:type %)) (:events (c/get-run store "run"))))

(deftest a-terminal-status-is-never-rewritten
  (let [store (fresh-run)]
    (c/finish-session! store "run" "root" :complete {:summary "6"})
    (c/finish-session! store "run" "root" :failed {:error "late failure"})
    (is (= :complete (status store "root")))
    (is (= [{:id "root" :status :failed :current :complete}] (map :payload (events store :session-finish-refused))))
    (is (= 1 (count (events store :session-finished))))))

(deftest an-unknown-outcome-is-not-masked-by-a-later-finish-or-cancel
  (let [store (fresh-run)]
    (c/session! store "run" "child" "root")
    (c/reserve! store "run" "q1" "child" 100 0.1)
    (c/recover! store "run" "q1")
    (is (= :unknown (status store "child")))
    ;; The failure handler's finish and a parent cancel both arrive later.
    (c/finish-session! store "run" "child" :failed {:error "provider failed"})
    (c/cancel! store "run" "root")
    (is (= :unknown (status store "child")))
    (is (= :cancelled (status store "root")))
    (is (= {:calls 1 :tokens 100 :usd 0.1} (select-keys (:reserved (c/get-run store "run")) [:calls :tokens :usd])))))

(deftest a-per-call-failure-leaves-concurrent-sibling-calls-alone
  (let [store (fresh-run)]
    (c/session! store "run" "a" "root")
    (c/session! store "run" "b" "root")
    (c/reserve! store "run" "qa" "a" 100 0.1)
    (c/reserve! store "run" "qb" "b" 100 0.1)
    ;; Session a's call fails; b's call is still in flight and later completes.
    (c/recover! store "run" "qa")
    (is (= :unknown (get-in (c/get-run store "run") [:provider-requests "qa" :status])))
    (is (= :pending (get-in (c/get-run store "run") [:provider-requests "qb" :status])))
    (is (= :calling (status store "b")))
    (c/reconcile! store "run" "qb" {:tokens 40 :usd 0.02 :model "m"})
    (is (= :ready (status store "b")))
    (is (= [{:request-id "qa"}] (map :payload (events store :provider-outcome-unknown))))
    ;; Recovering an already-settled or unknown request id changes nothing.
    (let [before (c/get-run store "run")]
      (c/recover! store "run" "qb")
      (c/recover! store "run" "missing")
      (is (= (:provider-requests before) (:provider-requests (c/get-run store "run")))))))

(deftest restart-recovery-marks-every-pending-call-unknown-and-reconciles-once
  (let [store (fresh-run)]
    (c/session! store "run" "a" "root")
    (c/reserve! store "run" "qa" "root" 100 0.1)
    (c/reserve! store "run" "qb" "a" 100 0.1)
    ;; A new process finds both calls pending: no call can still be in flight.
    (c/recover! store "run")
    (is (= #{:unknown} (set (map :status (vals (:provider-requests (c/get-run store "run")))))))
    ;; A late receipt is charged exactly once; a second copy is refused.
    (c/reconcile! store "run" "qa" {:tokens 30 :usd 0.03 :model "m"})
    (is (thrown? Exception (c/reconcile! store "run" "qa" {:tokens 30 :usd 0.03 :model "m"})))
    (is (= 1 (get-in (c/get-run store "run") [:spent :calls])))))

(deftest racing-finishes-settle-on-exactly-one-terminal-status
  (dotimes [_ 5]
    (let [store (fresh-run)
          start (promise)
          racers (doall (for [s [:complete :failed :cancelled]]
                          (future @start (c/finish-session! store "run" "root" s {:by s}))))]
      (deliver start true)
      (run! deref racers)
      (is (= 1 (count (events store :session-finished))))
      (is (= 2 (count (events store :session-finish-refused))))
      (is (= (:status (:payload (first (events store :session-finished)))) (status store "root"))))))
