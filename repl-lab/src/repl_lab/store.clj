(ns repl-lab.store (:require [repl-lab.util :as u] [clojure.java.io :as io])
  (:import [java.util.concurrent TimeUnit]))

(defn request! [db request]
  (let [p (.start (ProcessBuilder. ^java.util.List ["python3" "scripts/store.py" (str db)]))]
    (with-open [w (io/writer (.getOutputStream p))] (.write w (u/json-str request)))
    (let [out (future (slurp (.getInputStream p))) err (future (slurp (.getErrorStream p)))]
      (when-not (.waitFor p 15 TimeUnit/SECONDS)
        (.destroyForcibly p) (u/fail "Storage timeout" {}))
      (u/ensure! (zero? (.exitValue p)) "Storage failure" {:error @err}) (u/json-read @out))))
(defn read-record [db key]
  (let [r (request! db {:op :read :key key})]
    (update r :value #(when % (u/read-edn %)))))
(defn read-value [db key] (:value (read-record db key)))
(defn transact! [db key f]
  (loop [attempt 0]
    (u/ensure! (< attempt 20) "Concurrent storage contention" {:key key})
    (let [{:keys [revision value]} (read-record db key) next (f value)
          r (request! db {:op :cas :key key :revision revision :value (pr-str (u/canonical next))})]
      (if (:success r) next (recur (inc attempt))))))
