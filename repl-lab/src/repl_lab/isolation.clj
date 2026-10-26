(ns repl-lab.isolation (:require [repl-lab.util :as u] [clojure.java.io :as io])
  (:import [java.util.concurrent TimeUnit]))
(defn doctor []
  (let [p (.start (ProcessBuilder. ^java.util.List ["python3" "scripts/isolation.py" "doctor"]))
        output (future (slurp (.getInputStream p)))]
    (if (.waitFor p 12 TimeUnit/SECONDS) (u/json-read @output)
      (do (.destroyForcibly p) {:ready false :reason "Isolation preflight timeout"}))))
(defn open-session! []
  (let [check (doctor)]
    (u/ensure! (:ready check) "Generated-code execution disabled" check)
    (let [p (.start (ProcessBuilder. ^java.util.List ["python3" "scripts/isolation.py" "session"]))]
      {:process p :writer (io/writer (.getOutputStream p)) :reader (io/reader (.getInputStream p))
       :errors (future (slurp (.getErrorStream p)))})))
(defn close-session! [{:keys [process writer]}]
  (.close writer)
  ;; Closing stdin asks the supervisor to reap the entire container. The supervisor
  ;; enforces its own wall deadline even if this controller crashes.
  (when-not (.waitFor process 20 TimeUnit/SECONDS)
    (u/fail "Supervisor did not confirm worker termination" {})))
(defn evaluate! [{:keys [process writer reader] :as session} source bindings]
  (let [wire (pr-str {:source source :bindings bindings})]
    (u/ensure! (<= (count (.getBytes wire "UTF-8")) 65535) "Worker input too large" {})
    (.write writer (str wire "\n")) (.flush writer)
    (let [read-result (future (.readLine reader)) line (deref read-result 20000 ::timeout)]
      (when (= line ::timeout) (close-session! session) (u/fail "Worker response timeout" {}))
      (u/ensure! (string? line) "Worker terminated without result" {})
      (u/ensure! (<= (count line) 65536) "Worker result too large" {})
      (let [result (u/read-edn line)]
        (u/ensure! (not (:error result)) "Worker rejected expression" {:error (:error result)})
        (:value result)))))
