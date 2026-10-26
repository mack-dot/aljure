(ns repl-lab.provider
  (:require [repl-lab.controller :as c] [repl-lab.util :as u] [clojure.string :as str])
  (:import [java.net URI] [java.net.http HttpClient HttpRequest HttpRequest$BodyPublishers HttpResponse$BodyHandlers]
           [java.time Duration]))

(defprotocol Provider
  (invoke! [provider store run session messages]))

(defrecord FixtureProvider [responses]
  Provider
  (invoke! [_ store run session messages]
    (let [id (str (java.util.UUID/randomUUID)) answer (first (get @responses session))]
      (u/ensure! answer "Fixture response queue exhausted" {:session session})
      (c/reserve! store run id session 1000 0.0)
      (swap! responses update session #(vec (rest %)))
      (let [response {:model "fixture-script-v1" :tokens 0 :usd 0.0 :text (pr-str answer)
                      :provenance :synthetic-fixture :usage {:input_tokens 0 :output_tokens 0}}]
        (c/reconcile! store run id response)
        (c/update-run! store run #(c/event % :fixture-provider-call {:session session :input messages :response response}))
        response))))

(defn http-post! [path body api-key]
  (let [client (-> (HttpClient/newBuilder) (.connectTimeout (Duration/ofSeconds 10)) .build)
        request (-> (HttpRequest/newBuilder (URI/create (str "https://api.anthropic.com/v1/" path)))
                    (.timeout (Duration/ofSeconds 45))
                    (.header "content-type" "application/json")
                    (.header "anthropic-version" "2023-06-01")
                    (.header "x-api-key" api-key)
                    (.POST (HttpRequest$BodyPublishers/ofString (u/json-str body))) .build)
        response (.send client request (HttpResponse$BodyHandlers/ofInputStream))]
    (with-open [stream (.body response)]
      (let [read-task (future (.readNBytes stream 262145))
            bytes (deref read-task 45000 ::timeout)
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
        (let [body {:model model :messages messages}
              count-response (http-post! "messages/count_tokens" body api-key)
              _ (u/ensure! (<= (:input_tokens count-response) input-ceiling) "Token count exceeds reservation" {})
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
          actual)
        (catch Exception e
          ;; Reservation and request intent remain durable. No automatic retry.
          (c/recover! store run)
          (throw e))))))
