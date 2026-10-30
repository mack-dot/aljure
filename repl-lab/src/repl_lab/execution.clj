(ns repl-lab.execution
  "Language selection for the existing broker; no controller or provider changes."
  (:require [clojure.java.io :as io] [repl-lab.isolation :as isolation] [repl-lab.util :as u]))

(defprotocol ExecutionBackend
  (open! [backend deadline-ms])
  (evaluate! [backend worker source bindings])
  ;; The programmatic tool bridge (repl-lab.programs): one evaluation under a tool grant,
  ;; whose requests the handler answers. Only the SCI worker implements it.
  (run-program! [backend worker source bindings tools handler])
  (close! [backend worker]))

(def python-negative-cases
  #{:loop :allocation :oversized-result :read :write :process :network :evaluator :host-environment :session-reset})

(defn require-tested! [language]
  (if (= language :clojure)
    (isolation/require-tested!)
    (let [check (isolation/doctor language) file (io/file "var/python-isolation-proof.json")]
      (u/ensure! (:ready check) "Python generated-code execution disabled" check)
      (u/ensure! (.isFile file) "Run make python-isolation-test before Python execution" {})
      (let [proof (u/json-read (slurp file))]
        (u/ensure! (and (= "TESTED" (:status proof)) (= (:image check) (:image proof))
                        (= python-negative-cases (set (keys (:results proof))))
                        (every? true? (vals (:results proof))) (:positive_control proof))
                   "Python isolation proof is incomplete or belongs to another image" {})
        check))))

(defrecord ClojureExecutionBackend []
  ExecutionBackend
  (open! [_ deadline] (isolation/open-session! deadline))
  (evaluate! [_ worker source bindings] (isolation/evaluate! worker source bindings))
  (run-program! [_ worker source bindings tools handler] (isolation/run-program! worker source bindings tools handler))
  (close! [_ worker] (isolation/close-session! worker)))

(defrecord PythonExecutionBackend []
  ExecutionBackend
  (open! [_ deadline]
    (require-tested! :python)
    (isolation/open-session! deadline :python))
  (evaluate! [_ worker source bindings] (isolation/evaluate! worker source bindings))
  (run-program! [_ _ _ _ _ _] (u/fail "Programs are unavailable in the Python worker" {}))
  (close! [_ worker] (isolation/close-session! worker)))

(defn backend [language]
  (case language :clojure (->ClojureExecutionBackend) :python (->PythonExecutionBackend)
        (u/fail "Unknown execution language" {:language language})))

(defn for-run [ledger] (backend (get-in ledger [:config :execution-language] :clojure)))
