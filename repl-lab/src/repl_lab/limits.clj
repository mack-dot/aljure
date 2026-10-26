(ns repl-lab.limits (:require [repl-lab.util :as u]))

(defn now-ms [] (System/currentTimeMillis))
(defn from-run [run]
  (let [events (get-in run [:config :limits :event-budget])
        wall (get-in run [:config :limits :wall-ms])]
    (u/ensure! (and (pos-int? events) (pos-int? wall) (integer? (:started-ms run))) "Invalid execution limits" {})
    {:event-budget events :deadline-ms (+ (:started-ms run) wall)}))
(defn fresh [config] (from-run {:config config :started-ms (now-ms)}))
(defn expired? [deadline] (and deadline (<= deadline (now-ms))))
(defn timeout-ms [deadline ceiling]
  (let [remaining (if deadline (- deadline (now-ms)) ceiling)]
    (u/ensure! (pos? remaining) "Task wall budget exhausted" {:resource :wall-ms})
    (long (min ceiling remaining))))
