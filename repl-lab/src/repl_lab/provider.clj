(ns repl-lab.provider
  (:require [repl-lab.controller :as c] [repl-lab.util :as u] [clojure.string :as str] [repl-lab.limits :as limits]
            [repl-lab.model-protocol :as wire])
  (:import [java.net URI] [java.net.http HttpClient HttpRequest HttpRequest$BodyPublishers HttpResponse$BodyHandlers]
           [java.time Duration]))

(defprotocol Provider
  (invoke! [provider store run session messages]))

(defn playback-entries [ledger]
  (mapv (fn [event]
          (let [request (:payload event) response (get-in ledger [:provider-requests (:request-id request) :response])]
            (u/ensure! response "Cannot play back an unknown provider outcome" {})
            (assoc request :response response)))
        (filter #(= :provider-input (:type %)) (:events ledger))))

(defrecord PlaybackProvider [entries]
  Provider
  (invoke! [_ store run session messages]
    (let [entry (first @entries)]
      (u/ensure! (and entry (= session (:session entry)) (= (u/hash-value messages) (:input-hash entry)))
                 "Recorded-response playback input mismatch" {})
      (let [id (str (java.util.UUID/randomUUID)) original (:response entry)
            response (assoc original :tokens 0 :usd 0.0 :provenance :recorded-response-playback
                            :recorded-usage (select-keys original [:tokens :usd :usage]))]
        (c/reserve! store run id session 1 0.0)
        (c/reconcile! store run id response)
        (swap! entries #(vec (rest %)))
        (c/update-run! store run #(c/event % :recorded-response-playback {:session session :input-hash (:input-hash entry)
                                                                       :original-request (:request-id entry)}))
        response))))

(defrecord FixtureProvider [responses]
  Provider
  (invoke! [_ store run session messages]
    (let [id (str (java.util.UUID/randomUUID)) answer (first (get @responses session))]
      (u/ensure! answer "Fixture response queue exhausted" {:session session})
      (c/reserve! store run id session 1000 0.0)
      (swap! responses update session #(vec (rest %)))
      (let [response {:model "fixture-script-v1" :tokens 0 :usd 0.0 :text (wire/write-command (:config (c/get-run store run)) answer)
                      :provenance :synthetic-fixture :usage {:input_tokens 0 :output_tokens 0}}]
        (c/reconcile! store run id response)
        (c/update-run! store run #(c/event % :fixture-provider-call {:session session :input messages :response response}))
        response))))

(def ^:dynamic *task-deadline-ms* nil)

(defn http-post! [path body api-key]
  (let [client (-> (HttpClient/newBuilder) (.connectTimeout (Duration/ofMillis (limits/timeout-ms *task-deadline-ms* 10000))) .build)
        request (-> (HttpRequest/newBuilder (URI/create (str "https://api.anthropic.com/v1/" path)))
                    (.timeout (Duration/ofMillis (limits/timeout-ms *task-deadline-ms* 45000)))
                    (.header "content-type" "application/json")
                    (.header "anthropic-version" "2023-06-01")
                    (.header "x-api-key" api-key)
                    (.POST (HttpRequest$BodyPublishers/ofString (u/json-str body))) .build)
        response (.send client request (HttpResponse$BodyHandlers/ofInputStream))]
    (with-open [stream (.body response)]
      (let [read-task (future (.readNBytes stream 262145))
            bytes (deref read-task (limits/timeout-ms *task-deadline-ms* 45000) ::timeout)
            _ (when (= bytes ::timeout)
                (.close stream) (future-cancel read-task) (u/fail "Provider body timeout; outcome may be unknown" {}))]
        (u/ensure! (<= (alength bytes) 262144) "Provider response too large" {})
        ;; Do not log request headers, credentials, or provider error bodies.
        (u/ensure! (= 200 (.statusCode response)) "Provider HTTP failure" {:status (.statusCode response)})
        (u/json-read (String. bytes "UTF-8"))))))

(defrecord AnthropicProvider [model api-key input-rate output-rate max-output]
  Provider
  (invoke! [_ store run session messages]
    (let [r (c/get-run store run) _ (c/within-time! r)
          _ (u/ensure! (= :live (get-in r [:config :mode])) "Live provider requires explicit live run" {})
          _ (u/ensure! (and (string? model) (seq model) (not (str/ends-with? model "latest"))
                            (seq api-key) (pos? input-rate) (pos? output-rate)
                            (pos? (get-in r [:config :limits :usd] 0))) "Live model, explicit rates and positive cap required" {})
          request-id (str (java.util.UUID/randomUUID))
          ;; Reserve a conservative ceiling BEFORE even the token-count request.
          ;; No tools, cache, web search, images or provider-side execution are enabled.
          input-ceiling (+ 4096 (count (.getBytes (u/json-str messages) "UTF-8")))
          reserve-tokens (+ input-ceiling max-output)
          reserve-usd (/ (+ (* input-rate input-ceiling) (* output-rate max-output)) 1000000.0)]
      (c/reserve! store run request-id session reserve-tokens reserve-usd)
      (try
        (c/update-run! store run #(c/event % :provider-input {:request-id request-id :session session
                                                            :input-hash (u/hash-value messages) :input messages}))
        (binding [*task-deadline-ms* (:deadline-ms (limits/from-run r))]
        (let [body {:model model :messages messages}
              _ (limits/timeout-ms *task-deadline-ms* 45000)
              count-response (http-post! "messages/count_tokens" body api-key)
              _ (u/ensure! (<= (:input_tokens count-response) input-ceiling) "Token count exceeds reservation" {})
              _ (limits/timeout-ms *task-deadline-ms* 45000)
              response (http-post! "messages" (assoc body :max_tokens max-output) api-key)
              usage (:usage response)
              input (+ (:input_tokens usage) (get usage :cache_creation_input_tokens 0) (get usage :cache_read_input_tokens 0))
              output (:output_tokens usage)
              actual {:model (:model response) :requested-model model :provider-id (:id response)
                      :tokens (+ input output) :usd (/ (+ (* input input-rate) (* output output-rate)) 1000000.0)
                      :usage usage :text (apply str (map :text (filter #(= "text" (:type %)) (:content response))))
                      :provenance :recorded-model-run}]
          (c/reconcile! store run request-id actual)
          (u/ensure! (= model (:model response)) "Returned model identifier differs from pinned identifier" {})
          actual))
        (catch Exception e
          ;; Reservation and request intent remain durable. No automatic retry.
          (c/recover! store run)
          (throw e))))))
