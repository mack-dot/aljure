(ns repl-lab.artifact-library-test
  "Discovery from a hash-pinned library, applicability refusals, structural composition
  validated before promotion, and task-path preload accounting. No Docker: the backend
  below runs only compiled developer fixtures, found by the code hash of the forms the
  controller sends. It never evaluates source text on the host."
  (:require [clojure.test :refer :all] [clojure.string :as str] [clojure.java.io :as io]
            [repl-lab.util :as u] [repl-lab.artifact :as a] [repl-lab.skills :as skills]
            [repl-lab.executable :as executable] [repl-lab.execution :as execution]
            [repl-lab.isolation :as isolation] [repl-lab.controller :as c] [repl-lab.provider :as provider]
            [repl-lab.runtime :as runtime] [repl-lab.external-task :as external]
            [repl-lab.fixtures :refer [fixture-function]]
            [repl-lab.runtime-test :refer [temp-root config]]))

;; Developer fixtures: compiled here, and identified by the code hash of their quoted forms.
(fixture-function parse-labels
  (fn [text] (mapv (fn [line] (second (clojure.string/split line (re-pattern " :: ")))) (clojure.string/split-lines text))))
(fixture-function tally (fn [labels] (frequencies labels)))
(fixture-function most-common (fn [counts] (key (first (sort-by (fn [e] [(- (val e)) (key e)]) counts)))))
(fixture-function least-common (fn [counts] (key (first (sort-by (fn [e] [(val e) (key e)]) counts)))))
(fixture-function top-label (fn [x0] (most-common (tally (parse-labels x0)))))
(fixture-function bottom-label (fn [x0] (least-common (tally (parse-labels x0)))))
(fixture-function coarse-taxonomy
  (fn [input] (every? (fn [line] (boolean (re-find (re-pattern " :: (ABBR|DESC|ENTY|HUM|LOC|NUM)$") line)))
                      (clojure.string/split-lines (:context input)))))
(fixture-function always (fn [input] true))
(fixture-function broken (fn [input] (throw (ex-info "predicate failed" {}))))
(fixture-function sized (fn [input] (count (:context input))))
(fixture-function shadow (fn [labels] (count labels)))

(def trusted
  (into {} (map (fn [[form f]] [(a/forms-code-hash form) f])
                [[parse-labels-form parse-labels] [tally-form tally] [most-common-form most-common]
                 [least-common-form least-common] [top-label-form top-label] [bottom-label-form bottom-label]
                 [coarse-taxonomy-form coarse-taxonomy] [always-form always] [broken-form broken]
                 [sized-form sized] [shadow-form shadow]])))

(defn- fixture! [root form name arity]
  (let [artifact (a/make-artifact {:category :analysis :source (pr-str form) :interface {:name name :arity arity}
                                   :dependencies [] :author "developer-fixture" :parent nil :provenance :developer-fixture})]
    (a/save! root artifact) artifact))

(defn- run-trusted [form]
  (or (get trusted (a/forms-code-hash form)) (throw (ex-info "Worker rejected expression: untrusted fixture code" {}))))

(defn- fake-eval
  "Recognizes only the controller's own templates (executable/*, runtime done source and
  pages) and the test's scripted model forms."
  [script worker source bindings]
  (let [form (u/read-edn source) head (when (seq? form) (first form))
        binding-name (when (and (= 'let head) (vector? (second form))) (first (second form)))]
    (cond
      (= source executable/drain-source) (let [v (:invocations @worker)] (swap! worker assoc :invocations {}) v)
      (and (= 'do head) (= '(def aljure-invocations (atom {})) (second form))) (do (swap! worker assoc :invocations {}) nil)
      (and (= 'do head) (seq? (second form)) (= 'def (first (second form))))
      (let [[_ [_ name value]] form
            wrapped? (and (seq? value) (= 'let (first value)) (= 'aljure-f (first (second value))))
            code (if wrapped? (second (second value)) value) f (run-trusted code) h (a/forms-code-hash code)]
        (swap! worker assoc-in [:defs (str name)]
               (if wrapped?
                 (fn [& args]
                   (swap! worker update-in [:invocations h] #(update (or % {:calls 0 :returns 0 :values []}) :calls inc))
                   (let [v (apply f args)]
                     (swap! worker update-in [:invocations h]
                            #(cond-> (update % :returns inc) (and (string? v) (not-any? #{v} (:values %))) (update :values conj v)))
                     v))
                 f))
        nil)
      (= 'apply head) (apply (get-in @worker [:defs (str (second form))]) (:arguments bindings))
      (= 'aljure-p binding-name)
      (let [v ((run-trusted (second (second form))) (assoc (:aljure-public-input bindings) :context (:context @worker)))]
        (if (boolean? v) v :aljure/not-boolean))
      (= 'aljure-v binding-name)
      (let [v ((get script (second (second form))) worker)]
        (swap! worker assoc :answer v) (if (string? v) [(count v) (hash v)] :aljure/not-a-string))
      (= 'e binding-name)
      (let [[_ [_ [_ n end]] [_ [_ _ start _]]] form e (min n end)] [e (subs (:answer @worker) start e)])
      :else ((or (get script form) (throw (ex-info "Worker rejected expression: unknown fixture source" {}))) worker))))

(defrecord TrustedFixtureBackend [script log]
  execution/ExecutionBackend
  (open! [_ _] (swap! log conj :open) (atom {:defs {} :invocations {}}))
  (evaluate! [_ worker source bindings] (swap! log conj source) (fake-eval script worker source bindings))
  (close! [_ _] (swap! log conj :close)))

(def coarse-context "q1 :: HUM\nq2 :: LOC\nq3 :: HUM")
(def other-context "r1 :: positive\nr2 :: negative")

(defn- library!
  "parse-labels, tally and most-common, approved under the coarse-taxonomy predicate."
  [root]
  (let [predicate (fixture! root coarse-taxonomy-form "applicable" 1)
        functions (mapv #(apply fixture! root %) [[parse-labels-form "parse-labels" 1] [tally-form "tally" 1]
                                                  [most-common-form "most-common" 1]])
        entry (fn [f status] {:artifact (:hash f) :code-hash (a/code-hash f) :applicability (:hash predicate)
                              :applicability-code-hash (a/code-hash predicate) :status status})]
    {:predicate predicate :functions functions
     :sha (skills/write-library! root {:schema :aljure-library-v1 :parent nil
                                       :entries (mapv #(entry % :approved) functions)})
     :entry entry}))

(deftest a-pinned-library-survives-a-fresh-process-with-its-statuses
  (let [root (temp-root) {:keys [functions sha entry]} (library! root)
        [parse tally* most] functions
        quarantined (skills/set-status! root sha (:hash tally*) :quarantined)
        mixed (skills/set-status! root quarantined (:hash most) :unknown)
        here (skills/load-library root mixed)
        program (str "(require 'repl-lab.skills 'repl-lab.artifact) "
                     "(let [l (repl-lab.skills/load-library " (pr-str root) " " (pr-str mixed) ")] "
                     "(prn {:entries (mapv (fn [e] [(:artifact e) (:code-hash e) (:status e) "
                     "(repl-lab.artifact/code-hash (repl-lab.artifact/load! " (pr-str root) " (:artifact e)))]) (:entries l)) "
                     ":offered (mapv :artifact (:approved (repl-lab.skills/discover " (pr-str root) " " (pr-str mixed) ")))})) "
                     "(shutdown-agents)")
        process (.start (ProcessBuilder. ^java.util.List ["python3" "scripts/clj.py" "-e" program]))
        output (future (slurp (.getInputStream process)))]
    (is (.waitFor process 180 java.util.concurrent.TimeUnit/SECONDS))
    (let [fresh (u/read-edn (last (str/split-lines @output)))]
      ;; A new JVM reads the same bytes and re-derives byte-identical code hashes.
      (is (= (mapv (fn [e] [(:artifact e) (:code-hash e) (:status e) (:code-hash e)]) (:entries here)) (:entries fresh)))
      (is (= [:approved :quarantined :unknown] (map #(nth % 2) (:entries fresh))))
      ;; Quarantined and unknown entries are never offered.
      (is (= [(:hash parse)] (:offered fresh))))
    ;; Versions are immutable: the earlier pins still load unchanged.
    (is (= (repeat 3 :approved) (map :status (:entries (skills/load-library root sha)))))
    (is (= sha (:parent (skills/load-library root quarantined))))
    (is (= {:approved 1 :quarantined 1 :unknown 1} (:statuses (skills/discover root mixed))))
    ;; Fail closed: wrong pin, changed bytes, or an entry whose code hash does not match.
    (is (thrown-with-msg? Exception #"missing" (skills/load-library root (apply str (repeat 64 "0")))))
    (let [f (io/file root "libraries" (str mixed ".edn"))]
      (spit f (str/replace (slurp f) ":unknown" ":approved"))
      (is (thrown-with-msg? Exception #"hash mismatch" (skills/load-library root mixed))))
    (is (thrown-with-msg? Exception #"code hash differs"
          (skills/write-library! root {:schema :aljure-library-v1 :parent nil
                                       :entries [(assoc (entry parse :approved) :code-hash (a/code-hash tally*))]})))))

(defn- task-run! [root contract]
  (let [store (str root "/controller.sqlite") run "external-task"]
    (c/create-run! store run (cond-> config contract (assoc :contract contract)) nil)
    (c/session! store run "root" nil)
    [store run]))

(defn- events [store run type] (map :payload (filter #(= type (:type %)) (:events (c/get-run store run)))))

(deftest incompatible-artifacts-are-refused-and-the-refusals-recorded
  (let [root (temp-root) {:keys [predicate functions sha entry]} (library! root)
        broken-predicate (fixture! root broken-form "applicable" 1)
        sized-predicate (fixture! root sized-form "applicable" 1)
        always-predicate (fixture! root always-form "applicable" 1)
        shadowing (fixture! root shadow-form "count" 1)
        extra (skills/update-library! root sha
                (fn [entries]
                  (into (vec entries)
                        (for [[f p] [[shadowing always-predicate]
                                     [(fixture! root '(fn [x] (str x)) "label-a" 1) broken-predicate]
                                     [(fixture! root '(fn [x] (str x x)) "label-b" 1) sized-predicate]]]
                          {:artifact (:hash f) :code-hash (a/code-hash f) :applicability (:hash p)
                           :applicability-code-hash (a/code-hash p) :status :approved}))))
        prepare (fn [context]
                  (let [[store run] (task-run! (temp-root) nil) log (atom []) prewarmed (atom {})
                        backend (->TrustedFixtureBackend {} log)
                        prepared (with-redefs [execution/for-run (fn [_] backend)]
                                   (external/prepare-artifacts! {:store store :run run :spec {:library root :library_sha256 extra}
                                                                 :initialize (fn [_ worker] (swap! worker assoc :context context))
                                                                 :question "Which label is most common?" :prewarmed prewarmed}))]
                    {:store store :run run :prepared prepared :log @log :prewarmed @prewarmed}))
        other (prepare other-context)
        decisions (events (:store other) (:run other) :artifact-applicability)]
    ;; Another taxonomy: the parser, tally and ranker are refused as inapplicable.
    (is (= [:inapplicable :inapplicable :inapplicable :reserved-name :predicate-error :not-boolean] (mapv :reason decisions)))
    (is (every? #(= :refuse (:decision %)) decisions))
    (is (= (mapv :hash (concat functions [shadowing])) (take 4 (map :artifact decisions))))
    (is (every? #(re-matches #"[a-f0-9]{64}" (:code-hash %)) decisions))
    (is (str/includes? (:error (nth decisions 4)) "predicate failed"))
    ;; Nothing refused enters the worker or the task message; the worker still goes to the root.
    (is (empty? (events (:store other) (:run other) :artifact-preloaded)))
    (is (nil? (:note (:prepared other))))
    (is (nil? (:env (:prepared other))))
    (is (= (external/task-input {:question "q"} nil) {:task {:question "q"} :context-handle "context" :repl-binding "external-context"}))
    (is (contains? (:prewarmed other) "root"))
    (is (not-any? #(and (string? %) (str/includes? % "aljure-f")) (:log other)))
    ;; The same library on the matching taxonomy preloads the three approved functions only.
    (let [same (prepare coarse-context)
          decisions (events (:store same) (:run same) :artifact-applicability)]
      (is (= [:preload :preload :preload :refuse :refuse :refuse] (mapv :decision decisions)))
      (is (= ["parse-labels" "tally" "most-common"] (map :name (:functions (:note (:prepared same))))))
      (is (= 1 (count (events (:store same) (:run same) :artifact-preloaded))))
      ;; No provider call was made or charged for discovery, checks or preload.
      (is (= 0 (get-in (c/get-run (:store same) (:run same)) [:spent :calls])))
      (is (empty? (events (:store same) (:run same) :provider-reserved))))
    ;; A pin that does not verify stops the task before any worker opens.
    (is (thrown-with-msg? Exception #"missing"
          (external/prepare-artifacts! {:store nil :run nil :spec {:library root :library_sha256 (apply str (repeat 64 "a"))}})))))

(deftest structural-composition-is-validated-before-promotion
  (let [root (temp-root) {:keys [predicate functions sha]} (library! root)
        [parse tally* most] functions
        least (fixture! root least-common-form "least-common" 1)
        composed (a/compose "top-label" [parse tally* most] {:author "controller" :provenance :developer-fixture})
        backend (->TrustedFixtureBackend {} (atom []))
        cases [{:case "c1" :arguments [coarse-context] :expected "HUM"}
               {:case "c2" :arguments ["q1 :: LOC\nq2 :: LOC\nq3 :: NUM"] :expected "LOC"}]
        rule {:objective :verified-cases :min-score-improvement (count cases)}
        absent (mapv #(hash-map :case (:case %) :passed false) cases)
        validate (fn [artifact] (executable/validate! backend artifact (a/dependency-closure root artifact) cases nil))]
    ;; Built from code data: the forms are the composition, pinned to the exact stage hashes.
    (is (= '(fn [x0] (most-common (tally (parse-labels x0)))) (:forms composed)))
    (is (= (pr-str (:forms composed)) (:source composed)))
    (is (= (mapv :hash [parse tally* most]) (:dependencies composed)))
    (is (= (a/forms-code-hash top-label-form) (a/code-hash composed)))
    (a/save! root composed)
    ;; Validation runs the candidate in the worker; gold stays here, the rows keep pass/fail only.
    (let [rows (validate composed) evidence (a/promotion-evidence absent rows rule)
          promoted (skills/add-entry! root sha {:artifact composed :applicability predicate :summary "Most common label"} evidence)
          entry (last (:entries (skills/load-library root promoted)))]
      (is (= [{:case "c1" :passed true} {:case "c2" :passed true}] rows))
      (is (:approved evidence))
      (is (= :approved (:status entry)))
      (is (not (str/includes? (pr-str entry) "HUM")))
      (is (some #(= (:hash composed) (:artifact %)) (:approved (skills/discover root promoted))))
      ;; A structural patch of one subtree, with the stale-target check, then the same gate.
      (is (thrown-with-msg? Exception #"changed target"
            (a/patch composed {:base-hash (:hash composed) :path [2 0] :expected-hash (u/hash-value 'tally)
                               :replacement 'least-common :author "controller"})))
      (let [patched (a/make-artifact (assoc (a/patch composed {:base-hash (:hash composed) :path [2 0]
                                                               :expected-hash (u/hash-value 'most-common)
                                                               :replacement 'least-common :author "controller"
                                                               :dependencies (mapv :hash [parse tally* least])})
                                            :interface {:name "bottom-label" :arity 1}))
            _ (a/save! root patched)
            rows (validate patched) evidence (a/promotion-evidence absent rows rule)
            demoted (skills/add-entry! root promoted {:artifact patched :applicability predicate} evidence)]
        (is (= '(fn [x0] (least-common (tally (parse-labels x0)))) (:forms patched)))
        (is (= (:hash composed) (:parent patched)))
        (is (= [false false] (mapv :passed rows)))
        (is (not (:approved evidence)))
        (is (= :rejected (:status (last (:entries (skills/load-library root demoted))))))
        (is (not-any? #(= (:hash patched) (:artifact %)) (:approved (skills/discover root demoted))))))))

(defn- provider-for [commands] (provider/->FixtureProvider (atom {"root" commands})))

(defn- run-task!
  "The external task path (prepare-artifacts!, run-session!, reuse summary) with fixtures."
  [root sha contract commands]
  (let [[store run] (task-run! (temp-root) contract) log (atom []) prewarmed (atom {})
        script {'(top-label external-context) (fn [w] ((get-in @w [:defs "top-label"]) (:context @w)))
                '(str (top-label external-context)) (fn [w] (str ((get-in @w [:defs "top-label"]) (:context @w))))}
        backend (->TrustedFixtureBackend script log)
        initialize (fn [_ worker] (swap! worker assoc :context coarse-context))
        result (with-redefs [execution/for-run (fn [_] backend) isolation/close-session! (fn [_] nil)]
                 (let [prepared (when sha (external/prepare-artifacts! {:store store :run run :spec {:library root :library_sha256 sha}
                                                                        :initialize initialize :question "Most common?" :prewarmed prewarmed}))]
                   (runtime/run-session! (merge {:store store :run run :workers (atom {}) :prewarmed prewarmed
                                                 :provider (provider-for commands) :initialize-worker initialize}
                                                (:env prepared))
                                         "root" (external/task-input {:question "Most common?"} (:note prepared)))))]
    (when sha (c/update-run! store run #(c/event % :artifact-reuse-summary (skills/reuse-summary (:events %) result))))
    {:store store :run run :result result :log @log :ledger (c/get-run store run)}))

(deftest preload-invocations-are-recorded-and-budgets-unchanged
  (let [root (temp-root) {:keys [predicate functions sha]} (library! root)
        composed (a/compose "top-label" functions {:author "controller" :provenance :developer-fixture})
        _ (a/save! root composed)
        sha (skills/add-entry! root sha {:artifact composed :applicability predicate :summary "Most common label"}
                               {:approved true :old [] :new [] :rule {}})
        reuse (run-task! root sha nil [{:op :repl/eval :source "(top-label external-context)" :bindings {}}
                                       {:op :done/eval :source "(str (top-label external-context))"}])
        {:keys [store run result ledger]} reuse
        batches (events store run :artifact-invocations)
        summary (first (events store run :artifact-reuse-summary))]
    (is (= {:summary "HUM"} result))
    ;; Each model evaluation that called a preloaded function is recorded under its code hash.
    (is (= [:repl/eval :done/eval] (mapv :op batches)))
    (is (= (a/code-hash composed) (:code-hash (first (filter #(= "top-label" (:name %)) (:invocations (first batches)))))))
    ;; The compiled fixture calls its stages directly; in SCI they resolve through their own
    ;; wrappers too (sci-contract artifacts proof). Here only the export is counted.
    (is (= [{:name "top-label" :calls 1 :returns 1 :values ["HUM"]}]
           (mapv #(select-keys % [:name :calls :returns :values]) (:invocations (second batches)))))
    (is (= :eligible-reuse (:classification summary)))
    (is (= :computed-in-answer (get-in summary [:in-answer (a/code-hash composed)])))
    (is (= :done-eval (:answer-mode summary)))
    ;; Accounting: only the two model turns are charged; limits are the configured ones.
    (is (= 2 (get-in ledger [:spent :calls])))
    (is (= 2 (count (events store run :provider-reserved))))
    (is (= (:limits config) (get-in ledger [:config :limits])))
    (is (= 1 (count (events store run :artifact-preloaded))))
    (is (some #(= "top-label" (:name %)) (:functions (first (events store run :artifact-preloaded))))))
  ;; A direct text answer needs no code; the answer-format validator still acts first.
  (let [root (temp-root) {:keys [sha]} (library! root)
        direct (run-task! root sha {:answer-format {:max-lines 1 :max-chars 64}}
                          [{:op :done :summary "HUM\nbecause most lines say HUM"} {:op :done :summary "HUM"}])
        summary (first (events (:store direct) (:run direct) :artifact-reuse-summary))]
    (is (= {:summary "HUM"} (:result direct)))
    (is (= 1 (count (events (:store direct) (:run direct) :answer-format-notice))))
    (is (= :direct-answer (:classification summary)))
    (is (zero? (:model-evaluations summary)))
    (is (empty? (events (:store direct) (:run direct) :artifact-invocations))))
  ;; Off: no discovery, no drain, and the session sees only its own expressions.
  (let [off (run-task! nil nil nil [{:op :done :summary "HUM"}])]
    (is (= {:summary "HUM"} (:result off)))
    (is (not-any? #(str/starts-with? (name (:type %)) "artifact-") (:events (:ledger off))))
    (is (not-any? #{executable/drain-source} (:log off)))))

(deftest preload-sources-are-worker-readable-and-use-no-denied-symbol
  (let [denied (set (map str (u/read-edn (second (re-find #"(?s)\(def denied '(\[.*?\])\)" (slurp "worker/src/repl_lab/worker.clj"))))))
        functions [{:name "top-label" :code-hash (apply str (repeat 64 "a")) :source (pr-str top-label-form)}]
        sources (conj (executable/preload-sources functions) executable/drain-source
                      ;; the applicability template, through the worker's own reader
                      (str "(let [aljure-p " (pr-str always-form) " aljure-v (aljure-p (assoc aljure-public-input :context external-context))] "
                           "(if (boolean? aljure-v) aljure-v :aljure/not-boolean))"))]
    (is (seq denied))
    (doseq [source sources]
      (let [form (u/read-edn source) symbols (set (map str (filter symbol? (tree-seq coll? seq form))))]
        (is (empty? (filter denied symbols)) source)
        (is (< (count (.getBytes ^String source "UTF-8")) 65000))))
    (is (contains? (executable/reserved-names) "show-items"))
    (is (contains? (executable/reserved-names) "count"))))
