(ns repl-lab.gateway-test
  (:require [clojure.test :refer :all] [clojure.string :as str]
            [repl-lab.gateway :as g] [repl-lab.controller :as c] [repl-lab.util :as u]
            [repl-lab.runtime-test :refer [temp-root]]))

;; Rates and provider responses below are synthetic. There is no network call.
(def config {:model "fixture-model-v1" :context-window 1000 :max-output 100
             :pinned-settings {:temperature 0} :routes ["aljure/task-1" "prime/task-1"]
             :rates {:input 2 :output 10 :cache-read 0.2 :cache-write-5m 2.5 :cache-write-1h 4}
             :limits {:calls 20 :tokens 100000 :usd 1 :wall-ms 120000 :concurrent-subagents 4}})
(def request {:model "fixture-model-v1" :messages [{:role "user" :content "Test input"}]
              :max_tokens 100 :temperature 0 :stream false})
(def usage {:input_tokens 12 :output_tokens 3 :cache_read_input_tokens 5 :cache_creation_input_tokens 10
            :cache_creation {:ephemeral_5m_input_tokens 6 :ephemeral_1h_input_tokens 4}})
(defn response [id]
  {:status 200 :content-type "application/json"
   :body (u/json-str {:type "message" :id id :model "fixture-model-v1" :role "assistant"
                     :content [{:type "text" :text "Fixture only"}] :stop_reason "end_turn" :usage usage})})
(defn fixture ([] (fixture config))
  ([cfg] (g/create! (str (temp-root) "/ledger.sqlite") "gateway-fixture" cfg)))
(defn ledger [gateway] (c/get-run (:store gateway) (:run gateway)))
(defn stream-response [events]
  {:status 200 :content-type "text/event-stream"
   :body (apply str (map #(str "event: " (:type %) "\ndata: " (u/json-str %) "\n\n") events))})
(def stream-events
  [{:type "message_start" :message {:id "stream-1" :model "fixture-model-v1"
                                    :usage (assoc usage :output_tokens 1)}}
   {:type "ping"}
   {:type "content_block_start" :index 0 :content_block {:type "text" :text ""}}
   {:type "content_block_delta" :index 0 :delta {:type "text_delta" :text "Fixture"}}
   {:type "content_block_stop" :index 0}
   {:type "message_delta" :usage {:output_tokens 2}}
   {:type "message_delta" :usage {:output_tokens 3}}
   {:type "message_stop"}])

(deftest captured-sonnet-standard-speed-receipt-reconciles-offline
  ;; Exact preserved LIVE response, replayed without network or old-ledger edits.
  (let [wire (slurp "research/evidence/prime-head-to-head-v1-live-attempt1/provider-response.json")
        response (u/json-read wire)
        settings {:thinking {:type "adaptive" :display "summarized"} :output_config {:effort "medium"}}
        cfg (assoc config :model "claude-sonnet-5-5" :context-window 1000000 :max-output 32768
                   :pinned-settings settings :limits (assoc (:limits config) :usd 12 :tokens 12000000)
                   :rates {:input 2 :output 10 :cache-read 0.1 :cache-write-5m 2.5 :cache-write-1h 4})
        body (merge (dissoc request :temperature) settings {:model "claude-sonnet-5-5" :max_tokens 32768})
        gateway (fixture cfg)]
    (is (= "b007875495ea8fc82d517e90771b2161be5998a1003f4ba1490b32587d02a4b4" (u/sha wire)))
    (let [result (g/dispatch! gateway "aljure/task-1" body (constantly response))]
      (is (= response (select-keys result [:status :content-type :body])))
      (is (= "standard" (get-in result [:receipt :usage :speed])))
      (is (= "claude-sonnet-5-5" (get-in result [:receipt :model])))
      (is (= 2436 (get-in result [:receipt :tokens])))
      (is (= 0.005032 (get-in result [:receipt :usd])))
      (is (nil? (get-in result [:receipt :provider-billing-usd]))))
    (is (= {:calls 1 :tokens 2436 :usd 0.005032} (select-keys (:spent (ledger gateway)) [:calls :tokens :usd])))
    (is (every? zero? (vals (:reserved (ledger gateway)))))
    (is (= "complete" (:status (first (g/normalized-usage gateway)))))))

(deftest speed-price-boundary-remains-closed-for-json-and-streams
  (let [standard (assoc-in stream-events [0 :message :usage :speed] "standard")]
    (is (= 0.000086 (:usd (g/receipt config (stream-response standard)))))
    (doseq [speed ["fast" "unknown" nil 1]]
      (is (thrown? Exception (g/receipt config
                              (stream-response (assoc-in standard [6 :usage :speed] speed)))))))
  (doseq [speed ["fast" "unknown" nil 1]]
    (let [gateway (fixture)
          bad (update (response "unpriced-speed") :body
                      #(u/json-str (assoc-in (u/json-read %) [:usage :speed] speed)))]
      (is (thrown? Exception (g/dispatch! gateway "aljure/task-1" request (constantly bad))))
      (is (= :gateway-stopped (:status (ledger gateway))))
      (is (= 0 (get-in (ledger gateway) [:spent :calls])))
      (is (= 0.005 (get-in (ledger gateway) [:reserved :usd]))))))

(deftest streaming-usage-is-cumulative-and-cache-costs-are-distinct
  (let [parsed (g/receipt config (stream-response stream-events))]
    (is (= 30 (:tokens parsed)))
    (is (= 0.000086 (:usd parsed)))
    (is (= 3 (get-in parsed [:usage :output_tokens])))
    (is (nil? (:provider-billing-usd parsed)))
    (is (= (:usage (g/receipt config (response "json-1"))) (:usage parsed)))
  (doseq [events [(butlast stream-events)
                  (conj (vec (butlast stream-events)) {:type "error" :error {:type "overloaded_error"}})
                  (assoc stream-events 6 {:type "message_delta" :usage {:output_tokens 0}})
                  (conj stream-events {:type "message_start" :message {}})
                  (assoc stream-events 2 {:type "content_block_start" :content_block {:type "fallback"}})]]
    (is (thrown? Exception (g/receipt config (stream-response events)))))
  (is (= (:usage (g/receipt config (stream-response stream-events)))
         (:usage (g/receipt config (update (stream-response stream-events) :body str/replace "\n" "\r\n")))))))

(deftest reject-unpriced-usage-and-request-features
  (doseq [bad [(dissoc usage :output_tokens) (assoc usage :input_tokens -1)
               (assoc usage :server_tool_use {:web_search_requests 1})
               (assoc usage :service_tier "priority") (assoc usage :inference_geo "us")
               (dissoc usage :cache_creation) (assoc usage :cache_creation {:ephemeral_5m_input_tokens 99})]]
    (is (thrown? Exception (g/usage-cost (:rates config) bad))))
  (doseq [bad [(assoc request :model "different") (assoc request :max_tokens 101)
               (dissoc request :temperature) (assoc request :service_tier "priority")
               (assoc request :tools [{:name "web_search" :type "web_search_20250305" :input_schema {}}])
               (assoc request :messages [{:role "user" :content [{:type "image" :source {}}]}])]]
    (is (thrown? Exception (g/validate-request! config "prime/task-1" bad))))
  (is (= request (g/validate-request! config "prime/task-1" request)))
  (is (= {:tokens 1100 :usd 0.005} (g/reservation config request))))

(deftest request-bound-is-1-mib-unless-the-plan-raises-it
  (let [large (assoc request :messages [{:role "user" :content (apply str (repeat 1100000 "a"))}])
        huge (assoc request :messages [{:role "user" :content (apply str (repeat 4300000 "a"))}])]
    (is (thrown-with-msg? Exception #"Gateway input limit" (g/validate-request! config "prime/task-1" large)))
    (is (= large (g/validate-request! (assoc config :request-bytes 4194304) "prime/task-1" large)))
    ;; The bound never exceeds 4 MiB, whatever the config says.
    (is (thrown-with-msg? Exception #"Gateway input limit"
          (g/validate-request! (assoc config :request-bytes 99999999) "prime/task-1" huge)))))

(deftest all-routes-share-durable-reservations-and-unique-receipts
  (let [gateway (fixture) calls (atom 0)
        transport (fn [_]
                    (is (= 1 (get-in (ledger gateway) [:reserved :calls])))
                    (response (str "request-" (swap! calls inc))))]
    (g/dispatch! gateway "prime/task-1" request transport)
    (g/dispatch! gateway "aljure/task-1" request transport)
    (is (= 2 (get-in (ledger gateway) [:spent :calls])))
    (is (= 60 (get-in (ledger gateway) [:spent :tokens])))
    (is (zero? (get-in (ledger gateway) [:reserved :calls])))
    (let [rows (g/normalized-usage gateway)]
      (is (= #{"prime/task-1" "aljure/task-1"} (set (map :route rows))))
      (is (= 2 (count (set (map :provider_request_id rows)))))
      (is (every? #(= "complete" (:status %)) rows)))
    ;; A duplicate receipt cannot release another request's reservation.
    (is (thrown? Exception (g/dispatch! gateway "prime/task-1" request (constantly (response "request-1")))))
    (is (= :gateway-stopped (:status (ledger gateway))))
    (is (= 2 (get-in (ledger gateway) [:spent :calls])))
    (is (= 1 (get-in (ledger gateway) [:reserved :calls])))))

(deftest failure-keeps-reservation-and-stops-retries-after-reopen
  (let [gateway (fixture) calls (atom 0)
        failed (fn [_] (swap! calls inc) (throw (ex-info "fake-key-must-not-be-recorded" {})))]
    (is (thrown? Exception (g/dispatch! gateway "prime/task-1" request failed)))
    (is (= 0.005 (get-in (ledger gateway) [:reserved :usd])))
    (is (= :gateway-stopped (:status (ledger gateway))))
    (is (not (str/includes? (pr-str (ledger gateway)) "fake-key-must-not-be-recorded")))
    (g/recover! (select-keys gateway [:store :run]))
    (is (thrown? Exception (g/dispatch! gateway "prime/task-1" request failed)))
    (is (= 1 @calls))
    (is (= "unknown" (:status (first (g/normalized-usage gateway)))))
    (is (= 0.005 (:reserved_usd (first (g/normalized-usage gateway)))))))

(deftest concurrent-descendant-cannot-use-reserved-money
  (let [gateway (fixture (assoc-in config [:limits :usd] 0.005))
        entered (promise) release (promise) calls (atom 0)
        first-call (future (g/dispatch! gateway "prime/task-1" request
                             (fn [_] (swap! calls inc) (deliver entered true)
                               (deref release 20000 nil) (response "root-call"))))]
    (try
      (is (= true (deref entered 10000 :timeout)))
      (is (thrown? Exception (g/dispatch! gateway "prime/task-1" request
                              (fn [_] (swap! calls inc) (response "child-must-not-dispatch")))))
      (is (= 1 @calls))
      (is (= 0.005 (get-in (ledger gateway) [:reserved :usd])))
      (finally (deliver release true)))
    (is (map? (deref first-call 10000 nil)))
    (is (= 1 (get-in (ledger gateway) [:spent :calls])))
    (is (zero? (get-in (ledger gateway) [:reserved :calls])))))

(deftest model-mismatch-is-accounted-before-stopping
  (let [gateway (fixture)
        wrong (update (response "wrong-model") :body #(u/json-str (assoc (u/json-read %) :model "unexpected")))]
    (is (thrown? Exception (g/dispatch! gateway "aljure/task-1" request (constantly wrong))))
    (is (= :gateway-stopped (:status (ledger gateway))))
    (is (= 1 (get-in (ledger gateway) [:spent :calls])))
    (is (zero? (get-in (ledger gateway) [:reserved :calls])))
    (is (= "unexpected" (:model (first (g/normalized-usage gateway)))))))

(deftest crash-before-dispatch-remains-conservatively-reserved
  (let [{:keys [store run] :as gateway} (fixture)]
    (c/session! store run "crash-request" "gateway")
    (c/reserve! store run "crash-intent" "crash-request" 1100 0.005)
    (g/recover! gateway)
    (is (= :unknown (get-in (ledger gateway) [:provider-requests "crash-intent" :status])))
    (is (= :gateway-stopped (:status (ledger gateway))))
    (is (= 0.005 (get-in (ledger gateway) [:reserved :usd])))))

(deftest opus-contract-and-fixed-economic-reservations
  (let [settings {:thinking {:type "adaptive" :display "summarized"} :output_config {:effort "medium"}}
        cfg (assoc config :model "claude-opus-5-5" :context-window 1000000 :max-output 32768
                   :pinned-settings settings :limits (assoc (:limits config) :usd 12 :tokens 12000000)
                   :rates {:input 4 :output 20 :cache-read 0.2 :cache-write-5m 5 :cache-write-1h 8})
        body (merge (dissoc request :temperature) settings {:model "claude-opus-5-5" :max_tokens 32768})
        gateway (fixture cfg)
        first-call (g/admit! gateway "prime/task-1" body)]
    (is (= {:tokens 1032768 :usd 8.65536} (g/reservation cfg body)))
    (is (thrown? Exception (g/admit! gateway "prime/task-1" body)))
    (is (= 1 (get-in (ledger gateway) [:reserved :calls])))
    (is (= 8.65536 (get-in (ledger gateway) [:reserved :usd])))
    (g/finish! gateway first-call (update (response "opus-first") :body
                                  #(u/json-str (assoc (u/json-read %) :model "claude-opus-5-5"))))
    (is (zero? (get-in (ledger gateway) [:reserved :calls])))
    (is (= 1 (get-in (ledger gateway) [:spent :calls])))
    (let [next-call (g/admit! gateway "prime/task-1" body)]
      (is (string? (:id next-call)))
      (g/finish! gateway next-call (update (response "opus-second") :body
                                   #(u/json-str (assoc (u/json-read %) :model "claude-opus-5-5")))))
    (doseq [bad [(assoc body :tool_choice {:type "any"})
                 (assoc body :tool_choice {:type "tool" :name "ipython"})
                 (update body :messages conj {:role "assistant" :content "prefill"})]]
      (is (thrown? Exception (g/validate-request! cfg "prime/task-1" bad))))
    (doseq [choice [nil {:type "auto"} {:type "none"}]]
      (let [valid (cond-> body choice (assoc :tool_choice choice))]
        (is (= valid (g/validate-request! cfg "prime/task-1" valid)))))))
