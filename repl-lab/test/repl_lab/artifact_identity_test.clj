(ns repl-lab.artifact-identity-test
  "Regression tests for the identity, gain and attribution defects in
  research/RESEARCH_THESIS_REVIEW.md §3 and research/EXECUTABLE_LEARNING_EXPERIMENT.md §3."
  (:require [clojure.test :refer :all] [clojure.string :as str] [repl-lab.util :as u]
            [repl-lab.artifact :as a] [repl-lab.bundle :as bundle] [repl-lab.evaluation :as evaluation]
            [repl-lab.fixtures :as f] [repl-lab.provider :as provider] [repl-lab.sim :as sim]
            [repl-lab.workloads :as w] [repl-lab.runtime-test :refer [temp-root config]]))

(defn- analysis [source author parent]
  (a/make-artifact {:category :analysis :source source :interface {:name "tally" :arity 1}
                    :dependencies [] :author author :parent parent :provenance :developer-fixture}))

(deftest identical-code-has-one-code-hash-across-envelopes
  (let [one (analysis "(fn [items] (count items))" "session-a" nil)
        two (analysis "(fn [items] (count items))" "session-b" (:hash one))
        respaced (analysis "(fn [items]\n  (count items))" "session-a" nil)
        other (analysis "(fn [items] (count (distinct items)))" "session-a" nil)]
    ;; The defect: the provenance hash covers author, parent and source text.
    (is (not= (:hash one) (:hash two)))
    (is (not= (:hash one) (:hash respaced)))
    ;; The code hash covers the canonical forms only.
    (is (= (a/code-hash one) (a/code-hash two) (a/code-hash respaced)))
    (is (= (a/code-hash one) (a/forms-code-hash '(fn [items] (count items)))))
    (is (not= (a/code-hash one) (a/code-hash other)))
    (is (re-matches #"[a-f0-9]{64}" (a/code-hash one)))
    ;; Stored artifacts are unchanged: same file format, same provenance hash, still verify.
    (let [root (temp-root)]
      (a/save! root one)
      (is (= one (a/load! root (:hash one))))
      (is (not (contains? (a/load! root (:hash one)) :code-hash)))
      (is (= (a/code-hash one) (a/code-hash (a/load! root (:hash one))))))
    ;; The caller's print settings cannot change a code hash.
    (let [forms '(fn [m] (merge m {:a/x 1 :a/y 2}))]
      (is (= (binding [*print-namespace-maps* true] (a/forms-code-hash forms))
             (binding [*print-namespace-maps* false] (a/forms-code-hash forms)))))))

(deftest cold-boot-restore-keeps-the-code-hash
  ;; The defect: a cold-boot restore builds new envelopes, so every provenance hash changes.
  (let [root (temp-root) output (str root "/export")]
    (doseq [artifact [f/packed-policy f/improved-workflow]] (a/save! root artifact))
    (bundle/export! root output (:hash f/improved-workflow) :synthetic-fixture)
    (let [restored (get-in (evaluation/restore-library (bundle/load-bundle output)) [:by-original (:hash f/packed-policy)])]
      (is (not= (:hash f/packed-policy) (:hash restored)))
      (is (= (a/code-hash f/packed-policy) (a/code-hash restored))))))

(defn- healthy [case makespan]
  {:case case :status :complete :completed 4 :makespan makespan :score makespan :accepted-invariant-violations 0})
(defn- worker-failure [case]
  ;; sim/execution-failure: the run stopped before the policy was first called.
  {:case case :status :execution-failure :completed 0 :makespan nil :score 4800 :accepted-invariant-violations 0})

(deftest infrastructure-failed-pairs-do-not-inflate-the-promotion-gain
  (let [rule (:promotion config) cases ["d1" "d2" "d3" "d4" "d5" "d6"]]
    ;; The first live run (research/FIRST_LIVE_RESULTS.md): parents 145, 145, 154 and three
    ;; worker failures; candidate 37, 35, 40, 36, 59, 47. The recorded gain was 37,630.
    (let [old (into (mapv healthy (take 3 cases) [145 145 154]) (map worker-failure (drop 3 cases)))
          new (mapv healthy cases [37 35 40 36 59 47])
          evidence (a/promotion-evidence old new rule)]
      (is (= (- (+ 145 145 154) (+ 37 35 40)) (:score-gain evidence)))
      (is (= ["d4" "d5" "d6"] (:excluded-pairs evidence)))
      (is (= 3 (:healthy-pairs evidence)))
      (is (:approved evidence)))
    ;; No improvement on any healthy pair: failed parents alone must not approve a candidate.
    (let [old (conj (mapv healthy ["d1" "d2"] [50 60]) (worker-failure "d3"))
          new (mapv healthy ["d1" "d2" "d3"] [50 60 70])
          evidence (a/promotion-evidence old new rule)]
      (is (zero? (:score-gain evidence)))
      (is (not (:approved evidence))))
    ;; A candidate that never ran on a case cannot be approved on the others.
    (let [old [(worker-failure "d1") (healthy "d2" 90)]
          new [(worker-failure "d1") (healthy "d2" 40)]
          evidence (a/promotion-evidence old new rule)]
      (is (= ["d1"] (:candidate-execution-failures evidence)))
      (is (not (:approved evidence))))
    ;; Without one healthy pair there is no evidence.
    (is (not (:approved (a/promotion-evidence [(worker-failure "d1")] [(healthy "d1" 10)] rule))))
    ;; Healthy panels are decided exactly as before.
    (let [old [(healthy "d1" 10)] new [(healthy "d1" 8)]]
      (is (= [true 2] ((juxt :approved :score-gain) (a/promotion-evidence old new rule))))
      (is (not (:approved (a/promotion-evidence old old rule))))
      (is (not (:approved (a/promotion-evidence old [(assoc (first new) :completed 3)] rule)))))))

(defn- invocation-line [root episode]
  (u/json-read (first (str/split-lines (slurp (str root "/episodes/" episode ".jsonl"))))))

(deftest a-failed-episode-names-no-executed-artifact
  (let [root (temp-root) world (w/generate 7 {:size 4})
        policy f/packed-policy
        failing (fn [& _] (throw (ex-info "Worker terminated without result" {})))
        [failed] (evaluation/code-panel! root "retained-code" [world] policy failing config)
        [ran] (evaluation/code-panel! root "control" [world] policy (fn [_ world options] (sim/run-episode world f/packed options)) config)]
    ;; The defect: the retained hash was recorded although nothing ran.
    (is (nil? (:artifact failed)))
    (is (= (:hash policy) (:assigned-artifact failed)))
    (is (nil? (:artifact (invocation-line root "retained-code-0"))))
    (is (= (:hash policy) (:assigned-artifact (invocation-line root "retained-code-0"))))
    (is (zero? (:calls (invocation-line root "retained-code-0"))))
    ;; A run that invoked the policy keeps its attribution, unchanged.
    (is (= (:hash policy) (:artifact ran)))
    (is (not (contains? ran :assigned-artifact)))
    (is (= (:hash policy) (:artifact (invocation-line root "control-0"))))
    (is (not (contains? (invocation-line root "control-0") :assigned-artifact))))
  ;; The paired evaluation episode: a failed agent run is not reuse of the retained policy.
  (let [root (temp-root) world (w/generate 8 {:size 4})
        unavailable (reify provider/Provider
                      (invoke! [_ _ _ _ _] (throw (ex-info "Fixture provider unavailable" {}))))
        record (evaluation/episode! {:root root :id "attribution" :config config :provider unavailable
                                     :execute (fn [& _] (throw (ex-info "must not run" {})))
                                     :provenance :synthetic-fixture}
                                    "evolving" 0 world f/initial-workflow f/initial-policy)]
    (is (= :execution-failure (get-in record [:metrics :status])))
    (is (nil? (:artifact record)))
    (is (= (:hash f/initial-policy) (:assigned-artifact record)))))
