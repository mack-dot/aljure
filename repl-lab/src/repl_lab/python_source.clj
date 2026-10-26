(ns repl-lab.python-source
  "Python syntax operations run in a fresh, verified, syntax-only worker."
  (:require [repl-lab.execution :as execution] [repl-lab.isolation :as isolation]))

(def ^:dynamic *deadline-ms* nil)

(defn request! [request]
  (let [backend (execution/backend :python)
        worker (execution/open! backend (or *deadline-ms* (+ (System/currentTimeMillis) 30000)))]
    (try (isolation/request! worker request)
         (finally (execution/close! backend worker)))))

(defn parse! [source] (request! {:operation "parse" :source source}))
(defn render! [forms] (request! {:operation "render" :forms forms}))
