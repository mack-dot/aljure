(ns repl-lab.sci-contract
  "Checks every advertised SCI behaviour (resources/sci-contract.json) through
  the controller's own source, result and error paths against the real isolated
  worker. Writes a proof the paired preflight requires for the assisted surface."
  (:require [clojure.string :as str] [repl-lab.util :as u] [repl-lab.isolation :as isolation]
            [repl-lab.execution :as execution] [repl-lab.model-protocol :as wire]
            [repl-lab.external-task :as external] [repl-lab.controller :as c] [repl-lab.runtime :as runtime]
            [repl-lab.artifact :as a] [repl-lab.executable :as executable]
            [repl-lab.acquisition :as acquisition] [repl-lab.skills :as skills]))

(defn proof-path []
  (let [bound (isolation/output-bound)]
    (if (= 65536 bound) "var/sci-contract-proof.json" (str "var/sci-contract-proof-" bound ".json"))))

(defn digests []
  {:contract-sha256 (u/sha (slurp "resources/sci-contract.json"))
   :prelude-sha256 (u/sha (slurp "resources/sci-prelude.edn"))
   :verify-sha256 (u/sha (slurp "resources/sci-verify.edn"))
   :model-protocol-sha256 (u/sha (slurp "src/repl_lab/model_protocol.clj"))})

(defn display
  "What the model would see for this result, through the runtime's own path."
  [config result]
  (let [response {:content [{:type "tool_use" :id "contract" :name "repl_eval" :input {}}]}
        block (first (:content (second (wire/result-messages config response result))))]
    {:text (:content block) :error (boolean (:is_error block))}))

(defn run-probe [config backend worker {:keys [source]}]
  (display config
           (try {:value (execution/evaluate! backend worker (wire/assisted-source config :repl/eval source) {})}
                (catch Exception e {:error (.getMessage e)}))))

(defn passes? [{:keys [text error] :as expected} shown]
  (and (= (boolean error) (:error shown))
       (or (nil? text) (= text (:text shown)))
       (or (nil? (:text-prefix expected)) (str/starts-with? (:text shown) (:text-prefix expected)))
       (or (nil? (:text-contains expected)) (str/includes? (:text shown) (:text-contains expected)))))

(defn check-mode [contract mode]
  (let [config {:response-envelope wire/tool-envelope-version :sci-surface :assisted :sci-results (keyword mode)}
        backend (execution/backend :clojure)
        worker (execution/open! backend (+ (System/currentTimeMillis) 110000))]
    (try
      (external/initialize-context! (:context contract) true backend worker)
      (vec (for [probe (:probes contract) :when (some #{mode} (or (:modes probe) ["raw" "bounded"]))]
             (let [shown (run-probe config backend worker probe)]
               {:mode mode :source (:source probe) :passed (passes? probe shown) :shown (subs (:text shown) 0 (min 300 (count (:text shown))))})))
      (finally (execution/close! backend worker)))))

(def verification-probes
  [{:source "(show-items [\"a\" \"bb\" \"ccc\"] 0 5)" :text "0. a\n[items 0-0 of 3 shown whole; next start 1]"}
   {:source "(show-items [\"a\" \"bb\"] 0)" :text "0. a\n1. bb\n[items 0-1 of 2 shown whole; all shown]"}
   {:source "(select-keys (audit-labels (range 5) {0 :c 1 :n 2 :unknown 3 :c}) [:missing :unresolved :counts :count-range :open :complete])"
    :text "{:missing [4], :unresolved [2], :counts {:c 2, :n 1}, :count-range {:c [2 4], :n [1 3]}, :open 2, :complete false}"}
   {:source "(select-keys (audit-labels [0 1] [[0 :c] [0 :n] [1 :c] [7 :n]]) [:conflicts :unexpected :count-range :repeated-count :open])"
    :text "{:conflicts {0 [:c :n]}, :unexpected [7], :count-range {:c [1 2], :n [0 1]}, :repeated-count 1, :open 1}"}
   {:source "(select-keys @aljure-audit [:open])" :text "{:open 1}"}
   ;; Items 0 and 1 were shown by earlier probes in this worker; only item 2 never was.
   {:source "(do (show-items [\"a\" \"b\" \"c\"] 0 4) (:never-shown-count (audit-labels (range 3) {0 :x 1 :x 2 :x})))" :text "1"}])

(defn check-verification
  "The switchable verification helpers (resources/sci-verify.edn) in the real worker:
  absent unless the plan enables them, and exact coverage and count-range arithmetic when it does."
  [contract]
  (let [config {:response-envelope wire/tool-envelope-version :sci-surface :assisted :sci-results :bounded}
        backend (execution/backend :clojure)
        check (fn [verify probes]
                (let [worker (execution/open! backend (+ (System/currentTimeMillis) 110000))]
                  (try
                    (external/initialize-context! (:context contract) true verify backend worker)
                    (vec (for [probe probes]
                           (let [shown (run-probe config backend worker probe)]
                             {:mode (if verify "verification" "verification-absent") :source (:source probe)
                              :passed (passes? probe shown) :shown (subs (:text shown) 0 (min 300 (count (:text shown))))})))
                    (finally (execution/close! backend worker)))))]
    (into (check false [{:source "(audit-labels [0] {0 :c})" :error true :text-contains "audit-labels"}])
          (check true verification-probes))))

(defn check-recovery
  "Raw results: an output over the bound stops the worker. Through the real broker
  and ledger, the next call must get a fresh worker, and the record must keep both calls."
  [contract]
  (let [root (str (System/getProperty "java.io.tmpdir") "/sci-contract-" (System/nanoTime))
        store (str root "/controller.sqlite") run "contract"
        config (merge (u/read-file "config/experiment.edn")
                      {:response-envelope wire/tool-envelope-version :sci-surface :assisted :sci-results :raw})
        workers (atom {})
        env {:store store :run run :workers workers :registry root :allow-learning false
             :initialize-worker (partial external/initialize-context! (:context contract) true)}
        big (str "(apply str (repeat " (+ 100 (isolation/output-bound)) " \"x\"))")
        call (fn [source] (try {:value (runtime/broker! env "root" {:op :repl/eval :source source :bindings {}})}
                               (catch Exception e {:error (.getMessage e)})))]
    (c/create-run! store run config nil) (c/session! store run "root" nil)
    (try
      (let [before (call "(def kept 7)")
            oversized (call big)
            after (call "(count context-lines)")
            lost (call "kept")
            events (filter #(#{:tool-call :tool-result} (:type %)) (:events (c/get-run store run)))]
        [{:mode "raw-recovery" :source big
          :passed (and (:value before) (re-find #"The worker stopped" (str (:error oversized)))
                       (= {:value 3} (:value after)) (re-find #"Could not resolve symbol: kept" (str (:error lost)))
                       (= 2 (count @workers)) (= 8 (count events)))
          :shown (u/json-str {:oversized (:error oversized) :after (:value after) :lost (:error lost)
                              :workers (count @workers) :recorded-events (count events)})}])
      (finally (doseq [[_ w] @workers] (execution/close! (execution/backend :clojure) w))))))

(defn check-answer-delivery
  "done with source: an answer larger than one worker reply arrives whole, in
  pages below the bound, through the real broker; the worker is not replaced."
  [contract]
  (let [root (str (System/getProperty "java.io.tmpdir") "/sci-answer-" (System/nanoTime))
        store (str root "/controller.sqlite") run "answer"
        workers (atom {}) size (* 3 (isolation/output-bound))
        env {:store store :run run :workers workers :registry root :allow-learning false
             :initialize-worker (partial external/initialize-context! (:context contract) true)}]
    (c/create-run! store run (merge (u/read-file "config/experiment.edn")
                                    {:response-envelope wire/tool-envelope-version :sci-surface :assisted :sci-results :bounded}) nil)
    (c/session! store run "root" nil)
    (try
      ;; ASCII, then "a" plus an emoji (3 UTF-16 chars) so page ends fall inside surrogate pairs.
      (vec (for [[text label] [["y" "ascii"] ["a\uD83D\uDE00" "surrogate-pairs"]]]
             (let [expected (apply str (repeat (quot size (count text)) text))
                   result (try (runtime/broker! env "root" {:op :done/eval :source (str "(apply str (repeat " (quot size (count text)) " " (pr-str text) "))")})
                               (catch Exception e {:error (.getMessage e)}))
                   summary (:summary result)]
               {:mode (str "answer-delivery-" label) :source (str (count expected) " characters")
                :passed (and (string? summary) (= (u/sha expected) (u/sha summary)) (= 1 (count @workers)))
                :shown (u/json-str {:chars (count summary) :error (:error result) :workers (count @workers)})})))
      (finally (doseq [[_ w] @workers] (execution/close! (execution/backend :clojure) w))))))

(defn artifact-proof-path []
  (let [bound (isolation/output-bound)]
    (if (= 65536 bound) "var/artifact-path-proof.json" (str "var/artifact-path-proof-" bound ".json"))))

(defn artifact-digests
  "The sources whose SCI behaviour the artifact-path proof attests (aljure_contract.artifacts)."
  []
  (into (sorted-map) (for [[k path] {:executable-sha256 "src/repl_lab/executable.clj" :external-task-sha256 "src/repl_lab/external_task.clj"
                                     :skills-sha256 "src/repl_lab/skills.clj" :runtime-sha256 "src/repl_lab/runtime.clj"
                                     :skill-interface-sha256 "src/repl_lab/skill_interface.clj"}]
                       [k (u/sha (slurp path))])))

(defn check-artifacts
  "aljure_contract.artifacts in the real worker: a predicate accepts and refuses on public
  input; preloaded functions run under their names; a call through a composition is counted
  once under each code hash, dependencies included; a drain clears the log; validation of
  the composition passes in a fresh worker. Developer fixtures only; no model call."
  []
  (let [root (str (System/getProperty "java.io.tmpdir") "/artifact-proof-" (System/nanoTime))
        make (fn [source name] (let [x (a/make-artifact {:category :analysis :source source :interface {:name name :arity 1}
                                                          :dependencies [] :author "developer-fixture" :parent nil
                                                          :provenance :developer-fixture})]
                                 (a/save! root x) x))
        parse (make "(fn [text] (mapv (fn [line] (second (clojure.string/split line (re-pattern \" :: \")))) (clojure.string/split-lines text)))" "parse-labels")
        tally (make "(fn [labels] (frequencies labels))" "tally")
        most (make "(fn [counts] (key (first (sort-by (fn [e] [(- (val e)) (key e)]) counts))))" "most-common")
        top (doto (a/compose "top-label" [parse tally most] {:author "developer-fixture" :provenance :developer-fixture}) (->> (a/save! root)))
        accept (make "(fn [input] (clojure.string/includes? (:context input) \" :: HUM\"))" "applicable")
        refuse (make "(fn [input] (clojure.string/includes? (:context input) \"positive\"))" "applicable")
        context "q1 :: HUM\nq2 :: LOC\nq3 :: HUM"
        deadline (+ (System/currentTimeMillis) 110000)
        backend (execution/backend :clojure)
        worker (execution/open! backend deadline)
        row (fn [label passed shown] {:mode "artifacts" :source label :passed (boolean passed) :shown (u/json-str shown)})]
    (try
      (external/initialize-context! context false backend worker)
      (let [yes (executable/applicability! backend worker accept {:question "Most common label?"})
            no (executable/applicability! backend worker refuse {:question "Most common label?"})
            dependencies (a/dependency-closure root top)
            {:keys [functions]} (executable/preload-plan [{:artifact (:hash top) :code-hash (a/code-hash top) :function top
                                                           :dependencies dependencies :check yes}])
            _ (executable/install! backend worker functions)
            value (execution/evaluate! backend worker "(top-label external-context)" {})
            known (set (map :code-hash functions))
            drained (executable/drain! backend worker known)
            again (executable/drain! backend worker known)
            counts (into {} (map (juxt :code-hash :calls) (:invocations drained)))
            rows (executable/validate! backend top dependencies
                                       [{:case "c1" :arguments [context] :expected "HUM"}
                                        {:case "c2" :arguments ["a :: LOC\nb :: LOC"] :expected "LOC"}] deadline)]
        [(row "predicate-accepts" (= :preload (:decision yes)) yes)
         (row "predicate-refuses" (= :inapplicable (:reason no)) no)
         (row "preloaded-call" (= "HUM" value) value)
         (row "invocations-by-code-hash" (= (zipmap (map a/code-hash [parse tally most top]) (repeat 1)) counts) drained)
         (row "drain-clears" (= [] (:invocations again)) again)
         (row "validation" (= [true true] (mapv :passed rows)) rows)])
      (catch Exception e [(row "artifact-path" false {:error (.getMessage e)})])
      (finally (execution/close! backend worker)))))

(defn- artifacts-main []
  (try
    (let [check (isolation/require-tested!)
          results (check-artifacts)
          passed (every? :passed results)
          proof (merge (artifact-digests) {:status (if passed "TESTED" "FAILED") :image (:image check)
                                           :output-bytes (isolation/output-bound) :results results})]
      (when passed (u/write-json! (artifact-proof-path) proof))
      (println (u/json-str (dissoc proof :results)))
      (doseq [r results :when (not (:passed r))] (println "FAILED" (u/json-str r)))
      (shutdown-agents)
      (System/exit (if passed 0 1)))
    (catch Exception e
      (println "Artifact path check failed:" (.getMessage e))
      (shutdown-agents)
      (System/exit 2))))

(defn- contract-main []
  (try
    (let [check (isolation/require-tested!)
          contract (wire/sci-contract)
          results (-> (check-mode contract "raw") (into (check-mode contract "bounded")) (into (check-recovery contract)) (into (check-answer-delivery contract)) (into (check-verification contract)))
          passed (every? :passed results)
          proof (merge (digests) {:status (if passed "TESTED" "FAILED") :image (:image check)
                                  :output-bytes (isolation/output-bound) :results results})]
      (when passed (u/write-json! (proof-path) proof))
      (println (u/json-str (dissoc proof :results)))
      (doseq [r results :when (not (:passed r))] (println "FAILED" (u/json-str r)))
      (shutdown-agents)
      (System/exit (if passed 0 1)))
    (catch Exception e
      (println "SCI contract check failed:" (.getMessage e))
      (shutdown-agents)
      (System/exit 2))))

;; aljure_contract.acquisition (thesis pilot): the proposal memo readout, the arm-C memo
;; install and lookup, and panel validation, each in the real isolated worker.
(defn acquisition-proof-path []
  (let [bound (isolation/output-bound)]
    (if (= 65536 bound) "var/acquisition-proof.json" (str "var/acquisition-proof-" bound ".json"))))

(defn acquisition-digests []
  (into (sorted-map) (for [[k path] {:acquisition-sha256 "src/repl_lab/acquisition.clj" :executable-sha256 "src/repl_lab/executable.clj"
                                     :external-task-sha256 "src/repl_lab/external_task.clj" :skills-sha256 "src/repl_lab/skills.clj"
                                     :runtime-sha256 "src/repl_lab/runtime.clj"}]
                       [k (u/sha (slurp path))])))

(defn check-acquisition
  "Developer fixtures only; no model call. A panel run admits a classifier on its own
  taxonomy and refuses it on another; labels come back in pages; a memo is read out of a
  session worker in pages; exact-label answers only exact (trimmed) matches and is counted
  under its code hash."
  []
  (let [root (str (System/getProperty "java.io.tmpdir") "/acquisition-proof-" (System/nanoTime))
        make (fn [source name] (let [x (a/make-artifact {:category :analysis :source source :interface {:name name :arity 1}
                                                          :dependencies [] :author "developer-fixture" :parent nil
                                                          :provenance :developer-fixture})]
                                 (a/save! root x) x))
        rules (make "(fn [text] (cond (re-find (re-pattern \"^Where \") text) \"location\" (re-find (re-pattern \"^Who \") text) \"human being\" :else nil))" "trec-rules")
        accept (make "(fn [input] (clojure.string/includes? (:context input) \"'abbreviation'\"))" "applicable")
        trec-items (vec (for [i (range 600)] {:case (str "t" i) :text (str (["Where is " "Who wrote " "How many "] (mod i 3)) "item " i " ?")
                                              :label (["location" "human being" "numeric value"] (mod i 3))}))
        line (fn [{:keys [text]}] (str "Date: Jan 01, 2023 || User: 1 || Instance: " text))
        trec-context (str "Categories: 'numeric value', 'human being', 'location', 'abbreviation'.\n" (str/join "\n" (map line trec-items)))
        spam-items [{:case "s0" :text "WIN a free prize now" :label "spam"} {:case "s1" :text "see you at noon" :label "ham"}]
        spam-context (str "Each text message can be classified as spam or ham.\n" (str/join "\n" (map line spam-items)))
        panel {:windows [{:id "trec" :question "q" :context trec-context :items trec-items}
                         {:id "spam" :question "q" :context spam-context :items spam-items}]}
        deadline (+ (System/currentTimeMillis) 110000)
        backend (execution/backend :clojure)
        initialize (fn [context] (fn [backend worker] (external/initialize-context! context true false backend worker)))
        row (fn [label passed shown] {:mode "acquisition" :source label :passed (boolean passed) :shown (u/json-str shown)})]
    (try
      (let [results (acquisition/panel-run! backend initialize panel
                                            [{:key :rules :function rules :dependencies [] :predicate accept}] deadline)
            labels (get-in results [:rules "trec" :labels])
            worker (execution/open! backend deadline)]
        (try
          ((initialize trec-context) backend worker)
          (execution/evaluate! backend worker "(do (def my-labels (into {} (map (fn [l] [(str \"  \" l) \"location\"]) [\"Where is x ?\" \"Where is y ?\"]))) nil)" {})
          (let [memo (acquisition/read-memo! backend worker "my-labels")
                hits (acquisition/memo-hits {:entries (:entries memo)} "Date: x || User: 2 || Instance: Where is x ? \nDate: y || User: 3 || Instance: Who ?")
                exact (acquisition/exact-label-function)
                _ (doseq [[source bindings] (acquisition/memo-chunks hits)] (execution/evaluate! backend worker source bindings))
                _ (executable/install! backend worker [exact])
                hit (execution/evaluate! backend worker "(exact-label \" Where is x ?\")" {})
                miss (execution/evaluate! backend worker "(exact-label \"Who ?\")" {})
                drained (executable/drain! backend worker #{(:code-hash exact)})]
            [(row "panel-admits-own-taxonomy" (true? (get-in results [:rules "trec" :admitted])) (dissoc (get results :rules) "trec"))
             (row "panel-refuses-other-taxonomy" (= {:admitted false :reason :inapplicable} (get-in results [:rules "spam"])) (get-in results [:rules "spam"]))
             (row "panel-labels-in-pages" (= (mapv (fn [i] (["location" "human being" nil] (mod i 3))) (range 600)) labels) (take 6 labels))
             (row "memo-readout" (= {(acquisition/memo-key "Where is x ?") "location" (acquisition/memo-key "Where is y ?") "location"}
                                    (:entries memo)) memo)
             (row "memo-exact-hit" (= "location" hit) hit)
             (row "memo-exact-miss" (nil? miss) miss)
             (row "memo-invocations" (= [2] (mapv :calls (:invocations drained))) drained)])
          (finally (execution/close! backend worker))))
      (catch Exception e [(row "acquisition" false {:error (.getMessage e)})]))))

(defn- acquisition-main []
  (try
    (let [check (isolation/require-tested!)
          results (check-acquisition)
          passed (every? :passed results)
          proof (merge (acquisition-digests) {:status (if passed "TESTED" "FAILED") :image (:image check)
                                              :output-bytes (isolation/output-bound) :results results})]
      (when passed (u/write-json! (acquisition-proof-path) proof))
      (println (u/json-str (dissoc proof :results)))
      (doseq [r results :when (not (:passed r))] (println "FAILED" (u/json-str r)))
      (shutdown-agents)
      (System/exit (if passed 0 1)))
    (catch Exception e
      (println "Acquisition check failed:" (.getMessage e))
      (shutdown-agents)
      (System/exit 2))))

(defn -main [& args]
  (cond (= ["artifacts"] args) (artifacts-main)
        (= ["acquisition"] args) (acquisition-main)
        :else (contract-main)))
