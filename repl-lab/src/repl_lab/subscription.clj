(ns repl-lab.subscription
  (:require [clojure.java.io :as io] [repl-lab.provider :as provider]
            [repl-lab.controller :as c] [repl-lab.util :as u] [repl-lab.limits :as limits])
  (:import [java.util.concurrent TimeUnit]))

(defn transport! [operation request deadline]
  (let [process (.start (ProcessBuilder. ^java.util.List ["python3" "scripts/claude_subscription.py" operation]))
        output (future (with-open [stream (.getInputStream process)] (.readNBytes stream 262145)))
        errors (future (with-open [stream (.getErrorStream process)] (.readNBytes stream 65537)))]
    (try
      (with-open [writer (io/writer (.getOutputStream process))]
        (when request (.write writer (u/json-str request))))
      (u/ensure! (.waitFor process (limits/timeout-ms deadline 75000) TimeUnit/MILLISECONDS)
                 "Subscription transport timed out; retain its reservation" {})
      (let [bytes (deref output 5000 ::timeout)]
        (u/ensure! (and (not= bytes ::timeout) (<= (alength bytes) 262144)) "Invalid subscription transport response" {})
        (let [result (u/json-read (String. bytes "UTF-8"))]
          (u/ensure! (zero? (.exitValue process)) "Subscription transport stopped; inspect its preserved trace" (select-keys result [:reason :error_type]))
          result))
      (finally
        (when (.isAlive process) (.destroy process)
          (when-not (.waitFor process 6 TimeUnit/SECONDS) (.destroyForcibly process)))
        (future-cancel output) (future-cancel errors)))))

(defn preflight! []
  (let [check (transport! "doctor" nil nil)]
    (u/ensure! (:ready check) "Claude subscription login is unavailable to this process" check)
    check))

(defrecord SubscriptionProvider [model input-rate output-rate max-output cli]
  provider/Provider
  (invoke! [_ store run session messages]
    (let [ledger (c/get-run store run) _ (c/within-time! ledger)
          _ (u/ensure! (and (= :live (get-in ledger [:config :mode])) (= model "claude-sonnet-5-5")
                            (= 2.0 (double input-rate)) (= 10.0 (double output-rate)) (= 2048 max-output)
                            (<= 0.0 (get-in ledger [:config :limits :usd]) 1.0))
                       "Subscription transport is restricted to the authorized smoke configuration" {})
          id (str (java.util.UUID/randomUUID))
          ;; Whole serialized history plus conservative headroom for CLI-added context.
          ;; USD here is a standard-rate equivalent, never a subscription invoice.
          input-ceiling (+ 16384 (count (.getBytes (u/json-str {:messages messages}) "UTF-8")))
          tokens (+ input-ceiling max-output)
          usd (/ (+ (* input-rate input-ceiling) (* output-rate max-output)) 1000000.0)
          trace (.getAbsolutePath (io/file (.getParentFile (io/file store)) "transport" id))
          deadline (:deadline-ms (limits/from-run ledger))]
      (c/reserve! store run id session tokens usd)
      (try
        (c/update-run! store run #(c/event % :provider-input {:request-id id :session session :input messages
                                                            :input-hash (u/hash-value messages) :trace-path trace
                                                            :transport :claude-code-subscription}))
        (let [result (transport! "invoke" {:model model :messages messages :max_output_tokens max-output
                                           :reserved_usd usd :cli_sha256 (:cli_sha256 cli)
                                           :trace_dir trace :deadline_ms deadline} deadline)
              _ (u/ensure! (:ok result) "Subscription provider failed; inspect preserved transport evidence" {})
              receipt (:response result) usage (:usage receipt)
              input (+ (:input_tokens usage) (:cache_read_input_tokens usage) (:cache_creation_input_tokens usage))
              output (:output_tokens usage)
              actual {:model (:model receipt) :requested-model model :provider-id (:provider_id receipt)
                      :tokens (+ input output) :usd (/ (+ (* input-rate input) (* output-rate output)) 1000000.0)
                      :usage usage :text (:text receipt) :provenance :recorded-model-run
                      :transport :claude-code-subscription :trace-path trace
                      :billing-basis :standard-rate-equivalent :actual-billed-usd nil
                      :cli-reported-usd (:cli_reported_usd receipt) :transport-session-id (:transport_session_id receipt)}]
          ;; Charge known consumption before rejecting an invalid or over-budget result.
          (c/reconcile! store run id actual)
          (u/ensure! (and (:accepted receipt) (= model (:model receipt))
                          (<= (:tokens actual) tokens) (<= (:usd actual) usd))
                     "Subscription receipt failed model, output, cache, completion, or reservation validation" {})
          actual)
        (catch Exception error
          (c/recover! store run)
          (throw error))))))
