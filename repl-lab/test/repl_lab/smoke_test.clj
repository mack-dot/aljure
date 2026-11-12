(ns repl-lab.smoke-test
  (:require [clojure.test :refer :all] [repl-lab.smoke :as smoke] [repl-lab.provider :as provider]
            [repl-lab.controller :as c] [repl-lab.isolation :as isolation]
            [repl-lab.runtime-test :refer [temp-root config]] [repl-lab.util :as u]
            [repl-lab.live :as live] [repl-lab.evaluation :as evaluation] [repl-lab.subscription :as subscription]
            [clojure.java.io :as io]))

(deftest cleanup-exit-is-distinct-from-an-execution-error
  (doseq [code [0 2 3]]
    (let [process (.start (ProcessBuilder. ^java.util.List
                             ["python3" "-c" (str "import sys; sys.stdin.read(); sys.exit(" code ")")]))
          worker {:process process :writer (io/writer (.getOutputStream process))
                  :errors (future (slurp (.getErrorStream process)))}]
      (if (= code 3)
        (is (thrown-with-msg? Exception #"cleanup unconfirmed" (isolation/close-session! worker)))
        (is (nil? (isolation/close-session! worker)))))))

(def rows [{:id "a" :ready true :estimate 7} {:id "b" :ready false :estimate 99}
           {:id "c" :ready true :estimate 11}])
(def selection {:ids ["a" "c"] :estimate-sum 18})
(def answer {:count 2 :double-estimate 36})
(def root-source "(let [ready (filter :ready records)] {:ids (vec (sort (map :id ready))) :estimate-sum (reduce + (map :estimate ready))})")
(def child-source "{:count (count (:ids selection)) :double-estimate (* 2 (:estimate-sum selection))}")

(deftest smoke-requires-evidence-instead-of-model-claims
  (let [root (temp-root) p (provider/->FixtureProvider
                           (atom {"root" [{:op :context/query :handle "jobs" :query {:limit 16}}
                                          {:op :repl/eval :source root-source :bindings {:records rows}}
                                          {:op :agent/call :id "smoke-child" :task "Synthetic smoke child" :context selection}
                                          {:op :done :summary answer}]
                                  "smoke-child" [{:op :repl/eval :source child-source :bindings {:selection selection}}
                                                 {:op :done :summary answer}]}))
        closes (atom 0)
        report (with-redefs [isolation/open-session! (fn [_] {:synthetic true})
                            isolation/evaluate! (fn [_ source bindings]
                                                  (cond
                                                    (and (= source root-source) (= (:records bindings) rows)) selection
                                                    (and (= source child-source) (= (:selection bindings) selection)) answer
                                                    :else (throw (ex-info "Unexpected fixture expression" {}))))
                            isolation/close-session! (fn [_] (swap! closes inc))]
                 (smoke/execute! {:root root :id "smoke-test" :config config :provider p
                                  :snapshot {:provenance :synthetic-fixture} :provenance :synthetic-fixture} rows))
        ledger (c/get-run (str root "/controller.sqlite") "smoke-test")]
    (is (= 2 @closes))
    (is (= 6 (get-in report [:usage :spent :calls])))
    (is (every? true? (vals (dissoc (:checks report) :root-model-call :child-model-call))))
    ;; Scripted provider calls never pass as a live smoke result.
    (is (false? (:passed report)))
    (is (= report (u/read-file (str root "/report.edn"))))
    (is (= 2 (count (u/read-file (str root "/generated-code.edn")))))
    ;; Test data for the verifier only. This is not an inference measurement.
    (let [hypothetical (update ledger :provider-requests
                               #(into {} (map (fn [[id q]] [id (assoc-in q [:response :provenance] :recorded-model-run)]) %)))]
      (is (:passed (smoke/evidence hypothetical rows)))
      (is (:passed (smoke/completed-evidence hypothetical rows {:summary answer})))
      (is (false? (:passed (smoke/completed-evidence hypothetical rows {:error "Worker cleanup failed"}))))
      (doseq [op [:context/query :repl/eval :agent/call :done]]
        (let [damaged (update hypothetical :events
                              #(vec (remove (fn [e] (and (= :tool-call (:type e)) (= op (get-in e [:payload :command :op])))) %)))]
          (is (false? (:passed (smoke/evidence damaged rows))) (str "Missing evidence for " op))))
      (let [damaged (update hypothetical :events
                            #(mapv (fn [e] (if (and (= :tool-call (:type e)) (= :agent/call (get-in e [:payload :command :op])))
                                             (assoc-in e [:payload :command :context] {:fabricated true}) e)) %))]
        (is (false? (:passed (smoke/evidence damaged rows))))))))

(deftest isolation-proof-needs-all-negative-results-and-the-same-image
  (let [check {:ready true :image "sha256:fixture-image"}
        proof {:status "TESTED" :gate-version 2 :supervisor-sha256 (u/sha (slurp "scripts/isolation.py"))
               :startup (zipmap isolation/negative-cases (repeat true))
               :image (:image check) :results (zipmap isolation/negative-cases (repeat true))
               :output-bytes 65536 :boundary {:at-bound true :over-bound true}}]
    (is (= check (isolation/validate-proof! check proof)))
    (doseq [invalid [(assoc proof :status "UNVERIFIED") (assoc proof :image "other")
                     (update proof :results dissoc :loop) (assoc-in proof [:results :network] false)
                     (dissoc proof :gate-version) (assoc proof :supervisor-sha256 "stale")
                     (assoc-in proof [:startup :process] false) (update proof :startup dissoc :loop)
                     (assoc proof :output-bytes 1048576) (dissoc proof :output-bytes) (dissoc proof :boundary)
                     (assoc-in proof [:boundary :over-bound] false) (update proof :boundary dissoc :at-bound)]]
      (is (thrown? Exception (isolation/validate-proof! check invalid))))))

(deftest all-live-entry-points-stop-before-inference-without-isolation
  (let [env {"LIVE" "1" "MODEL" "fixture-model" "MAX_USD" "1"
             "INPUT_USD_PER_M" "2" "OUTPUT_USD_PER_M" "10" "ANTHROPIC_API_KEY" "offline-not-a-credential"}
        root (temp-root) dispatched (atom 0)]
    (u/write-edn! (str root "/manifest.edn") {})
    (u/write-edn! (str root "/sealed-splits.edn") {})
    (with-redefs [isolation/doctor (fn [] {:ready false :reason "Synthetic unavailable isolation"})
                  provider/http-post! (fn [& _] (swap! dispatched inc) (throw (ex-info "Unexpected HTTP" {})))
                  subscription/transport! (fn [& _] (swap! dispatched inc) (throw (ex-info "Unexpected CLI" {})))]
      (doseq [operation [#(smoke/smoke! env) #(smoke/smoke! (assoc env "SMOKE_PROVIDER" "claude-subscription"))
                         #(live/evolve! env) #(live/resume! root env)
                         #(evaluation/evaluate-live! "missing-export" "heldout" env false)
                         #(evaluation/evaluate-live! "missing-export" "heldout" env true)]]
        (is (thrown-with-msg? Exception #"Generated-code execution disabled" (operation))))
      (is (zero? @dispatched)))
    (is (thrown-with-msg? Exception #"Paid calls are disabled" (smoke/smoke! {})))))
