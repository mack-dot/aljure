(ns repl-lab.language-benchmark-test
  (:require [clojure.test :refer :all] [repl-lab.language-benchmark :as b]
            [repl-lab.execution :as x] [repl-lab.isolation :as iso]))

(deftest scorer-rejects-semantically-wrong-and-untransformed-programs
  (let [input [{:op "add" :value 2} {:op "add" :value 3} {:op "mul" :value 1}]
        good [{:op "add" :value 5}]]
    (is (b/correct? :transform input good))
    (is (not (b/correct? :transform input input)))
    (is (not (b/correct? :transform input [{:op "add" :value 6}])))
    (is (not (b/correct? :transform input [{:op "mul" :value 5}])))
    (is (not (b/correct? :transform input [{:op "add" :value 5 :hidden 1}])))
    (is (b/correct? :transform [] []))
    (is (not (b/correct? :aggregate [{:id "a" :ready true :weight 3}] {:ids ["a"] :total 4})))))

(deftest seeded-cases-and-metamorphic-interpretation
  (is (= (b/examples :aggregate 10) (b/examples :aggregate 10)))
  (is (not= (b/examples :aggregate 10) (b/examples :aggregate 11)))
  (doseq [seed (range 20) input (b/examples :transform seed) value [-5 0 3]]
    (is (= (b/interpret input value) (b/interpret (conj input {:op "add" :value 0} {:op "mul" :value 1}) value)))))

(deftest backend-selection-never-falls-back-and-python-gate-fails-closed
  (is (thrown? Exception (x/backend :ruby)))
  (with-redefs [iso/doctor (fn [& _] {:ready false :reason "test unavailable"})]
    (is (thrown-with-msg? Exception #"disabled" (x/open! (x/backend :python) nil)))))

(deftest worker-eof-retains-supervisor-diagnostics
  (let [worker {:writer (java.io.StringWriter.)
                :reader (java.io.BufferedReader. (java.io.StringReader. ""))
                :errors (future "Fixture supervisor failure; not a live failure")}
        error (try (iso/evaluate! worker "42" {}) nil (catch Exception e e))]
    (is (= "Worker terminated without result" (.getMessage error)))
    (is (= "Fixture supervisor failure; not a live failure" (:worker-stderr (ex-data error))))))
