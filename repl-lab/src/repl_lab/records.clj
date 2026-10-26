(ns repl-lab.records
  (:require [clojure.java.io :as io] [clojure.string :as str]
            [repl-lab.util :as u] [repl-lab.sim :as sim] [repl-lab.model-protocol :as wire]))

(defn save-episode! [root case-id world run metadata]
  (u/ensure! (re-matches #"[a-zA-Z0-9-]+" case-id) "Invalid episode filename" {})
  (sim/replay world (:records run) (:final-hash run) (get-in run [:metrics :status]))
  (let [record (merge {:case (u/hash-value world) :world world :metrics (:metrics run)
                       :records (:records run) :final-hash (:final-hash run) :error (:error run)
                       :timeline (get-in run [:state :history]) :attempts (get-in run [:state :attempts])
                       :wall-ms (:wall-ms run)} metadata)
        base (str (io/file root "episodes" case-id))
        invocation {:type :policy-invocation :artifact (:artifact record) :workflow (:workflow record)
                    :input-kind :permitted-observation :arm (:arm record) :case (:case record)
                    :calls (get-in run [:metrics :policy-calls] 0)}]
    (u/write-edn! (str base ".edn") record)
    (u/atomic-write! (str base ".jsonl")
                     (str (str/join "\n" (map u/json-str (cons invocation (:records run)))) "\n"))
    record))

(defn write-events! [path events]
  (u/atomic-write! path (str (str/join "\n" (map wire/json-text events)) "\n")))
