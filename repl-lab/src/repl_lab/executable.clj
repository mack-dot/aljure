(ns repl-lab.executable
  "Load and call immutable exported functions through the selected worker backend."
  (:require [repl-lab.artifact :as artifact] [repl-lab.execution :as execution]
            [repl-lab.util :as u] [repl-lab.python-source :as python]))

(defn load! [backend worker target dependencies]
  (doseq [item (conj (vec dependencies) target)]
    (artifact/verify item)
    (u/ensure! (= (artifact/language target) (artifact/language item)) "Mixed executable languages" {})
    (u/ensure! (#{:analysis :policy} (:category item)) "Executable function required" {})
    (execution/evaluate! backend worker
      (case (artifact/language item)
        :clojure (str "(do (def " (get-in item [:interface :name]) " " (:source item) ") nil)")
        :python (:source item)) {})))

(defn call! [backend worker target arguments]
  (u/ensure! (and (vector? arguments) (= (count arguments) (get-in target [:interface :arity]))) "Export arity mismatch" {})
  (let [name (get-in target [:interface :name])]
    (execution/evaluate! backend worker
      (case (artifact/language target) :clojure (str "(apply " name " arguments)") :python (str name "(*arguments)"))
      {:arguments arguments})))

(defn invoke! [registry target arguments deadline]
  (binding [python/*deadline-ms* deadline]
  (let [dependencies (artifact/dependency-closure registry target)
        language (artifact/language target) _ (execution/require-tested! language)
        backend (execution/backend language) worker (execution/open! backend deadline)]
    (try
      (load! backend worker target dependencies)
      (call! backend worker target arguments)
      (finally (execution/close! backend worker))))))
