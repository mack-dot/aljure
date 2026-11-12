(ns repl-lab.selector-accounting
  "Strict receipts for selector v2. Uses the existing durable reservation ledger."
  (:require [repl-lab.controller :as c] [repl-lab.provider :as p] [repl-lab.util :as u]))

(defn finite-nonnegative? [n]
  (and (number? n) (Double/isFinite (double n)) (<= 0 n)))

(defn usage! [ledger]
  (u/ensure! (and (map? ledger) (string? (:id ledger)) (integer? (:started-ms ledger))
                  (map? (:config ledger)) (map? (:sessions ledger)) (vector? (:events ledger))
                  (map? (:provider-requests ledger))
                  (= #{:calls :tokens :usd} (set (keys (:reserved ledger))))
                  (every? #(contains? (:spent ledger) %) [:calls :tokens :usd]))
             "Complete controller usage ledger required" {})
  (u/ensure! (and (every? #(and (finite-nonnegative? %) (zero? %)) (vals (:reserved ledger)))
                  (not= :budget-overrun (:status ledger))) "Unresolved or exceeded usage reservation" {})
  (let [requests (:provider-requests ledger)
        receipts (filter #(= :provider-result (:type %)) (:events ledger))
        ids (map #(get-in % [:payload :request-id]) receipts)
        _ (u/ensure! (and (= (count ids) (count (set ids))) (= (set ids) (set (keys requests))))
                     "Provider events do not reconcile with requests" {})
        total (reduce
                (fn [out [id request]]
                  (let [response (:response request) usage (:usage response)
                        input (+ (get usage :input_tokens 0) (get usage :cache_creation_input_tokens 0)
                                 (get usage :cache_read_input_tokens 0))
                        output (:output_tokens usage) usd (:usd response)
                        event (:payload (first (filter #(= id (get-in % [:payload :request-id])) receipts)))]
                    (u/ensure! (and (= :complete (:status request))
                                    (contains? (:sessions ledger) (:session request))
                                    (map? usage) (nat-int? (:input_tokens usage)) (nat-int? output)
                                    (every? nat-int? (map #(get usage % 0) [:cache_creation_input_tokens :cache_read_input_tokens]))
                                    (= (:tokens response) (+ input output)) (finite-nonnegative? usd)
                                    (= (select-keys response [:tokens :usd :model]) (select-keys event [:tokens :usd :model])))
                               "Provider receipt is incomplete or inconsistent" {})
                    (when (= :live (get-in ledger [:config :mode]))
                      (u/ensure! (and (= :recorded-model-run (:provenance response))
                                      (= "claude-sonnet-5-5" (:requested-model response) (:model response))
                                      (< (Math/abs (- usd (/ (+ (* 2.0 input) (* 10.0 output)) 1000000.0))) 1.0e-9))
                                 "Live model or standard-rate-equivalent receipt differs" {}))
                    (merge-with + out {:calls 1 :input-tokens input :output-tokens output :tokens (+ input output) :usd usd})))
                {:calls 0 :input-tokens 0 :output-tokens 0 :tokens 0 :usd 0.0} requests)]
    (doseq [key [:calls :tokens :usd]]
      (u/ensure! (and (finite-nonnegative? (get-in ledger [:spent key]))
                      (< (Math/abs (- (double (get total key)) (double (get-in ledger [:spent key])))) 1.0e-9))
                 "Spent totals do not reconcile" {:resource key}))
    total))

(defn cost! [ledger] (:usd (usage! ledger)))

(defn reconcile-phase! [phase ledgers]
  (let [total (usage! phase)
        _ (doseq [ledger ledgers] (usage! ledger))
        shape #(select-keys % [:model :requested-model :provider-id :tokens :usd :usage :text :provenance])
        expected (frequencies (for [ledger ledgers [_ request] (:provider-requests ledger)]
                                [(:accounting-store ledger) (:id ledger) (:session request) (shape (:response request))]))
        actual (frequencies (for [[_ request] (:provider-requests phase) :let [response (:response request)]]
                              [(:origin-store response) (:origin-run response) (:origin-session response) (shape response)]))]
    (u/ensure! (= expected actual) "Phase and root/descendant ledgers disagree" {}) total))

(defrecord PhaseProvider [delegate phase-store phase-id max-output]
  p/Provider
  (invoke! [_ store run session messages]
    ;; Every root/child request uses this wrapper. The native adapter still
    ;; enforces its task ledger. Phase caps sum to the campaign ceiling.
    (let [id (str (java.util.UUID/randomUUID))
          input-ceiling (+ 16384 (count (.getBytes (u/json-str {:messages messages}) "UTF-8")))
          tokens (+ input-ceiling max-output)
          usd (/ (+ (* 2.0 input-ceiling) (* 10.0 max-output)) 1000000.0)]
      (c/reserve! phase-store phase-id id "accounting" tokens usd)
      (c/update-run! phase-store phase-id #(c/event % :accounted-dispatch
                                            {:request-id id :origin-store store :origin-run run :origin-session session
                                             :input-hash (u/hash-value messages)}))
      (try
        (let [response (p/invoke! delegate store run session messages)]
          (c/reconcile! phase-store phase-id id (assoc response :origin-store store :origin-run run :origin-session session))
          (u/ensure! (= :running (:status (c/get-run phase-store phase-id))) "Phase reservation exceeded" {})
          response)
        (catch Exception e
          ;; Conservative even if a task rejected before dispatch. No retries;
          ;; unknown reservations block the phase until independent recovery.
          (c/recover! phase-store phase-id id)
          (throw e))))))
