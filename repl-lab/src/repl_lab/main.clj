(ns repl-lab.main
  (:require [clojure.java.io :as io] [repl-lab.util :as u] [repl-lab.isolation :as iso]
            [repl-lab.experiment :as experiment] [repl-lab.live :as live] [repl-lab.bundle :as bundle]
            [repl-lab.evaluation :as evaluation] [repl-lab.smoke :as smoke])
  (:import [java.util.concurrent TimeUnit]))

(defn run-root [id]
  (let [id (if (seq id) id (when (.exists (io/file "var/latest-run")) (slurp "var/latest-run")))]
    (u/ensure! (and id (re-matches #"[a-z]+-[0-9]+" id)) "Supply a recorded RUN_ID" {})
    (let [paths (map #(str % id) ["var/runs/" "var/evaluations/"])
          found (filter #(.isDirectory (io/file %)) paths)]
      (u/ensure! (= 1 (count found)) "Recorded run is missing or ambiguous" {:id id})
      (first found))))
(defn process! [command timeout-seconds]
  (let [p (.start (doto (ProcessBuilder. ^java.util.List command) (.inheritIO)))]
    (when-not (.waitFor p timeout-seconds TimeUnit/SECONDS)
      (.destroyForcibly p) (u/fail "Command timeout" {:command (first command)}))
    (u/ensure! (zero? (.exitValue p)) "Command failed" {:exit (.exitValue p)})))
(defn doctor []
  {:offline-ready true :java (System/getProperty "java.version") :clojure (clojure-version)
   :isolation (iso/doctor) :paid-calls-default :disabled
   :dependencies (u/read-file "deps.edn")
   :note "Offline readiness covers trusted fixtures. Generated-code tests need a verified worker image."})
(defn -main [& [command arg1 arg2]]
  (try
    (let [result
          (case command
            "doctor" (doctor)
            "fixture-demo" (experiment/fixture-demo!)
            "smoke" (smoke/smoke! (into {} (System/getenv)))
            "evolve" (live/evolve! (into {} (System/getenv)))
            "resume" (live/resume! (run-root arg1) (into {} (System/getenv)))
            ("evaluate" "cold-evaluate")
            (do (u/ensure! (seq arg1) "EXPORT path is required" {})
                (if (= :synthetic-fixture (get-in (bundle/load-bundle arg1) [:manifest :provenance]))
                  (experiment/evaluate! arg1 (if (seq arg2) arg2 "heldout") (str "var/evaluations/eval-" (System/currentTimeMillis)))
                  (evaluation/evaluate-live! arg1 (if (seq arg2) arg2 "heldout") (into {} (System/getenv)) (= command "cold-evaluate"))))
            "cold-boot" (do
                          (u/ensure! (seq arg1) "EXPORT path is required" {})
                          ;; A new JVM has no old REPL vars or controller sessions.
                          (process! ["python3" "scripts/clj.py" "-m" "repl-lab.main" "cold-evaluate" arg1 "heldout"] 3600)
                          {:mode :fresh-process :export arg1 :note "See child report for provenance and hypothesis status."})
            "replay" (experiment/replay! (run-root arg1))
            "demo" (do (process! ["python3" "scripts/demo.py" (run-root arg1)] 60)
                       {:dashboard "dashboard/dist/index.html" :provenance :recorded-data})
            (u/fail "Commands: doctor, test (make), fixture-demo, smoke, evolve, resume, evaluate, cold-boot, replay, demo" {}))]
      (println (u/json-str result))
      (shutdown-agents))
    (catch Exception e
      (binding [*out* *err*] (println (u/json-str {:error (.getMessage e) :data (ex-data e)})))
      (shutdown-agents) (System/exit 2))))
