(ns repl-lab.program-library-test
  "Program artifacts: identity with declared capabilities, validation on fixtures through the real
  bridge (fake worker), the frozen rule, capture with quarantine reasons, parameterization, and
  library entries. Offline: no Docker, no model."
  (:require [clojure.test :refer [deftest is testing]] [clojure.string :as str]
            [repl-lab.program-library :as pl] [repl-lab.programs :as programs] [repl-lab.bridge :as bridge]
            [repl-lab.bridge-fake :as fake] [repl-lab.isolation :as isolation] [repl-lab.artifact :as a]
            [repl-lab.skills :as skills] [repl-lab.controller :as c] [repl-lab.util :as u]
            [repl-lab.model-protocol :as wire]))

(def close-stale-source
  (str "(fn [status] (let [stale (:items (tool \"service_list\" {:collection \"issues\" :where {:status status}}))] "
       "(doseq [i stale] (tool \"service_update\" {:collection \"issues\" :id (:id i) :fields {:status \"closed\"} "
       ":idempotency-key (str \"close-\" (:id i))})) (count stale)))"))

(def envelope {:author "developer-fixture" :provenance :developer-fixture})

(defn- fixture [n]
  {:collections {"issues" (into {} (for [i (range 1 (inc n))] [(str "i" i) {:status (if (odd? i) "stale" "open")}]))}})

(defn- expected-state [n]
  {"issues" (into {} (for [i (range 1 (inc n))] [(str "i" i) {:status (if (odd? i) "closed" "open")}]))})

(defn- store []
  (let [root (str (System/getProperty "java.io.tmpdir") "/program-library-test-" (System/nanoTime))
        store (str root "/controller.sqlite")]
    (c/create-run! store "v" (merge (u/read-file "config/experiment.edn") {:response-envelope wire/tool-envelope-version}) nil)
    [root store]))

(def grant (programs/grant {:tools [{:name "service_list"} {:name "service_update" :approval "preapproved"}]}))

;; The fake worker: a Clojure version of close-stale-source, called the way validate! calls it.
(defn- close-stale [status]
  (let [stale (:items (bridge/tool "service_list" {:collection "issues" :where {:status status}}))]
    (doseq [i stale] (bridge/tool "service_update" {:collection "issues" :id (:id i) :fields {:status "closed"}
                                                    :idempotency-key (str "close-" (:id i))}))
    (count stale)))

(defn- evaluator [f]
  (fn [source bindings]
    (cond (str/starts-with? source "(do (def") nil
          (str/starts-with? source "(apply") (apply f (:arguments bindings))
          :else (throw (ex-info (str "unexpected source " source) {})))))

(deftest a_program_declares_exactly_the_tools_it_calls
  (let [p (pl/make-program (assoc envelope :source close-stale-source :name "close-stale"))]
    (is (= :program (:category p)))
    (is (= ["service_list" "service_update"] (:capabilities p)))
    (is (= 1 (get-in p [:interface :arity])))
    (is (= p (a/verify p)))
    (is (= (a/code-hash p) (a/code-hash (assoc p :author "someone-else"))) "code identity ignores the envelope")
    (is (pl/requires-within? p grant))
    (is (not (pl/requires-within? p (programs/grant {:tools [{:name "service_list"}]}))))
    (is (thrown-with-msg? Exception #"Unknown tools" (pl/make-program (assoc envelope :source "(fn [] (tool \"shell\" {}))" :name "x"))))
    (is (thrown-with-msg? Exception #"literal string" (pl/make-program (assoc envelope :source "(fn [n] (tool n {}))" :name "x"))))
    (is (thrown-with-msg? Exception #"at least one tool" (pl/make-program (assoc envelope :source "(fn [x] (inc x))" :name "x"))))
    (is (thrown-with-msg? Exception #"capabilities" (a/make-artifact (assoc envelope :category :analysis :source "(fn [x] x)" :interface {:name "f" :arity 1}
                                                                            :dependencies [] :parent nil :capabilities ["service_get"])))
        "only a program declares capabilities")))

(deftest validation_runs_each_case_on_its_own_fixture_through_the_bridge_and_the_rule_needs_two_fixtures
  (let [[_ store] (store) p (pl/make-program (assoc envelope :source close-stale-source :name "close-stale"))
        session (fake/session (evaluator close-stale))
        run (fn [source bindings tools handler] (isolation/run-program! session source bindings tools handler))]
    (try
      (let [cases [{:case "five" :fixture (fixture 5) :arguments ["stale"] :expected 3 :expected-state (expected-state 5)}
                   {:case "eight" :fixture (fixture 8) :arguments ["stale"] :expected 4 :expected-state (expected-state 8)}
                   {:case "none" :fixture (fixture 2) :arguments ["missing"] :expected 0 :expected-state (:collections (fixture 2))}]
            rows (pl/validate! {:store store :run-id "v" :grant grant} p cases run)]
        (is (= [true true true] (mapv :passed rows)))
        (is (= [4 5 1] (mapv :ops rows)))
        (is (= [3 4 0] (mapv :effects rows)))
        (is (true? (:approved (pl/decide rows cases))))
        ;; A wrong expectation fails the case on value, the state still matching.
        (let [wrong (pl/validate! {:store store :run-id "v" :grant grant} p [(assoc (first cases) :expected 99)] run)]
          (is (= [false] (mapv :passed wrong)))
          (is (= [false] (mapv :value-ok wrong))) (is (= [true] (mapv :state-ok wrong))))
        ;; One fixture, however many cases, is not enough for the rule.
        (let [same [(first cases) (assoc (first cases) :case "again")]]
          (is (false? (:approved (pl/decide (pl/validate! {:store store :run-id "v" :grant grant} p same run) same)))))
        ;; Every operation was recorded with its validation origin.
        (is (some #(= "validate/five/program-1" (get-in % [:payload :origin])) (:events (c/get-run store "v")))))
      (finally (fake/stop! session)))))

(deftest capture_reads_program_sources_and_quarantines_task_data
  (let [sources ["(let [stale (:items (tool \"service_list\" {:collection \"issues\" :where {:status \"stale\"}}))] (count stale))"
                 "(tool \"service_update\" {:collection \"issues\" :id \"i3\" :fields {:status \"closed\"} :idempotency-key \"k\"})"
                 "(count (filter #(re-find #\"stale\" %) context-lines))"
                 "(helper (tool \"service_get\" {:collection \"issues\" :id (first ids)}))"
                 "(let [stale (:items (tool \"service_list\" {:collection \"issues\" :where {:status \"stale\"}}))] (count stale))"]
        found (pl/candidates sources ["i1" "i2" "i3"])]
    (is (= 4 (count found)) "the repeated source is one candidate, its latest recording kept")
    (is (= [[[:embedded-task-data "i3"]] [[:session-data "context-lines"] [:no-tool-call]] [[:unresolved "helper"] [:unresolved "ids"]] []]
           (mapv :reasons found)))
    (is (= [1 2 3 4] (mapv :index found)))
    (is (= ["service_list"] (:capabilities (last found))))
    (is (str/starts-with? (:source (last found)) "(fn [] (let [stale"))
    (is (= "p4" (:id (last found))))
    ;; The eligible candidate becomes a program artifact; a quarantined one is refused by its reasons, not by chance.
    (let [p (pl/make-program (assoc envelope :source (:source (last found)) :name "count-stale"))]
      (is (= 0 (get-in p [:interface :arity]))))))

(deftest parameterization_lifts_a_pinned_literal_into_a_parameter
  (let [p (pl/make-program (assoc envelope :source "(fn [] (count (:items (tool \"service_list\" {:collection \"issues\" :where {:status \"stale\"}}))))" :name "count-stale"))
        ;; (fn [] (count (:items (tool "service_list" {... :where {:status "stale"}})))): path to "stale"
        path [2 1 1 2 :where :status]
        target (a/subtree (:forms p) path)
        q (pl/parameterize p {:path path :expected-hash (u/hash-value target) :parameter 'status
                              :author "controller" :provenance :controller-generated})]
    (is (= "stale" target))
    (is (= 1 (get-in q [:interface :arity])))
    (is (= (:hash p) (:parent q)))
    (is (= ["service_list"] (:capabilities q)))
    (is (= '(fn [status] (count (:items (tool "service_list" {:collection "issues" :where {:status status}})))) (:forms q)))
    (is (thrown-with-msg? Exception #"Ambiguous or changed" (pl/parameterize p {:path path :expected-hash "0" :parameter 'x :author "c" :provenance :controller-generated})))
    (is (thrown-with-msg? Exception #"literal value" (pl/parameterize p {:path [2] :expected-hash (u/hash-value (a/subtree (:forms p) [2])) :parameter 'x :author "c" :provenance :controller-generated})))))

(deftest a_library_version_holds_a_program_with_its_predicate_and_receipt
  (let [[root _] (store)
        p (pl/make-program (assoc envelope :source close-stale-source :name "close-stale"))
        predicate (a/make-artifact (assoc envelope :category :analysis :source "(fn [input] (clojure.string/includes? (:question input) \"stale\"))"
                                          :interface {:name "applicable" :arity 1} :dependencies [] :parent nil))]
    (a/save! root p) (a/save! root predicate)
    (let [empty (skills/write-library! root {:schema :aljure-library-v1 :parent nil :entries []})
          evidence {:approved true :no-regression true :score-gain 0 :old [] :new [] :rule pl/rule}
          sha (skills/add-entry! root empty {:artifact p :applicability predicate :summary "closes stale issues"} evidence)
          found (skills/discover root sha)]
      (is (= 1 (count (:approved found))))
      (is (= :program (get-in found [:approved 0 :function :category])))
      (is (= ["service_list" "service_update"] (get-in found [:approved 0 :function :capabilities]))))))
