(ns repl-lab.isolation (:require [repl-lab.util :as u] [repl-lab.limits :as limits] [clojure.java.io :as io])
  (:import [java.util.concurrent TimeUnit]))
(defn verify-limits [check requested]
  (let [limits (:limits check)
        actual {:memory-mb (:memory_mb limits) :cpus (:cpus limits) :pids (:pids limits)
                :scratch-mb (:scratch_mb limits) :wall-ms (* 1000 (get limits :wall_seconds 0))
                :output-bytes (:output_bytes limits)}]
    (if (and (:ready check) (not= requested actual))
      (assoc check :ready false :reason "Configured isolation limits differ from the enforced worker limits"
             :requested requested :enforced actual)
      check)))
(defn script [language]
  (case language :clojure "scripts/isolation.py" :python "scripts/python_isolation.py"
        (u/fail "Unknown execution language" {:language language})))
(defn doctor
  ([] (doctor :clojure))
  ([language]
  (let [p (.start (ProcessBuilder. ^java.util.List ["python3" (script language) "doctor"]))
        output (future (slurp (.getInputStream p)))]
    (if (.waitFor p 12 TimeUnit/SECONDS) (verify-limits (u/json-read @output) (:isolation (u/read-file "config/experiment.edn")))
      (do (.destroyForcibly p) {:ready false :reason "Isolation preflight timeout"})))))
(def negative-cases #{:loop :allocation :oversized-result :read :write :process :network :evaluator :reader-eval})
(defn validate-proof! [check proof]
  (u/ensure! (:ready check) "Generated-code execution disabled" check)
  (u/ensure! (and (= "TESTED" (:status proof)) (= 2 (:gate-version proof))
                  (= (:supervisor-sha256 proof) (u/sha (slurp "scripts/isolation.py")))
                  (= negative-cases (set (keys (:startup proof)))) (every? true? (vals (:startup proof)))
                  (= (:image check) (:image proof))
                  (= negative-cases (set (keys (:results proof))))
                  (every? true? (vals (:results proof))))
             "Isolation proof is incomplete or differs from the worker image; run make isolation-test" {})
  check)
(defn require-tested! []
  (let [check (doctor) path (io/file "var/isolation-proof.json")]
    (u/ensure! (:ready check) "Generated-code execution disabled" check)
    (u/ensure! (.isFile path) "Run make isolation-test successfully before live execution" {})
    (validate-proof! check (u/json-read (slurp path)))))
(defn open-session!
  ([] (open-session! nil))
  ([deadline-ms] (open-session! deadline-ms :clojure))
  ([deadline-ms language]
  (limits/timeout-ms deadline-ms 120000)
  (let [check (if (= language :clojure) (doctor) (doctor language))]
    (u/ensure! (:ready check) "Generated-code execution disabled" check)
    (limits/timeout-ms deadline-ms 120000)
    (let [builder (ProcessBuilder. ^java.util.List ["python3" (script language) "session"])
          _ (when deadline-ms (.put (.environment builder) "REPL_LAB_TASK_DEADLINE_MS" (str deadline-ms)))
          p (.start builder)]
      {:process p :writer (io/writer (.getOutputStream p)) :reader (io/reader (.getInputStream p))
       :language language :deadline-ms deadline-ms :errors (future (slurp (.getErrorStream p)))}))))
(defn close-session! [{:keys [process writer]}]
  (.close writer)
  ;; Closing stdin asks the supervisor to reap the entire container. The supervisor
  ;; enforces its own wall deadline even if this controller crashes.
  (when-not (.waitFor process 20 TimeUnit/SECONDS)
    (u/fail "Supervisor did not confirm worker termination" {})))
(defn request! [{:keys [process writer reader deadline-ms language] :as session} request]
  (let [wire ((if (= language :python) u/json-str pr-str) request)]
    (limits/timeout-ms deadline-ms 20000)
    (u/ensure! (<= (count (.getBytes wire "UTF-8")) 65535) "Worker input too large" {})
    (.write writer (str wire "\n")) (.flush writer)
    (let [read-result (future (.readLine reader)) line (deref read-result (limits/timeout-ms deadline-ms 20000) ::timeout)]
      (when (= line ::timeout) (close-session! session) (u/fail "Worker response timeout" {}))
      (u/ensure! (string? line) "Worker terminated without result"
                 (when-not (string? line)
                   {:worker-stderr (if-let [errors (:errors session)] (deref errors 5000 "Diagnostics unavailable") "Diagnostics unavailable")}))
      (u/ensure! (<= (count line) 65536) "Worker result too large" {})
      (let [result ((if (= language :python) u/json-read u/read-edn) line)]
        (u/ensure! (not (:error result)) (str "Worker rejected expression: " (:error result)) {:error (:error result)})
        (:value result)))))

(defn evaluate! [session source bindings]
  (request! session {:source source :bindings bindings}))
