(ns repl-lab.reservation-policy-test
  "Reservation invariants under concurrency, on the controller ledger itself (no gateway, network or
  model): a per-arm cap of K reservations plus an allowance admits exactly K calls in flight, spend
  plus active reservations never exceeds the cap, a receipt is reconciled exactly once, an unknown
  outcome keeps its reservation, and a failed call does not release an uncertain charge."
  (:require [clojure.test :refer [deftest is testing]]
            [repl-lab.controller :as c]
            [repl-lab.gateway :as g]
            [repl-lab.util :as u]
            [repl-lab.gateway-test :as gt]
            [repl-lab.runtime-test :as rt]))

(def reservation 4.32768)

(defn- arm
  "A run whose limits admit k concurrent full reservations plus a $0.50 allowance."
  [k]
  (let [root (rt/temp-root) store (str root "/controller.sqlite")
        config (-> rt/config
                   (assoc-in [:limits :usd] (+ (* k reservation) 0.5))
                   (assoc-in [:limits :calls] 64)
                   (assoc-in [:limits :tokens] 100000000)
                   (assoc-in [:limits :concurrent-subagents] 16))]
    (c/create-run! store "run" config nil)
    (c/session! store "run" "root" nil)
    (doseq [i (range 8)] (c/session! store "run" (str "child-" i) "root"))
    store))

(defn- ledger [store] (c/get-run store "run"))
(defn- exposure [store] (let [l (ledger store)] (+ (get-in l [:spent :usd]) (get-in l [:reserved :usd]))))

(deftest a-cap-of-k-reservations-admits-exactly-k-calls-in-flight
  (doseq [k [1 2 4]]
    (let [store (arm k)]
      (dotimes [i k]
        (c/reserve! store "run" (str "r" i) (str "child-" i) 1032768 reservation))
      (is (= k (get-in (ledger store) [:reserved :calls])) (str "k=" k))
      (is (thrown-with-msg? Exception #"Global provider budget exhausted"
            (c/reserve! store "run" "one-too-many" (str "child-" k) 1032768 reservation)) (str "k=" k))
      (is (<= (exposure store) (+ (* k reservation) 0.5)))
      ;; A receipt frees its reservation; the next call is then admitted.
      (c/reconcile! store "run" "r0" {:tokens 9000 :usd 0.03 :model "fixture"})
      (c/reserve! store "run" "next" (str "child-" k) 1032768 reservation)
      (is (= k (get-in (ledger store) [:reserved :calls])))
      (is (<= (exposure store) (+ (* k reservation) 0.5))))))

(deftest a-receipt-is-reconciled-exactly-once
  (let [store (arm 2)]
    (c/reserve! store "run" "a" "child-0" 1032768 reservation)
    (c/reconcile! store "run" "a" {:tokens 9000 :usd 0.03 :model "fixture"})
    (is (thrown-with-msg? Exception #"Request not pending" (c/reconcile! store "run" "a" {:tokens 9000 :usd 0.03 :model "fixture"})))
    (is (= {:calls 1 :usd 0.03} (select-keys (:spent (ledger store)) [:calls :usd])))
    (is (= 0 (get-in (ledger store) [:reserved :calls])))))

(deftest an-unknown-outcome-keeps-its-reservation-and-blocks-what-no-longer-fits
  (let [store (arm 2)]
    (c/reserve! store "run" "a" "child-0" 1032768 reservation)
    (c/reserve! store "run" "b" "child-1" 1032768 reservation)
    ;; Call a fails with an uncertain outcome: its charge is not released.
    (c/recover! store "run" "a")
    (is (= :unknown (get-in (ledger store) [:provider-requests "a" :status])))
    (is (= 2 (get-in (ledger store) [:reserved :calls])))
    (c/reconcile! store "run" "b" {:tokens 9000 :usd 0.03 :model "fixture"})
    ;; One reservation is still held by the unknown call, so exactly one more fits, not two.
    (c/reserve! store "run" "c" "child-2" 1032768 reservation)
    (is (thrown-with-msg? Exception #"Global provider budget exhausted"
          (c/reserve! store "run" "d" "child-3" 1032768 reservation)))
    (is (<= (exposure store) (+ (* 2 reservation) 0.5)))
    (testing "a late receipt for the unknown call is still reconciled once, at its real cost"
      (c/reconcile! store "run" "a" {:tokens 12000 :usd 0.04 :model "fixture"})
      (is (thrown? Exception (c/reconcile! store "run" "a" {:tokens 12000 :usd 0.04 :model "fixture"})))
      (is (= 2 (get-in (ledger store) [:spent :calls]))))))

(deftest spend-plus-reservations-never-exceeds-the-cap-as-spend-accumulates
  (let [store (arm 1) cap (+ reservation 0.5)]
    ;; Sequential calls of $0.11 each: admitted while spent + one reservation fits, refused after.
    (loop [i 0]
      (let [admitted (try (c/reserve! store "run" (str "s" i) "child-0" 1032768 reservation) true
                          (catch Exception _ false))]
        (when admitted
          (is (<= (exposure store) cap))
          (c/reconcile! store "run" (str "s" i) {:tokens 30000 :usd 0.11 :model "fixture"})
          (recur (inc i)))))
    (let [l (ledger store)]
      (is (= 5 (get-in l [:spent :calls])) "calls start while spend is at most the $0.50 allowance: at $0.00, 0.11, 0.22, 0.33 and 0.44")
      (is (< (- cap reservation) (+ (get-in l [:spent :usd]) 1e-9)))
      (is (= 0 (get-in l [:reserved :calls]))))))

;; The evidence-coverage plan's budget, through the gateway itself: Sonnet 5.5 rates and bounds, $17.82 per arm.
(def ^:private plan-settings {:thinking {:type "adaptive" :display "summarized"} :output_config {:effort "medium"}})
(defn- plan-gateway [subagents]
  (gt/fixture (assoc gt/config :model "claude-sonnet-5-5" :context-window 1000000 :max-output 32768 :pinned-settings plan-settings
                     :rates {:input 2 :output 10 :cache-read 0.1 :cache-write-5m 2.5 :cache-write-1h 4}
                     :limits {:calls 16 :tokens 12000000 :usd 17.82 :wall-ms 240000 :concurrent-subagents subagents})))
(def ^:private plan-body (merge (dissoc gt/request :temperature) plan-settings {:model "claude-sonnet-5-5" :max_tokens 32768}))

(deftest four-provider-calls-overlap-through-the-gateway-and-a-fifth-is-refused
  (doseq [[subagents refusal] [[4 #"Subagent limit|Global provider budget exhausted"] [8 #"Global provider budget exhausted"]]]
    (let [gateway (plan-gateway subagents)
          response (u/json-read (slurp "research/evidence/prime-head-to-head-v1-live-attempt1/provider-response.json"))
          entered (java.util.concurrent.CountDownLatch. 4)
          release (java.util.concurrent.CountDownLatch. 1)
          calls (atom 0)
          ;; Each provider reply has its own id, as real replies do (the gateway refuses a duplicate receipt).
          reply (fn [n] (update response :body #(u/json-str (assoc (u/json-read %) :id (str "msg_fixture_" n)))))
          transport (fn [_] (let [n (swap! calls inc)] (.countDown entered) (.await release) (reply n)))
          running (doall (repeatedly 4 #(future (g/dispatch! gateway "prime/task-1" plan-body transport))))]
      ;; All four are admitted and in flight at once, each holding the unchanged $4.32768 reservation.
      (is (.await entered 20 java.util.concurrent.TimeUnit/SECONDS))
      (let [l (gt/ledger gateway)]
        (is (= 4 (get-in l [:reserved :calls])))
        (is (< (Math/abs (- (get-in l [:reserved :usd]) (* 4 reservation))) 1e-9))
        (is (<= (+ (get-in l [:spent :usd]) (get-in l [:reserved :usd])) 17.82)))
      ;; A fifth concurrent call is refused before any dispatch.
      (is (thrown-with-msg? Exception refusal
            (g/dispatch! gateway "prime/task-1" plan-body (fn [_] (swap! calls inc) (reply 99)))))
      (is (= 4 @calls))
      (.countDown release)
      (is (every? #(= 200 (:status (deref % 20000 nil))) running))
      (let [l (gt/ledger gateway)]
        (is (= 4 (get-in l [:spent :calls])))
        (is (zero? (get-in l [:reserved :calls])))
        (is (< (Math/abs (- (get-in l [:spent :usd]) (* 4 0.005032))) 1e-9)))
      ;; The refusal did not stop the gateway: with the reservations released, the next call is admitted.
      (is (= 200 (:status (g/dispatch! gateway "prime/task-1" plan-body (constantly (reply 5))))))
      (is (= 5 (count (filter #(= "complete" (:status %)) (g/normalized-usage gateway))))))))
