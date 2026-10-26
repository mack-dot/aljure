(ns repl-lab.subscription-test
  (:require [clojure.test :refer :all] [repl-lab.subscription :as subscription]
            [repl-lab.provider :as provider] [repl-lab.controller :as c]
            [repl-lab.live :as live]
            [repl-lab.provider-test :refer [live-ledger]]))

(def adapter (subscription/->SubscriptionProvider "claude-sonnet-5-5" 2.0 10.0 2048 {:cli_sha256 "fixture-cli"}))
(def messages [{:role "user" :content "Synthetic transport exercise; not model evidence"}])
(def receipt {:model "claude-sonnet-5-5" :provider_id "fixture-message" :accepted true
              :usage {:input_tokens 100 :output_tokens 20 :cache_read_input_tokens 0 :cache_creation_input_tokens 0}
              :text "{:op :done :summary 42}" :cli_reported_usd 0.0004 :transport_session_id "fixture-session"})

(deftest learning-provider-reuses-private-login-with-explicit-scope
  (let [options (live/options {"LIVE" "1" "MODEL" "claude-sonnet-5-5" "MAX_USD" "15"
                              "INPUT_USD_PER_M" "2" "OUTPUT_USD_PER_M" "10"
                              "INFERENCE_PROVIDER" "claude-subscription"})]
    (with-redefs [subscription/preflight! (constantly {:cli_sha256 "fixture-cli" :cli_version "fixture"})]
      (let [prepared (live/prepare-provider! options)]
        (is (= :claude-code-subscription (get-in prepared [:model :provider])))
        (is (= :standard-rate-equivalent (:usd-basis prepared)))
        (is (= "fixture-cli" (get-in prepared [:transport :cli_sha256])))
        (is (= :learning-evaluation (:subscription-scope (live/provider-scope {} options)))))
      (is (thrown? Exception (live/prepare-provider! (assoc options :input-rate 3.0))))))
  (let [[_ store] (live-ledger) calls (atom 0)]
    (c/update-run! store "run" #(assoc-in % [:config :limits :usd] 2.5))
    (with-redefs [subscription/transport! (fn [& _] (swap! calls inc) {:ok true :response receipt})]
      (is (thrown? Exception (provider/invoke! adapter store "run" "root" messages)))
      (is (zero? @calls))
      (c/update-run! store "run" #(assoc-in % [:config :subscription-scope] :learning-evaluation))
      (is (= 120 (:tokens (provider/invoke! adapter store "run" "root" messages))))
      (is (= 1 @calls)))))

(deftest reserve-before-cli-and-charge-root-and-child-on-the-same-ledger
  (let [[_ store] (live-ledger) calls (atom [])]
    (c/session! store "run" "child" "root")
    (with-redefs [subscription/transport!
                  (fn [op request deadline]
                    (is (= "invoke" op))
                    (is (= 1 (get-in (c/get-run store "run") [:reserved :calls])))
                    (is (number? deadline))
                    (is (= "fixture-cli" (:cli_sha256 request)))
                    (is (= 2048 (:max_output_tokens request)))
                    (swap! calls conj request)
                    {:ok true :response (assoc receipt :provider_id (str "fixture-" (count @calls)))})]
      (let [root (provider/invoke! adapter store "run" "root" messages)
            child (provider/invoke! adapter store "run" "child" messages)
            ledger (c/get-run store "run")]
        (is (= 2 (count @calls)))
        (is (= 2 (get-in ledger [:spent :calls])))
        (is (= 240 (get-in ledger [:spent :tokens])))
        (is (= 0.0008 (get-in ledger [:spent :usd])))
        (is (zero? (get-in ledger [:reserved :calls])))
        (is (= :standard-rate-equivalent (:billing-basis root) (:billing-basis child)))
        (is (nil? (:actual-billed-usd root)))
        (is (= 2 (count (provider/playback-entries ledger))))))))

(deftest failure-keeps-reservation-and-never-retries
  (let [[_ store] (live-ledger) calls (atom 0)]
    (with-redefs [subscription/transport! (fn [& _] (swap! calls inc) (throw (ex-info "Fixture disconnect" {})))]
      (is (thrown? Exception (provider/invoke! adapter store "run" "root" messages)))
      (let [ledger (c/get-run store "run")]
        (is (= 1 @calls))
        (is (= 1 (get-in ledger [:reserved :calls])))
        (is (zero? (get-in ledger [:spent :calls])))
        (is (= :unknown (get-in ledger [:sessions "root" :status])))
        (is (thrown? Exception (provider/playback-entries ledger)))))))

(deftest rejected-completion-and-overrun-keep-known-consumption
  (doseq [answer [(assoc receipt :accepted false)
                  (assoc-in receipt [:usage :input_tokens] 100000)]]
    (let [[_ store] (live-ledger)]
      (with-redefs [subscription/transport! (fn [& _] {:ok true :response answer})]
        (is (thrown? Exception (provider/invoke! adapter store "run" "root" messages)))
        (let [ledger (c/get-run store "run")]
          (is (= 1 (get-in ledger [:spent :calls])))
          (is (zero? (get-in ledger [:reserved :calls])))
          (is (pos? (get-in ledger [:spent :usd]))))))))

(deftest insufficient-shared-budget-stops-before-cli
  (let [[_ store] (live-ledger) calls (atom 0)]
    (c/update-run! store "run" #(assoc-in % [:config :limits :usd] 0.001))
    (with-redefs [subscription/transport! (fn [& _] (swap! calls inc))]
      (is (thrown? Exception (provider/invoke! adapter store "run" "root" messages)))
      (is (zero? @calls))
      (is (empty? (:provider-requests (c/get-run store "run")))))))
