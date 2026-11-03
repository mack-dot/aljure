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
(def python-proof-path "var/python-isolation-proof.json")

(defn validate-python-proof!
  "Gate v2 parity with isolation/validate-proof!: the shared supervisor's and the gate's
  hashes, readiness confirmed in the same worker before every negative case, both sides
  of the output boundary, every negative case, the image, and the positive control."
  [check proof]
  (u/ensure! (:ready check) "Python generated-code execution disabled" check)
  (u/ensure! (and (= "TESTED" (:status proof)) (= 2 (:gate-version proof))
                  (= (:supervisor-sha256 proof) (u/sha (slurp "scripts/isolation.py")))
                  (= (:gate-sha256 proof) (u/sha (slurp "scripts/python_isolation.py")))
                  (= (:image check) (:image proof))
                  (= python-negative-cases (set (keys (:startup proof)))) (every? true? (vals (:startup proof)))
                  (= #{:at-bound :over-bound} (set (keys (:boundary proof)))) (every? true? (vals (:boundary proof)))
                  (= python-negative-cases (set (keys (:results proof))))
                  (every? true? (vals (:results proof))) (:positive_control proof))
             "Python isolation proof is incomplete, stale or belongs to another image; run make python-isolation-test" {})
  check)

(defn require-tested! [language]
  (if (= language :clojure)
    (isolation/require-tested!)
    (let [check (isolation/doctor language) file (io/file python-proof-path)]
      (u/ensure! (:ready check) "Python generated-code execution disabled" check)
      (u/ensure! (.isFile file) "Run make python-isolation-test before Python execution" {})
      (validate-python-proof! check (u/json-read (slurp file))))))

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
  ;; Source is a string, or a request map {:source :display} / {:source :answer} built by
  ;; repl-lab.model-protocol: the Python worker shows results and keeps answers itself.
  (evaluate! [_ worker source bindings] (isolation/evaluate! worker source bindings))
  (run-program! [_ _ _ _ _ _] (u/fail "Programs are unavailable in the Python worker" {}))
  (close! [_ worker] (isolation/close-session! worker)))

(defn language
  "The execution language of a backend; initialization and result display differ by it."
  [backend]
  (if (instance? PythonExecutionBackend backend) :python :clojure))

(defn backend [language]
  (case language :clojure (->ClojureExecutionBackend) :python (->PythonExecutionBackend)
        (u/fail "Unknown execution language" {:language language})))

(defn for-run [ledger] (backend (get-in ledger [:config :execution-language] :clojure)))
