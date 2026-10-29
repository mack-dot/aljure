(ns repl-lab.transport-failure-test
  "Provider-transport failure modes, offline. Scripted gateway replies and
  synthetic receipts only: no network, credentials, model calls or Docker."
  (:require [clojure.test :refer :all] [clojure.string :as str]
            [repl-lab.controller :as c] [repl-lab.gateway :as g] [repl-lab.runtime :as runtime]
            [repl-lab.external-task :as external] [repl-lab.model-protocol :as wire]
            [repl-lab.provider :as provider] [repl-lab.util :as u]
            [repl-lab.runtime-test :as rt] [repl-lab.gateway-test :as gt]
            [repl-lab.command-envelope-test :as ce]))

(defmacro expected-failure
  "Known issue: the assertions in body are expected to FAIL. While the issue
  reproduces this reports one pass and prints the reason. Once it is fixed it
  reports an unexpected success, so the marker is removed with the fix."
  [reason & body]
  `(let [failed# (atom 0)]
     (binding [report (fn [m#] (when (#{:fail :error} (:type m#)) (swap! failed# inc)))]
       (try ~@body (catch Throwable _# (swap! failed# inc))))
     (when (pos? @failed#) (println "KNOWN ISSUE (expected failure):" ~reason))
     (is (pos? @failed#) (str "Unexpected success; the known issue may be fixed: " ~reason))))

(defn- events [ledger kind] (filter #(= kind (:type %)) (:events ledger)))
(defn- retried-flags [ledger] (mapv #(get-in % [:payload :retried]) (events ledger :provider-turn-retried)))

;; ---------------------------------------------------------------------------
;; Gateway: malformed and partial provider bodies, duplicate and late delivery.

(defn- json-edit [response f] (update response :body #(u/json-str (f (u/json-read %)))))

(def malformed-replies
  "[label reply rejection-category]. Every case is an unknown outcome."
  (let [json (gt/response "malformed") stream (gt/stream-response gt/stream-events)]
    [["cut-off JSON body" (update json :body #(subs % 0 (quot (count %) 2))) :receipt-validation]
     ["empty body" (assoc json :body "") :receipt-validation]
     ["non-JSON body" (assoc json :body "<html>overloaded</html>") :receipt-validation]
     ["unknown content type" (assoc json :content-type "text/html") :receipt-validation]
     ["HTTP 529" (assoc json :status 529) :receipt-validation]
     ["missing message id" (json-edit json #(dissoc % :id)) :receipt-validation]
     ["missing usage" (json-edit json #(dissoc % :usage)) :receipt-validation]
     ["usage without output_tokens" (json-edit json #(update % :usage dissoc :output_tokens)) :receipt-validation]
     ["no body" (assoc json :body nil) :receipt-validation]
     ["stream: undecodable event" (update stream :body #(str "event: message_start\ndata: {\"type\":\n\n" %)) :receipt-validation]
     ["stream: event before message_start"
      (gt/stream-response (into [{:type "content_block_start" :index 0 :content_block {:type "text" :text ""}}] gt/stream-events))
      :receipt-validation]
     ["stream: unknown event type" (gt/stream-response (assoc gt/stream-events 1 {:type "surprise"})) :receipt-validation]
     ["stream: message_start without id" (gt/stream-response (update-in gt/stream-events [0 :message] dissoc :id)) :receipt-validation]
     ["stream: cut off before message_stop" (gt/stream-response (vec (butlast gt/stream-events))) :incomplete-stream]
     ["stream: message_delta without usage"
      (gt/stream-response (-> gt/stream-events (update 5 dissoc :usage) (update 6 dissoc :usage))) :terminal-usage]]))

(deftest malformed-or-partial-provider-bodies-are-unknown-outcomes-and-never-retried
  (doseq [[label bad category] malformed-replies]
    (testing label
      (let [gateway (gt/fixture) calls (atom 0)
            transport (fn [_] (swap! calls inc) bad)]
        (is (thrown? Exception (g/dispatch! gateway "aljure/task-1" gt/request transport)))
        (let [l (gt/ledger gateway) [q] (vals (:provider-requests l))]
          (is (= :gateway-stopped (:status l)))
          ;; Not charged, not released: the full reservation is held.
          (is (= 0 (get-in l [:spent :calls])))
          (is (= {:calls 1 :tokens 1100 :usd 0.005} (:reserved l)))
          (is (= :unknown (:status q)))
          (is (= [category] (map #(get-in % [:payload :category]) (events l :gateway-receipt-rejected))))
          ;; The raw bytes stay in evidence whenever there were bytes.
          (when (string? (:body bad))
            (is (= (:body bad) (get-in (first (events l :gateway-response)) [:payload :response :body]))))
          (is (= ["unknown"] (map :status (g/normalized-usage gateway)))))
        ;; The gateway never resends or accepts another request after an unknown outcome.
        (is (thrown? Exception (g/dispatch! gateway "aljure/task-1" gt/request transport)))
        (is (= 1 @calls))))))

(deftest the-same-receipt-delivered-twice-is-charged-once
  (let [gateway (gt/fixture) admission (g/admit! gateway "aljure/task-1" gt/request) reply (gt/response "delivered-twice")]
    (is (= 30 (get-in (g/finish! gateway admission reply) [:receipt :tokens])))
    (is (thrown? Exception (g/finish! gateway admission reply)))
    (let [l (gt/ledger gateway)]
      (is (= {:calls 1 :tokens 30} (select-keys (:spent l) [:calls :tokens])))
      (is (= 0 (get-in l [:reserved :calls])))
      (is (= {"delivered-twice" (:id admission)} (:gateway-receipts l)))
      (is (= :complete (get-in l [:provider-requests (:id admission) :status])))
      ;; Both deliveries are evidence; the duplicate stops the gateway.
      (is (= 2 (count (events l :gateway-response))))
      (is (= :gateway-stopped (:status l))))
    (is (= ["complete"] (map :status (g/normalized-usage gateway))))))

(deftest a-late-receipt-for-an-abandoned-request-is-reconciled-once
  (let [gateway (gt/fixture) calls (atom 0)
        admission (g/admit! gateway "aljure/task-1" gt/request) reply (gt/response "late-receipt")]
    ;; The transport gave up: the outcome is unknown and the reservation is held.
    (g/stop-uncertain! gateway (:id admission))
    (is (= :unknown (get-in (gt/ledger gateway) [:provider-requests (:id admission) :status])))
    (is (= 0.005 (get-in (gt/ledger gateway) [:reserved :usd])))
    ;; The receipt arrives later: its known cost replaces the reservation, once.
    (is (= 30 (get-in (g/finish! gateway admission reply) [:receipt :tokens])))
    (is (thrown? Exception (g/finish! gateway admission reply)))
    (let [l (gt/ledger gateway)]
      (is (= {:calls 1 :tokens 30} (select-keys (:spent l) [:calls :tokens])))
      (is (= {:calls 0 :tokens 0 :usd 0.0} (:reserved l)))
      (is (= :gateway-stopped (:status l))))
    ;; Reconciling a late receipt never reopens the stopped gateway.
    (is (thrown? Exception (g/dispatch! gateway "aljure/task-1" gt/request
                             (fn [_] (swap! calls inc) (gt/response "must-not-dispatch")))))
    (is (= 0 @calls))
    (is (= ["complete"] (map :status (g/normalized-usage gateway))))))

(deftest a-cancelled-session-is-charged-once-for-its-in-flight-call-and-cannot-call-again
  (let [[_ store] (rt/fixture)]
    (c/session! store "run" "child" "root")
    (c/reserve! store "run" "in-flight" "child" 100 0.0)
    ;; The parent cancels the child while its provider call is in flight.
    (c/cancel! store "run" "child")
    (c/reconcile! store "run" "in-flight" {:tokens 40 :usd 0.0 :model "fixture"})
    (let [l (c/get-run store "run")]
      (is (= :cancelled (get-in l [:sessions "child" :status])))
      (is (= {:calls 1 :tokens 40} (select-keys (:spent l) [:calls :tokens])))
      (is (= 0 (get-in l [:reserved :calls]))))
    (is (thrown? Exception (c/reconcile! store "run" "in-flight" {:tokens 40 :usd 0.0 :model "fixture"})))
    (is (thrown? Exception (c/reserve! store "run" "after-cancel" "child" 100 0.0)))
    (is (= 1 (get-in (c/get-run store "run") [:spent :calls])))))

;; ---------------------------------------------------------------------------
;; Task runtime through the production ExternalProvider: scripted gateway frames.

(def thinking {:type "thinking" :thinking "fixture" :signature "fixture-signature"})
(def interrupted {:type "thinking" :thinking "This part of the response was interrupted before it finished." :signature "fixture-signature"})
(defn- tool-use [name input] {:type "tool_use" :id (str "toolu_" (java.util.UUID/randomUUID)) :name name :input input})
(defn- message [content stop]
  {:type "message" :id (str "msg_" (java.util.UUID/randomUUID)) :model "fixture-model-v1" :role "assistant"
   :content content :stop_reason stop :usage gt/usage})
(defn- reply
  "A gateway reply to the emitted request: a message map, or a raw body string."
  [body]
  (fn [frame] {:id (:id frame) :response {:status 200 :content-type "application/json"
                                          :body (if (string? body) body (u/json-str body))}}))
(def truncated (reply (message [thinking interrupted] "tool_use")))
(def finish (reply (message [thinking (tool-use "done" {:summary "6"})] "tool_use")))
(def contract {:truncated-turn-retries 2 :terminal-text-answer true})

(defn run-external
  "Runs a root session through ExternalProvider; each scripted reply answers the
  last emitted request frame. after-reply runs once each reply is read."
  [replies & {:keys [contract limits after-reply]}]
  (let [root (rt/temp-root) store (str root "/controller.sqlite") emitted (atom []) queue (atom replies)
        cfg (cond-> (-> rt/config (assoc :response-envelope wire/tool-envelope-version)
                        (assoc-in [:limits :history-records] Integer/MAX_VALUE)
                        (update :limits merge {:usd 1} limits))
              contract (assoc :contract contract))
        p (external/->ExternalProvider {:model "fixture-model-v1" :tools (wire/tool-definitions)} gt/config)]
    (c/create-run! store "run" cfg nil)
    (c/session! store "run" "root" nil)
    (with-redefs [external/emit! (fn [frame] (swap! emitted conj frame))
                  external/receive! (fn []
                                      (let [next-reply (first @queue)]
                                        (u/ensure! next-reply "No scripted gateway reply" {})
                                        (swap! queue rest)
                                        (let [r (next-reply (last @emitted))]
                                          (when after-reply (after-reply store "run"))
                                          r)))]
      (let [result (runtime/run-session! {:store store :run "run" :workers (atom {}) :provider p
                                          :base-instructions "Fixture transport test"}
                                         "root" {:task "Fixture only"})]
        {:result result :emitted @emitted :ledger (c/get-run store "run")}))))

(deftest a-truncated-turn-through-the-external-provider-resends-the-identical-body
  (let [{:keys [result emitted ledger]} (run-external [truncated finish] :contract contract)
        [a b] emitted [first-input second-input] (events ledger :provider-input)]
    (is (= {:summary "6"} result))
    (is (= 2 (count emitted)))
    (is (= (:body a) (:body b)))
    (is (not= (:id a) (:id b)))
    (is (= {:calls 2 :tokens 60} (select-keys (:spent ledger) [:calls :tokens])))
    (is (= {:calls 0 :tokens 0 :usd 0.0} (:reserved ledger)))
    (is (= 1 (:transport-retries-issued ledger)))
    (is (nil? (:command-corrections-issued ledger)))
    ;; The retry appends nothing: the truncated turn never enters history.
    (is (= (get-in first-input [:payload :input-hash]) (get-in second-input [:payload :input-hash])))
    (is (= [] (get-in second-input [:payload :appended])))))

(def unknown-replies
  "[label reply]. Each leaves the task ledger without a receipt."
  [["gateway error frame (Relay.poll shape)"
    (fn [frame] {:id (:id frame) :error "Gateway rejected request or provider outcome is uncertain"})]
   ["reply for a different request (stale or late delivery)"
    (fn [_] ((reply (message [thinking interrupted] "tool_use")) {:id "an-earlier-request"}))]
   ["non-200 reply" (fn [frame] {:id (:id frame) :response {:status 529 :content-type "application/json" :body "{}"}})]
   ["malformed JSON body" (reply "{\"type\":\"message\",\"id\":")]
   ["missing usage" (reply (dissoc (message [thinking interrupted] "tool_use") :usage))]])

(deftest unknown-outcomes-are-never-retried-even-with-transport-retries-enabled
  ;; Each scripted body would be a truncated turn if it had a receipt.
  (doseq [[label unknown] unknown-replies]
    (testing label
      (let [{:keys [result emitted ledger]} (run-external [unknown finish] :contract contract)
            [q] (vals (:provider-requests ledger))]
        (is (= :failed (:status result)))
        (is (= 1 (count emitted)))
        (is (= :unknown (:status q)))
        (is (= 0 (get-in ledger [:spent :calls])))
        (is (= {:calls 1 :tokens 1100 :usd 0.005} (:reserved ledger)))
        (is (empty? (mapcat #(events ledger %) [:provider-turn-retried :command-rejected :tool-call])))
        (is (nil? (:transport-retries-issued ledger))))))
  ;; Same rule for a provider that throws after recording the outcome as unknown.
  (let [{:keys [result ledger observed]}
        (let [root (rt/temp-root) store (str root "/controller.sqlite") calls (atom 0)
              p (reify provider/Provider
                  (invoke! [_ store run session _]
                    (swap! calls inc)
                    (c/reserve! store run (str "unknown-" @calls) session 100 0.01)
                    (c/recover! store run)
                    (throw (ex-info "Fixture provider interruption" {}))))]
          (c/create-run! store "run" (-> ce/tool-config (assoc :contract contract) (assoc-in [:limits :usd] 1)) nil)
          (c/session! store "run" "root" nil)
          {:result (runtime/run-session! {:store store :run "run" :workers (atom {}) :provider p} "root" {})
           :ledger (c/get-run store "run") :observed @calls})]
    (is (:error result))
    (is (= 1 observed))
    (is (empty? (events ledger :provider-turn-retried)))))

(def partial-replies
  "[label reply]. A receipt exists, but the turn did not end for one tool call."
  [["max_tokens, text only" (reply (message [thinking {:type "text" :text "I will count the"}] "max_tokens"))]
   ["max_tokens, cut inside a tool call" (reply (message [thinking (tool-use "done" {:summary "6"})] "max_tokens"))]
   ["stop_reason missing" (reply (dissoc (message [thinking interrupted] "tool_use") :stop_reason))]
   ["stop_reason null" (reply (message [thinking interrupted] nil))]])

(deftest partial-turns-are-charged-rejected-and-never-retried-or-executed
  (doseq [[label partial] partial-replies]
    (testing label
      (let [{:keys [result emitted ledger]} (run-external [partial finish] :contract contract)
            rejected (map :payload (events ledger :command-rejected))]
        (is (= "Command response rejected; no correction permitted" (:error result)))
        (is (= 1 (count emitted)))
        (is (= 1 (get-in ledger [:spent :calls])))
        (is (= 0 (get-in ledger [:reserved :calls])))
        (is (= [[:incomplete-turn false false false]]
               (map (juxt :reason :recoverable :correction-requested :executed) rejected)))
        (is (empty? (events ledger :provider-turn-retried)))
        (is (empty? (events ledger :tool-call)))))))

;; ---------------------------------------------------------------------------
;; F1 truncated-turn retry: allowance, scope, deadline and budget.

(deftest the-transport-retry-allowance-is-bounded-and-task-wide
  (let [cfg (assoc ce/tool-config :contract contract)
        trunc (ce/opus-response :imdb-truncated)
        done (ce/tool-response "done" {:summary "6"})
        two (ce/execute-script {"root" [trunc trunc done]} {} nil cfg)
        three (ce/execute-script {"root" [trunc trunc trunc done]} {} nil cfg)
        ;; The root spends the only retry; the child's truncated turn then fails.
        shared (ce/execute-script {"root" [trunc (ce/tool-response "agent_call" {:id "child" :task "t"}) done]
                                   "child" [trunc done]}
                                  {} nil (assoc ce/tool-config :contract {:truncated-turn-retries 1}))]
    (is (= {:summary "6"} (:result two)))
    (is (= 2 (get-in two [:ledger :transport-retries-issued])))
    (is (= 3 (get-in two [:ledger :spent :calls])))
    (is (= "Provider turn truncated; transport retry budget exhausted" (get-in three [:result :error])))
    (is (= [true true false] (retried-flags (:ledger three))))
    (is (= 3 (count (:observed three)) (get-in three [:ledger :spent :calls])))
    (is (= {:summary "6"} (:result shared)))
    (is (= ["root" "root" "child" "root"] (mapv :session (:observed shared))))
    (is (= :failed (get-in shared [:ledger :sessions "child" :status])))
    (is (= [true false] (retried-flags (:ledger shared))))
    (is (= 1 (get-in shared [:ledger :transport-retries-issued]))))
  ;; Only native tool turns are retried; a text envelope rejects the same shape.
  (let [text-turn {:text "" :stop-reason "tool_use" :content [thinking]}
        r (ce/execute-script {"root" [text-turn (ce/response ce/done)]} {} nil (assoc ce/strict-config :contract contract))]
    (is (:error (:result r)))
    (is (empty? (events (:ledger r) :provider-turn-retried)))
    (is (= 1 (count (:observed r)))))
  ;; A tool_use stop with no blocks at all also carried no command.
  (is (wire/truncated-tool-turn? {:stop-reason "tool_use" :content []})))

(def ^:private expire! (fn [store run & _] (c/update-run! store run #(assoc % :started-ms 0))))
(def refused-retries
  "[label limits after-call error]. The truncated turn is the first call."
  [["calls cap" {:calls 1} nil #"Global provider budget exhausted"]
   ["usd cap" {:usd 0.01} nil #"Global provider budget exhausted"]
   ["tokens cap" {:tokens 100} nil #"Global provider budget exhausted"]
   ["task deadline" {} expire! #"wall budget exhausted"]])

(deftest a-retry-without-deadline-or-budget-left-is-never-dispatched
  (doseq [[label limits after-call error] refused-retries]
    (testing label
      (let [{:keys [result observed ledger]}
            (ce/execute-script {"root" [(ce/opus-response :imdb-truncated) (ce/tool-response "done" {:summary "6"})]}
                               limits after-call (assoc ce/tool-config :contract contract))]
        (is (re-find error (str (:error result))))
        (is (= 1 (count observed) (get-in ledger [:spent :calls])))
        (is (= 0 (get-in ledger [:reserved :calls])))
        (is (empty? (events ledger :tool-call))))))
  ;; Through the external provider no second request frame is emitted.
  (let [{:keys [result emitted ledger]} (run-external [truncated finish] :contract contract :after-reply expire!)]
    (is (re-find #"wall budget exhausted" (str (:error result))))
    (is (= 1 (count emitted)))
    (is (= 1 (get-in ledger [:spent :calls])))))

(deftest a-refused-retry-is-not-recorded-as-a-retry
  ;; scripts/contract_audit.py treats retried=true as "the identical request was
  ;; resent" and reports f1-retry when no request follows. The runtime writes
  ;; retried=true and spends the counter before the next call checks the caps.
  (expected-failure
   "runtime.clj retry-truncated-turn! records :retried true and increments :transport-retries-issued before the deadline/budget check refuses the resend; the contract auditor then reports a false f1-retry violation"
   (doseq [[label limits after-call] refused-retries]
     (let [{:keys [observed ledger]}
           (ce/execute-script {"root" [(ce/opus-response :imdb-truncated) (ce/tool-response "done" {:summary "6"})]}
                              limits after-call (assoc ce/tool-config :contract contract))]
       (is (= 1 (count observed)) label)
       (is (= (dec (count observed)) (count (filter true? (retried-flags ledger)))) label)
       (is (nil? (:transport-retries-issued ledger)) label)))))
