(ns repl-lab.sim-test
  (:require [clojure.test :refer :all] [repl-lab.sim :as s] [repl-lab.baselines :as b]
            [repl-lab.workloads :as w] [repl-lab.util :as u] [repl-lab.limits :as limits]))

(def world {:horizon 40 :workers [{:id "w" :capacity {:cpu 1} :speed 1}]
            :jobs [{:id "a" :deps [] :resources {:cpu 1} :estimate 4 :actual 4 :delay 0}
                   {:id "b" :deps ["a"] :resources {:cpu 1} :estimate 2 :actual 2 :delay 0}] :faults []})
(defn act [st a] (:state (s/step st a)))
(def dispatch {:op :dispatch :job "a" :worker "w"})

(deftest dependencies-and-atomic-rejection
  (let [st (s/initial-state world) running (act st dispatch)]
    (doseq [a [{:op :dispatch :job "b" :worker "w"} {:op :completion :job "a"}
               {:op :dispatch :job "a" :worker "missing"} {:op :wait :ticks 0}
               {:op :wait :ticks 51} {:op :dispatch :job "a" :worker "w" :actual 0} nil]]
      (let [r (s/step st a)] (is (false? (:accepted r))) (is (= st (:state r)))))
    (is (= :not-ready (:error (s/step running dispatch))))
    (is (empty? (s/check-invariants running)))
    (is (= :committed (get-in (act running {:op :wait :ticks 4}) [:jobs "a" :status])))))

(deftest stale-completion-cannot-release-new-attempt
  (let [world (assoc world :faults [{:type :failure :at 2 :worker "w"} {:type :recover :at 3 :worker "w"}])
        st (-> (s/initial-state world) (act dispatch) (act {:op :wait :ticks 3}) (act dispatch))
        stale (act st {:op :wait :ticks 1})]
    (is (= 1 (get-in stale [:metrics :stale-events])))
    (is (= { :cpu 1} (get-in stale [:workers "w" :used])))
    (is (= "a1" (get-in stale [:jobs "a" :attempt])))
    (is (= :running (get-in stale [:jobs "a" :status])))
    (is (empty? (s/check-invariants stale)))
    (is (= 1 (get-in (act stale {:op :wait :ticks 3}) [:jobs "a" :commits])))))

(deftest failure-wins-ties-and-delivery-can-be-late
  (let [world (-> world (assoc :faults [{:type :failure :at 4 :worker "w"} {:type :recover :at 4 :worker "w"}]))
        st (-> (s/initial-state world) (act dispatch) (act {:op :wait :ticks 4}))]
    (is (= :pending (get-in st [:jobs "a" :status])))
    (is (= 1 (get-in st [:metrics :stale-events])))
    (is (= [:dispatch :attempt-failed :failure :recover :stale-completion] (mapv :type (:history st)))))
  (let [delayed (assoc-in world [:jobs 0 :delay] 5)
        st (-> (s/initial-state delayed) (act dispatch) (act {:op :wait :ticks 4}))]
    (is (= :running (get-in st [:jobs "a" :status])))
    (is (= :committed (get-in (act st {:op :wait :ticks 5}) [:jobs "a" :status])))))

(deftest impossible-deadlock-and-budgets
  (is (= :impossible (:status (s/initial-state (assoc-in world [:jobs 0 :deps] ["b"])))))
  (is (= :impossible (:status (s/initial-state (assoc-in world [:jobs 0 :resources] {:cpu 2})))))
  (is (= :deadlock (get-in (s/run-episode (assoc world :faults [{:type :failure :at 0 :worker "w"}]) b/fifo {}) [:metrics :status])))
  (is (= :horizon (get-in (s/run-episode world (fn [_ m] {:actions [{:op :wait :ticks 50}] :memory m}) {}) [:metrics :status])))
  (is (= :event-budget (get-in (s/run-episode world (fn [_ m] {:actions [dispatch] :memory m}) {:event-budget 5}) [:metrics :status])))
  (is (thrown? Exception (s/initial-state (assoc-in world [:jobs 0 :actual] 0)))))

(deftest observation-is-a-whitelist
  (let [obs (s/observe (s/initial-state (assoc world :seed 99 :faults [{:type :failure :at 3 :worker "w"}])) nil)]
    (is (= #{:time :horizon :jobs :workers :history} (set (keys obs))))
    (is (not-any? #(contains? % :actual) (:jobs obs)))
    (is (not-any? #(contains? % :delay) (:jobs obs)))
    (is (= [] (:history obs)))))

(deftest deterministic-panels-and-replay
  (doseq [seed (range 30) policy [b/fifo b/estimate-aware]]
    (let [world (w/generate seed {:size (+ 3 (mod seed 13)) :fault-count 3 :resource-mix true})
          a (s/run-episode world policy {}) b (s/run-episode world policy {})]
      (is (s/feasible? world))
      (is (= :complete (get-in a [:metrics :status])))
      (is (empty? (s/check-invariants (:state a))))
      (is (= (:final-hash a) (:final-hash b)))
      (is (= (:state a) (s/replay world (:records a) (:final-hash a) (get-in a [:metrics :status])))))))

(deftest replay-detects-tampering
  (let [run (s/run-episode world b/fifo {})]
    (is (thrown? Exception (s/replay world (assoc-in (:records run) [1 :after] "wrong") (:final-hash run) :complete)))))

(deftest event-budget-is-enforced-inside-action-batches-and-waits
  (let [run (s/run-episode world (fn [_ m] {:actions (vec (repeat 128 dispatch)) :memory m}) {:event-budget 4})]
    (is (= :event-budget (get-in run [:metrics :status])))
    (is (= 4 (+ (get-in run [:metrics :policy-calls]) (get-in run [:state :steps])
                 (get-in run [:metrics :rejected-actions]) (get-in run [:metrics :world-events]))))
    (is (= (:state run) (s/replay world (:records run) (:final-hash run) :event-budget))))
  (let [faults (mapv (fn [i] {:type (if (odd? i) :recover :failure) :worker "w" :at (inc i)}) (range 10))
        world (assoc world :faults faults)
        run (s/run-episode world (fn [_ m] {:actions [{:op :wait :ticks 50}] :memory m}) {:event-budget 3})]
    (is (= :event-budget (get-in run [:metrics :status])))
    (is (= 1 (get-in run [:metrics :world-events])))
    (is (= (:state run) (s/replay world (:records run) (:final-hash run) :event-budget)))))

(deftest wall-deadline-discards-late-policy-response-and-replays
  (let [clock (atom 0)
        run (with-redefs [limits/now-ms #(deref clock)]
              (s/run-episode world (fn [_ memory] (reset! clock 6) {:actions [dispatch] :memory memory})
                             {:event-budget 100 :deadline-ms 5}))]
    (is (= :wall-budget (get-in run [:metrics :status])))
    (is (= 1 (get-in run [:metrics :policy-calls])))
    (is (empty? (get-in run [:state :attempts])))
    (is (= (:state run) (s/replay world (:records run) (:final-hash run) :wall-budget)))))

(deftest wall-deadline-stops-an-action-batch
  (let [clock (atom 0) original-step s/step
        run (with-redefs [limits/now-ms #(deref clock)
                          s/step (fn [& args] (let [result (apply original-step args)] (reset! clock 6) result))]
              (s/run-episode world (fn [_ memory] {:actions [dispatch {:op :wait :ticks 10}] :memory memory})
                             {:event-budget 100 :deadline-ms 5}))]
    (is (= :wall-budget (get-in run [:metrics :status])))
    (is (= 1 (get-in run [:state :steps])))
    (is (zero? (get-in run [:metrics :completed])))
    (is (= (:state run) (s/replay world (:records run) (:final-hash run) :wall-budget)))))
