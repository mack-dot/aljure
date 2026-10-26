(ns repl-lab.gateway
  "Trusted request accounting for an external provider gateway. No network listener
   or production transport is enabled here. Uses the existing controller ledger."
  (:require [clojure.string :as str] [repl-lab.controller :as c] [repl-lab.util :as u]))

(def input-fields [:input_tokens :cache_read_input_tokens :cache_creation_input_tokens])
(def token-fields (conj input-fields :output_tokens))
(def request-fields #{:model :messages :system :tools :tool_choice :max_tokens :stream
                      :temperature :thinking :output_config :stop_sequences :metadata})
(def usage-fields #{:input_tokens :output_tokens :cache_read_input_tokens :cache_creation_input_tokens
                    :cache_creation :output_tokens_details :service_tier :inference_geo})

(defn create! [store run config]
  (let [{:keys [model context-window max-output rates limits routes pinned-settings]} config]
    (u/ensure! (and (string? model) (seq model) (not (str/ends-with? model "latest"))
                    (pos-int? context-window) (pos-int? max-output) (<= max-output context-window)
                    (map? pinned-settings) (seq routes) (every? string? routes)
                    (every? #(and (number? %) (pos? %) (Double/isFinite (double %)))
                            (map rates [:input :output :cache-read :cache-write-5m :cache-write-1h]))
                    (every? pos-int? (map limits [:calls :tokens :wall-ms :concurrent-subagents]))
                    (number? (:usd limits)) (pos? (:usd limits)))
               "Explicit gateway model, rates, routes and positive limits required" {})
    (c/create-run! store run (assoc config :mode :gateway :limits (merge limits {:recursion-depth 1 :history-records 2})) nil)
    (c/session! store run "gateway" nil)
    {:store store :run run}))

(defn recover! [{:keys [store run] :as gateway}]
  ;; Only call during exclusive process startup, never during concurrent requests.
  (c/recover! store run)
  (c/update-run! store run #(if (some (fn [q] (= :unknown (:status q))) (vals (:provider-requests %)))
                            (assoc % :status :gateway-stopped) %))
  gateway)

(defn validate-request! [config route body]
  (u/ensure! (contains? (set (:routes config)) route) "Unknown controller-owned route" {})
  (u/ensure! (and (map? body) (every? request-fields (keys body))
                  (= (:model config) (:model body)) (vector? (:messages body)) (seq (:messages body))
                  (pos-int? (:max_tokens body)) (<= (:max_tokens body) (:max-output config))
                  (or (not (contains? body :stream)) (boolean? (:stream body)))
                  (= (select-keys body [:temperature :thinking :output_config]) (:pinned-settings config)))
             "Request differs from pinned model/settings or allowed Messages fields" {})
  ;; Restrict this initial adapter to text and client tools. Server tools, media,
  ;; service tiers, fallback and server-side compaction need separate cost bounds.
  ;; Native host-side refinement/compaction are ordinary accounted requests.
  (doseq [tool (:tools body)]
    (u/ensure! (and (map? tool) (string? (:name tool)) (map? (:input_schema tool))
                    (or (nil? (:type tool)) (= "custom" (:type tool)))) "Unpriced server tool denied" {}))
  (doseq [message (:messages body)]
    (u/ensure! (and (map? message) (#{"user" "assistant"} (:role message))) "Invalid message" {}))
  (letfn [(content! [content]
            (u/ensure! (or (string? content) (vector? content)) "Invalid content" {})
            (when (vector? content)
              (doseq [block content]
                (u/ensure! (and (map? block) (#{"text" "tool_use" "tool_result" "thinking" "redacted_thinking"} (:type block)))
                           "Unpriced content block denied" {})
                (when (= "tool_result" (:type block)) (content! (:content block))))))]
    (doseq [message (:messages body)] (content! (:content message)))
    (when (:system body) (content! (:system body))))
  (u/ensure! (<= (alength (.getBytes (u/json-str body) "UTF-8")) 1048576) "Gateway input limit" {})
  body)

(defn reservation [config body]
  ;; Reserve the entire declared model context bound at the highest input/cache
  ;; rate, plus maximum output. A token-count estimate is not a hard upper bound.
  ;; This is intentionally conservative and requires a verified model context cap
  ;; before a real transport can be enabled. No guessed byte/token ratio is used.
  (let [input (:context-window config) output (:max_tokens body) rates (:rates config)]
    {:tokens (+ input output)
     :usd (/ (+ (* input (apply max (map rates [:input :cache-read :cache-write-5m :cache-write-1h])))
                (* output (:output rates))) 1000000.0)}))

(defn usage-cost [rates usage]
  (u/ensure! (and (map? usage) (every? usage-fields (keys usage))
                  (every? #(nat-int? (get usage %)) [:input_tokens :output_tokens])
                  (every? #(nat-int? (get usage % 0)) [:cache_read_input_tokens :cache_creation_input_tokens])
                  (or (nil? (:service_tier usage)) (= "standard" (:service_tier usage)))
                  (or (nil? (:inference_geo usage)) (= "global" (:inference_geo usage))))
             "Missing, invalid or unpriced usage" {})
  (let [write (get usage :cache_creation_input_tokens 0)
        creation (:cache_creation usage)
        short (get creation :ephemeral_5m_input_tokens 0)
        long (get creation :ephemeral_1h_input_tokens 0)]
    (u/ensure! (and (nat-int? short) (nat-int? long)
                    (or (nil? creation) (and (map? creation)
                       (every? #{:ephemeral_5m_input_tokens :ephemeral_1h_input_tokens} (keys creation))))
                    (or (zero? write) (and creation (= write (+ short long))))
                    (= write (+ short long))) "Cache write duration is unknown or inconsistent" {})
    {:tokens (reduce + (map #(get usage % 0) token-fields))
     :usd (/ (+ (* (:input rates) (:input_tokens usage)) (* (:output rates) (:output_tokens usage))
                (* (:cache-read rates) (get usage :cache_read_input_tokens 0))
                (* (:cache-write-5m rates) short) (* (:cache-write-1h rates) long)) 1000000.0)}))

(defn parse-stream [body]
  ;; message_delta usage counters are cumulative. Merge, never sum them.
  (let [events (keep (fn [frame]
                       (let [data (->> (str/split-lines frame) (filter #(str/starts-with? % "data:"))
                                       (map #(str/replace-first (subs % 5) #"^ " "")) (str/join "\n"))]
                         (when (seq data) (u/json-read data))))
                     (str/split (str/replace body "\r\n" "\n") #"\n\n"))]
    (loop [[event & more] events message nil delta? false stop? false]
      (if-not event
        (do (u/ensure! (and message delta? stop?) "Incomplete provider stream" {}) message)
        (do
          (u/ensure! (not stop?) "Provider event after message_stop" {})
          (case (:type event)
            "message_start" (do (u/ensure! (nil? message) "Duplicate message_start" {})
                                (recur more (:message event) delta? false))
            "message_delta" (do (u/ensure! (and message (map? (:usage event))) "Missing cumulative usage" {})
                                (doseq [field token-fields :when (contains? (:usage event) field)]
                                  (u/ensure! (and (nat-int? (get-in event [:usage field]))
                                                  (>= (get-in event [:usage field]) (get-in message [:usage field] 0)))
                                             "Usage counter decreased" {}))
                                (recur more (update message :usage merge (:usage event)) true false))
            "message_stop" (recur more message delta? true)
            "ping" (recur more message delta? false)
            (do (u/ensure! (and message (#{"content_block_start" "content_block_delta" "content_block_stop"} (:type event)))
                           "Provider stream error or unsupported event" {})
                (u/ensure! (not= "fallback" (get-in event [:content_block :type])) "Model fallback denied" {})
                (recur more message delta? false))))))))

(defn receipt [config response]
  (u/ensure! (and (= 200 (:status response)) (string? (:body response))
                  (<= (alength (.getBytes (:body response) "UTF-8")) 4194304)) "Invalid or oversized provider response" {})
  (let [stream? (= "text/event-stream" (:content-type response))
        _ (u/ensure! (or stream? (= "application/json" (:content-type response))) "Unknown response type" {})
        message (if stream? (parse-stream (:body response)) (u/json-read (:body response)))
        _ (u/ensure! (and (string? (:id message)) (seq (:id message)) (string? (:model message))) "Missing provider identity" {})]
    (merge (usage-cost (:rates config) (:usage message))
           {:model (:model message) :requested-model (:model config) :provider-id (:id message)
            :usage (:usage message) :provenance :gateway-provider-receipt
            :cost-kind :configured-rate-estimate :provider-billing-usd nil})))

(defn stop-uncertain! [{:keys [store run]} request-id]
  (c/update-run! store run
    (fn [r]
      (let [q (get-in r [:provider-requests request-id])]
        (cond-> (assoc r :status (if (= :budget-overrun (:status r)) :budget-overrun :gateway-stopped))
          (= :pending (:status q))
          (-> (assoc-in [:provider-requests request-id :status] :unknown)
              (assoc-in [:sessions (:session q) :status] :unknown)
              (c/event :provider-outcome-unknown {:request-id request-id})))))))

(defn dispatch! [{:keys [store run] :as gateway} route body transport]
  ;; route comes from the trusted adapter, not an agent-supplied session label.
  ;; The ledger sessions below identify REQUESTS, not inferred agent ancestry.
  (let [config (:config (c/get-run store run))
        _ (validate-request! config route body)
        id (str (java.util.UUID/randomUUID)) session (str "request-" id)
        bound (reservation config body)]
    (c/session! store run session "gateway")
    (try
      (c/update-run! store run #(c/event % :gateway-request-intent {:request-id id :route route
                                                                  :input-hash (u/hash-value body) :input body}))
      (c/reserve! store run id session (:tokens bound) (:usd bound))
      (catch Exception e
        (c/finish-session! store run session :failed {:reason :reservation-denied})
        (throw e)))
    (try
      ;; Transport owns bounded I/O and credentials. It must not retry. Native
      ;; retry requests each re-enter this gate with a fresh server-owned UUID.
      (let [response (transport body)
            _ (u/ensure! (and (map? response) (string? (:body response))
                              (<= (alength (.getBytes (:body response) "UTF-8")) 4194304))
                         "Missing or oversized provider body" {})
            _ (c/update-run! store run #(c/event % :gateway-response {:request-id id :response
                                    (select-keys response [:status :content-type :body])}))
            actual (receipt config response)]
        (c/update-run! store run
          (fn [r]
            (u/ensure! (nil? (get-in r [:gateway-receipts (:provider-id actual)])) "Duplicate provider receipt" {})
            (assoc-in r [:gateway-receipts (:provider-id actual)] id)))
        (c/reconcile! store run id actual)
        ;; Account first even when the provider returns the wrong model or more
        ;; than reserved. Preserve measured usage and then stop the whole run.
        (u/ensure! (= (:model config) (:model actual)) "Provider model differs from pin" {})
        (u/ensure! (and (<= (reduce + (map #(get-in actual [:usage %] 0) input-fields)) (:context-window config))
                        (<= (get-in actual [:usage :output_tokens]) (:max_tokens body)))
                   "Provider exceeded configured token bounds" {})
        (u/ensure! (not= :budget-overrun (:status (c/get-run store run))) "Provider exceeded reservation" {})
        (c/finish-session! store run session :complete {:request-id id})
        (assoc response :gateway-request-id id :receipt actual))
      (catch Exception e
        (stop-uncertain! gateway id)
        ;; Never forward an exception or raw headers that could contain keys.
        (throw (ex-info "Gateway stopped; inspect the durable request ledger" {:request-id id}))))))

(defn normalized-usage [{:keys [store run]}]
  (let [ledger (c/get-run store run)
        routes (into {} (for [event (:events ledger) :when (= :gateway-request-intent (:type event))]
                          [(get-in event [:payload :request-id]) (get-in event [:payload :route])]))]
    (mapv (fn [[id q]]
            (merge {:kind "provider-call" :call_id id :session_id (:session q) :route (routes id)
                    :session_identity "gateway-request; agent ancestry unverified"
                    :model (get-in ledger [:config :model]) :status (if (= :complete (:status q)) "complete" "unknown")}
                   (if (= :complete (:status q))
                     (let [response (:response q)]
                       (merge (zipmap token-fields (repeat 0)) (select-keys (:usage response) token-fields)
                              {:provider_request_id (:provider-id response) :model (:model response)
                               :cache_creation (get-in response [:usage :cache_creation])
                               :estimated_usd (:usd response) :provider_billing_usd nil}))
                     {:reserved_usd (:reserved-usd q)})))
          (sort-by key (:provider-requests ledger)))))
