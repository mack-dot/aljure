(ns repl-lab.provider-test
  (:require [clojure.test :refer :all]
            [repl-lab.runtime-test :refer [fixture]] [repl-lab.controller :as c]
            [repl-lab.provider :as provider] [repl-lab.util :as u] [repl-lab.limits :as limits]))

;; These HTTP responses are test data. They are never published as model results.
(def messages [{:role "user" :content "Offline HTTP transport test"}])
(def fake-key "offline-test-key-not-a-credential")
(def adapter (provider/->AnthropicProvider "fixture-model-id" fake-key 1.0 2.0 32))
(defn live-ledger []
  (let [[root store] (fixture)]
    (c/update-run! store "run" #(-> % (assoc-in [:config :mode] :live) (assoc-in [:config :limits :usd] 1.0)))
    [root store]))
(defn response [model]
  {:model model :id "fixture-response" :usage {:input_tokens 12 :output_tokens 3}
   :content [{:type "text" :text "{:op :done :summary \"Offline fixture response\"}"}]})

(deftest reserve-before-count-and-reconcile-actual-usage
  (let [[_ store] (live-ledger) paths (atom [])]
    (with-redefs [provider/http-post!
                  (fn [path body key]
                    (is (= fake-key key))
                    (is (= "fixture-model-id" (:model body)))
                    (is (= 1 (get-in (c/get-run store "run") [:reserved :calls])))
                    (swap! paths conj path)
                    (case path
                      "messages/count_tokens" {:input_tokens 12}
                      "messages" (do (is (= 32 (:max_tokens body))) (response "fixture-model-id"))))]
      (let [answer (provider/invoke! adapter store "run" "root" messages)
            ledger (c/get-run store "run") playback (provider/playback-entries ledger)]
        (is (= ["messages/count_tokens" "messages"] @paths))
        (is (= 15 (:tokens answer)))
        (is (= 0.000018 (:usd answer)))
        (is (= 1 (get-in ledger [:spent :calls])))
        (is (zero? (get-in ledger [:reserved :calls])))
        (is (= :ready (get-in ledger [:sessions "root" :status])))
        (is (= answer (:response (first playback))))
        (is (= (u/hash-value messages) (:input-hash (first playback))))
        (is (not (.contains (pr-str ledger) fake-key)))))))

(deftest request-failure-keeps-reservation-and-is-not-retried
  (let [[_ store] (live-ledger) calls (atom 0)]
    (with-redefs [provider/http-post! (fn [& _] (swap! calls inc) (throw (ex-info "Mock transport disconnect" {})))]
      (is (thrown? Exception (provider/invoke! adapter store "run" "root" messages)))
      (let [ledger (c/get-run store "run")]
        (is (= 1 @calls))
        (is (= 1 (get-in ledger [:reserved :calls])))
        (is (zero? (get-in ledger [:spent :calls])))
        (is (= :unknown (get-in ledger [:sessions "root" :status])))
        (is (every? #(= :unknown (:status %)) (vals (:provider-requests ledger))))
        (is (thrown? Exception (provider/playback-entries ledger)))))))

(deftest count-ceiling-and-model-mismatch-fail-with-honest-accounting
  (let [[_ store] (live-ledger) paths (atom [])]
    (with-redefs [provider/http-post! (fn [path & _] (swap! paths conj path) {:input_tokens 1000000})]
      (is (thrown? Exception (provider/invoke! adapter store "run" "root" messages)))
      (is (= ["messages/count_tokens"] @paths))
      (is (= 1 (get-in (c/get-run store "run") [:reserved :calls])))))
  (let [[_ store] (live-ledger)]
    (with-redefs [provider/http-post! (fn [path & _] (if (= path "messages/count_tokens") {:input_tokens 12}
                                                      (response "unexpected-model-id")))]
      (is (thrown? Exception (provider/invoke! adapter store "run" "root" messages)))
      (let [ledger (c/get-run store "run")]
        (is (= 1 (get-in ledger [:spent :calls])))
        (is (zero? (get-in ledger [:reserved :calls])))
        (is (= "unexpected-model-id" (get-in (first (vals (:provider-requests ledger))) [:response :model])))))))

(deftest rejected-budget-makes-no-http-call
  (let [[_ store] (live-ledger) calls (atom 0)]
    (c/update-run! store "run" #(assoc-in % [:config :limits :calls] 0))
    (with-redefs [provider/http-post! (fn [& _] (swap! calls inc) (throw (ex-info "Must not call" {})))]
      (is (thrown? Exception (provider/invoke! adapter store "run" "root" messages)))
      (is (zero? @calls))
      (is (empty? (:provider-requests (c/get-run store "run")))))))

(deftest count-request-cannot-reset-the-task-deadline
  (let [[_ store] (live-ledger) paths (atom []) clock (atom (System/currentTimeMillis))]
    (with-redefs [limits/now-ms #(deref clock)
                  provider/http-post! (fn [path & _]
                                        (swap! paths conj path)
                                        (reset! clock provider/*task-deadline-ms*)
                                        {:input_tokens 12})]
      (is (thrown-with-msg? Exception #"wall budget" (provider/invoke! adapter store "run" "root" messages))))
    (is (= ["messages/count_tokens"] @paths))
    (is (= 1 (get-in (c/get-run store "run") [:reserved :calls])))
    (is (zero? (get-in (c/get-run store "run") [:spent :calls])))))

(deftest remaining-time-bounds-both-http-phases
  (with-redefs [limits/now-ms (constantly 1000)]
    (is (= 20 (limits/timeout-ms 1020 45000)))
    (is (= 10000 (limits/timeout-ms 100000 10000)))
    (is (thrown? Exception (limits/timeout-ms 1000 45000)))))
