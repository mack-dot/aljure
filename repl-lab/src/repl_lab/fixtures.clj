(ns repl-lab.fixtures (:require [repl-lab.artifact :as a] [repl-lab.util :as u]))

;; These are developer-authored, reviewed fixtures. This macro preserves the exact
;; compiled function form. It never reads or evaluates submitted candidate source.
(defmacro fixture-function [name form]
  `(do (def ~name ~form) (def ~(symbol (str name "-form")) (quote ~form))))

(fixture-function serial
  (fn [observation memory]
    (let [job (first (filter :ready (:jobs observation)))
          worker (first (filter (fn [w] (and (:up w)
                                             (every? (fn [[r n]] (<= n (get (:available w) r 0))) (:resources job)))) (:workers observation)))]
      {:actions (if (and job worker (not-any? (fn [j] (= :running (:status j))) (:jobs observation)))
                  [{:op :dispatch :job (:id job) :worker (:id worker)}] [{:op :wait :ticks 1}])
       :memory memory})))

(fixture-function packed
  (fn [observation memory]
    (let [[actions workers]
          (reduce (fn [[actions workers] job]
                    (let [worker (first (sort-by (fn [w] [(- (:speed w)) (:id w)])
                                                (filter (fn [w] (and (:up w) (every? (fn [[r n]] (<= n (get (:available w) r 0))) (:resources job)))) workers)))]
                      (if worker
                        [(conj actions {:op :dispatch :job (:id job) :worker (:id worker)})
                         (mapv (fn [w] (if (= (:id worker) (:id w))
                                         (update w :available (fn [r] (merge-with - r (:resources job)))) w)) workers)]
                        [actions workers])))
                  [[] (:workers observation)] (sort-by (fn [j] [(- (:estimate j)) (:id j)]) (filter :ready (:jobs observation))))]
      {:actions (if (seq actions) actions [{:op :wait :ticks 1}]) :memory memory})))

(defn policy [form parent]
  (a/make-artifact {:category :policy :source (pr-str form) :interface {:name "decide" :arity 2}
                    :dependencies [] :author "developer-fixture" :parent parent :provenance :developer-fixture}))
(def initial-policy (policy serial-form nil))
(def packed-policy (policy packed-form (:hash initial-policy)))
(def initial-workflow
  (a/make-artifact {:category :workflow
                    :source (pr-str {:strategy {:policy (:hash initial-policy)
                                               :context {:limit 4 :select [:id :estimate :status]}
                                               :delegate {:task "Summarize scheduling constraints."}}})
                    :interface {:name "investigate" :version 1} :dependencies [(:hash initial-policy)]
                    :author "developer-fixture" :parent nil :provenance :developer-fixture}))
(def improved-workflow
  (let [patched (a/patch initial-workflow
                 {:base-hash (:hash initial-workflow) :path [:strategy]
                  :expected-hash (u/hash-value (get-in initial-workflow [:forms :strategy]))
                  :replacement {:policy (:hash packed-policy)
                                :context {:where {:ready true} :limit 32 :select [:id :deps :resources :estimate]}
                                :delegate {:task "Analyze the ready frontier and resource bottlenecks."}}
                  :dependencies [(:hash packed-policy)] :author "developer-fixture"})]
    (a/make-artifact (assoc patched :dependencies [(:hash packed-policy)]))))
(def approved-fixture-functions {(:hash initial-policy) serial (:hash packed-policy) packed})
(defn resolve-policy [artifact]
  (a/verify artifact)
  (or (get approved-fixture-functions (:hash artifact))
      (u/fail "Only exact compiled developer fixtures can use the trusted executor" {:hash (:hash artifact)})))
