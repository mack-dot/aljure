(ns repl-lab.selector-gate-test
  (:require [clojure.test :refer :all] [repl-lab.selector-gate :as gate]
            [repl-lab.artifact :as a] [repl-lab.util :as u] [repl-lab.runtime-test :as rt]
            [repl-lab.sim :as sim] [repl-lab.fixtures :as f] [repl-lab.workloads :as w]
            [repl-lab.executable :as executable] [repl-lab.skill-discovery :as discovery]))

(def candidate (a/make-artifact {:category :analysis :source "(fn [input] {:route :synthesize})"
                                :interface {:name "select-route" :arity 1} :dependencies []
                                :parent nil :author "fixture-author" :provenance :developer-fixture}))
(defn usage [usd] {:reserved {:usd 0 :calls 0 :tokens 0}
                  :provider-requests {"fixture" {:status :complete :response {:usd usd}}}})
(defn options []
  (let [worlds [(w/generate 850000 {:size 3 :structure :independent :fault-count 0})]]
    {:root (rt/temp-root) :candidate candidate :mode :fixture :development-worlds worlds
     :authoring-ledger (usage 0.01) :registry []
     :config (assoc rt/config :development-case-hashes (mapv u/hash-value worlds))
     :control-decisions {:deterministic-reuse (constantly {:route :adapt})
                         :descriptive-discovery (constantly {:route :delegate})
                         :applicability-guard (constantly {:route :compute})}
     :execute-route (fn [decision world limits]
                      {:episode (sim/run-episode world f/packed limits)
                       :ledger (usage ({:adapt 0 :delegate 0.1 :compute 0.05 :synthesize 0} (:route decision)))})}))

(deftest development-gate-accepts-rejects-and-keeps-hidden-data-out
  (let [seen (atom [])]
    (with-redefs [executable/invoke! (fn [_ _ [public] _] (swap! seen conj public) {:route :synthesize})]
      (let [accepted (gate/adjudicate! (options))]
        (is (= :fixture-accepted (:status accepted)))
        (is (= :FIXTURE (:evidence-category accepted)))
        (is (false? (:active-library-changed accepted)))
        (is (= :NOT-RUN (:held-out-result accepted)))
        (is (not (:independent-authorship accepted))))
      (is (= #{:observation :skills} (set (keys (first @seen)))))
      (is (not-any? #(contains? % :actual) (get-in (first @seen) [:observation :jobs])))
      (is (not-any? #(contains? (:observation (first @seen)) %) [:seed :faults :fault-seed :hidden-outcomes]))
      (let [rejected (gate/adjudicate! (assoc (options) :authoring-ledger (usage 0.2)))]
        (is (= :fixture-rejected (:status rejected)))
        (is (false? (:cheaper-than-directed rejected))))
      (let [o (options) execute (:execute-route o)
            result (gate/adjudicate! (assoc o :execute-route (fn [& args] (assoc (apply execute args) :failure-stage :startup))))]
        (is (= :unverified-infrastructure (:status result))))
      (is (= :validation-error (:status (gate/adjudicate! (assoc (options) :mode :live)))))
      (is (= :validation-error (:status (gate/adjudicate! (assoc-in (options) [:config :development-case-hashes] ["changed"])))))
      (let [o (options) execute (:execute-route o)]
        (is (= :validation-error (:status
              (gate/adjudicate! (assoc o :execute-route
                (fn [& args] (assoc-in (apply execute args) [:episode :metrics :score] -100)))))))))))

(deftest source-authorship-and-output-contract
  (let [model-candidate (a/make-artifact (assoc candidate :provenance :model-generated))
        command (assoc (select-keys model-candidate [:category :source :interface :dependencies :parent]) :op :artifact/submit)
        ;; Synthetic provider receipt. No model call occurs in this test.
        ledger {:config {:mode :live} :events [{:type :artifact-staged :payload {:hash (:hash model-candidate) :session "fixture-author"}}]
                :provider-requests {"mock" {:status :complete :session "fixture-author"
                                           :response {:provenance :recorded-model-run :model "claude-sonnet-5-5"
                                                      :requested-model "claude-sonnet-5-5" :text (pr-str command)}}}}]
    (is (gate/authored? model-candidate ledger))
    (is (not (gate/authored? model-candidate (assoc ledger :events []))))
    (is (not (gate/authored? model-candidate (assoc-in ledger [:provider-requests "mock" :response :text] "{:op :done :summary \"claimed improvement\"}")))))
  (is (thrown? Exception (gate/decision! {:route :reuse :hash "unapproved"} #{})))
  (is (thrown? Exception (gate/decision! {:route :synthesize :score 100} #{})))
  (is (thrown? Exception (gate/cost! {:reserved {:usd 0.1} :provider-requests {}})))
  ;; This is a fixed structural checker, including a non-GPU counterexample.
  (is (discovery/applicable? {:jobs [{:resources {:cpu 1 :mem 1}}]}))
  (is (not (discovery/applicable? {:jobs [{:resources {:cpu 1 :mem 1 :license 1}}]}))))
