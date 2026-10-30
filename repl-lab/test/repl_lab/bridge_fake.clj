(ns repl-lab.bridge-fake
  "A fake SCI worker for offline bridge tests: the real worker bridge half
  (worker/src/repl_lab/bridge.clj) in a thread over pipes, with a Clojure function in place of
  SCI evaluation. The controller side (isolation/request!, programs) is the real code."
  (:require [repl-lab.bridge :as bridge])
  (:import [java.io PipedInputStream PipedOutputStream InputStreamReader OutputStreamWriter BufferedReader BufferedWriter]))

(defn session
  "evaluate: (fn [source bindings]) that may call bridge/tool; it runs under each request's grant.
  The worker prints {:value} or {:error} exactly as the SCI worker does."
  [evaluate]
  (let [to-worker (PipedOutputStream.) from-worker (PipedOutputStream.)
        worker-in (BufferedReader. (InputStreamReader. (PipedInputStream. to-worker 65536) "UTF-8"))
        worker-out (java.io.PrintWriter. (BufferedWriter. (OutputStreamWriter. from-worker "UTF-8")) true)
        thread (Thread. (fn []
                          (binding [*in* worker-in *out* worker-out]
                            (loop []
                              (when-let [line (read-line)]
                                (let [result (try (let [{:keys [source bindings tools]} (bridge/safe-read line)
                                                        value (bridge/with-grant tools (evaluate source bindings))]
                                                    (bridge/safe-read (pr-str {:value value})))
                                                  (catch Exception e {:error (or (.getMessage e) "failed")}))]
                                  (prn result) (flush))
                                (recur))))))]
    (.start thread)
    {:writer (BufferedWriter. (OutputStreamWriter. to-worker "UTF-8"))
     :reader (BufferedReader. (InputStreamReader. (PipedInputStream. from-worker 65536) "UTF-8"))
     :language :clojure :deadline-ms (+ (System/currentTimeMillis) 60000) :thread thread}))

(defn stop! [session] (.close ^java.io.Writer (:writer session)) (.join ^Thread (:thread session) 2000))
