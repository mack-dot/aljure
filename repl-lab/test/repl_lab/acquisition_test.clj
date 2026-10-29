(ns repl-lab.acquisition-test
  "Propose step and trajectory pins (research/THESIS_PILOT_PROTOCOL.md).

  FIXTURES, NOT AUTONOMOUS MODEL LEARNING. Every proposal below is scripted, and every
  function is a compiled developer fixture that the backend finds by the code hash of the
  forms the controller sends. These tests prove the plumbing (pins carried forward,
  validation, refusal, rollback, provenance, accounting, crash recovery). They say nothing
  about whether a model would propose useful code. No Docker, no model call, and no source
  text is evaluated on the host."
  (:require [clojure.test :refer :all] [clojure.string :as str] [clojure.java.io :as io]
            [repl-lab.util :as u] [repl-lab.artifact :as a] [repl-lab.skills :as skills]
            [repl-lab.executable :as executable] [repl-lab.execution :as execution]
            [repl-lab.isolation :as isolation] [repl-lab.controller :as c] [repl-lab.provider :as provider]
            [repl-lab.runtime :as runtime] [repl-lab.external-task :as external] [repl-lab.acquisition :as acq]
            [repl-lab.model-protocol :as wire]
            [repl-lab.fixtures :refer [fixture-function]]
            [repl-lab.runtime-test :refer [temp-root config]]))

;; ---------------------------------------------------------------------------------------
;; Developer fixtures (compiled here; identified by the code hash of their quoted forms)

(fixture-function where-who
  (fn [text] (cond (re-find (re-pattern "^Where ") text) "location" (re-find (re-pattern "^Who ") text) "human being" :else nil)))
(fixture-function where-who-many
  (fn [text] (cond (re-find (re-pattern "^Where ") text) "location" (re-find (re-pattern "^Who ") text) "human being"
                   (re-find (re-pattern "^How many ") text) "numeric value" :else nil)))
(fixture-function where-only (fn [text] (if (re-find (re-pattern "^Where ") text) "location" nil)))
(fixture-function entity-all (fn [text] "entity"))
;; The approved patch keeps its exported name trec-rules, so a composition calls it by that name.
(def trec-rules where-who-many)
(fixture-function trec-plus (fn [text] (or (trec-rules text) (if (re-find (re-pattern "stand for") text) "abbreviation" nil))))
(fixture-function spam-words (fn [text] (if (re-find (re-pattern "(?i)free|win|prize") text) "spam" nil)))
(fixture-function trec-taxonomy (fn [input] (clojure.string/includes? (:context input) "'abbreviation'")))
(fixture-function spam-taxonomy (fn [input] (clojure.string/includes? (:context input) "spam or ham")))
(fixture-function always (fn [input] true))
(fixture-function answer-six (fn [context] "Answer: 6"))

(def trusted
  (into {} (map (fn [[form f]] [(a/forms-code-hash form) f])
                [[where-who-form where-who] [where-who-many-form where-who-many] [where-only-form where-only]
                 [entity-all-form entity-all] [trec-plus-form trec-plus] [spam-words-form spam-words]
                 [trec-taxonomy-form trec-taxonomy] [spam-taxonomy-form spam-taxonomy] [always-form always]
                 [answer-six-form answer-six]])))

(defn- exact-question-form? [form]
  (and (seq? form) (= 'fn (first form)) (= '[input] (second form))
       (let [b (nth form 2 nil)] (and (seq? b) (= '= (first b)) (= '(:question input) (second b)) (string? (nth b 2 nil))))))

(defn- run-trusted [form]
  (cond (get trusted (a/forms-code-hash form)) (get trusted (a/forms-code-hash form))
        ;; The controller-generated arm-C predicate: a fixed template around one question string.
        (exact-question-form? form) (let [q (nth (nth form 2) 2)] (fn [input] (= (:question input) q)))
        :else (throw (ex-info "Worker rejected expression: untrusted fixture code" {}))))

(defn- counting [worker h f]
  (fn [& args]
    (swap! worker update-in [:invocations h] #(update (or % {:calls 0 :returns 0 :values []}) :calls inc))
    (let [v (apply f args)]
      (swap! worker update-in [:invocations h]
             #(cond-> (update % :returns inc) (and (string? v) (not-any? #{v} (:values %))) (update :values conj v)))
      v)))

(defn- memo-page [worker start]
  (let [{:keys [memo-keys memo-map]} @worker]
    (loop [i start n 0 out []]
      (if (or (>= i (count memo-keys)) (> n 6000)) [i out]
        (let [k (nth memo-keys i) l (get memo-map k)] (recur (inc i) (+ n (count k) (count l)) (conj out [k l])))))))

(defn- fake-eval
  "Recognizes only the controller's own templates (initialize-context!, executable/*,
  acquisition/*, runtime done source and pages) and the test's scripted model forms."
  [script worker source bindings]
  (let [form (u/read-edn source) head (when (seq? form) (first form))
        [b0 b1] (when (and (= 'let head) (vector? (second form))) (second form))]
    (cond
      (= source executable/drain-source) (let [v (:invocations @worker)] (swap! worker assoc :invocations {}) v)
      (= form '(do (def external-context "") nil)) (do (swap! worker assoc :context "") nil)
      (= form '(do (def external-context (str external-context chunk)) nil)) (do (swap! worker update :context str (:chunk bindings)) nil)
      (= form '(do (def aljure-exact {}) nil)) (do (swap! worker assoc :exact {}) nil)
      (= form '(do (def aljure-exact (merge aljure-exact aljure-chunk)) nil)) (do (swap! worker update :exact merge (:aljure-chunk bindings)) nil)
      (and (= 'do head) (= '(def aljure-invocations (atom {})) (second form))) (do (swap! worker assoc :invocations {}) nil)
      (and (= 'do head) (seq? (second form)) (= 'def (first (second form))))
      (let [[_ [_ name value]] form
            wrapped? (and (seq? value) (= 'let (first value)) (= 'aljure-f (first (second value))))
            code (if wrapped? (second (second value)) value)
            f (if (= code acq/exact-label-form)
                (fn [t] (when (string? t) (get (:exact @worker) (str/trim t))))
                (run-trusted code))]
        (swap! worker assoc-in [:defs (str name)] (if wrapped? (counting worker (a/forms-code-hash code) f) f))
        nil)
      (= 'aljure-p b0)
      (let [v ((run-trusted b1) (assoc (:aljure-public-input bindings) :context (:context @worker)))]
        (if (boolean? v) v :aljure/not-boolean))
      (and (= 'mapv head) (= 'aljure-items (last form)))
      (let [name (str (first (second (second (nth (second form) 2))))) f (get-in @worker [:defs name])]
        (mapv (fn [t] (let [v (f t)] (if (or (nil? v) (and (string? v) (<= (count v) 64))) v :aljure/not-a-label)))
              (:aljure-items bindings)))
      (and (= 'aljure-v b0) (= 'aljure-memo-map (second (nth form 2))))
      (let [v ((get script b1) worker) m (if (map? v) v {})
            ks (vec (take acq/max-memo-entries
                          (sort (filter (fn [k] (and (string? k) (<= 1 (count (str/trim k)) 1024) (string? (get m k))
                                                     (<= 1 (count (get m k)) 64))) (keys m)))))]
        (swap! worker assoc :memo-map m :memo-keys ks)
        [(map? v) (count m) (count ks)])
      (= 'loop head) (memo-page worker (second (second form)))
      (= 'aljure-v b0)
      (let [v ((get script b1) worker)] (swap! worker assoc :answer v) (if (string? v) [(count v) (hash v)] :aljure/not-a-string))
      (= 'e b0) (let [[_ [_ [_ n end]] [_ [_ _ start _]]] form e (min n end)] [e (subs (:answer @worker) start e)])
      :else ((or (get script form) (throw (ex-info "Worker rejected expression: unknown fixture source" {}))) worker))))

(defrecord FixtureBackend [script log]
  execution/ExecutionBackend
  (open! [_ _] (swap! log conj :open) (atom {:defs {} :invocations {} :context "" :exact {} :session {}}))
  (evaluate! [_ worker source bindings] (swap! log conj source) (fake-eval script worker source bindings))
  (close! [_ _] (swap! log conj :close)))

;; ---------------------------------------------------------------------------------------
;; A scripted tool-mode provider. Each call is reserved and reconciled at a fixed price, so
;; the ledger accounts for it exactly as for a real call.

(defrecord ScriptedToolProvider [queues usd seen]
  provider/Provider
  (invoke! [_ store run session messages]
    (let [id (str (java.util.UUID/randomUUID)) reply (first (get @queues session))]
      (u/ensure! reply "Fixture response queue exhausted" {:session session})
      (c/reserve! store run id session 1000 usd)
      (swap! queues update session #(vec (rest %)))
      (swap! seen conj {:session session :messages messages})
      (let [response (merge {:model "fixture-script-v1" :tokens 10 :usd usd :provider-id (str "fixture-" id) :request-id id
                             :usage {:input_tokens 5 :output_tokens 5} :provenance :synthetic-fixture :text ""}
                            reply)]
        (c/reconcile! store run id response)
        response))))

(defn- tool [name input] {:content [{:type "tool_use" :id (str "tu-" (java.util.UUID/randomUUID)) :name name :input input}]
                          :stop-reason "tool_use"})
(defn- done [summary] (tool "done" {:summary summary}))
(defn- text-reply [text] {:content [{:type "text" :text text}] :stop-reason "end_turn" :text text})
(defn- propose [input] (tool "propose_artifact" input))
(defn- e-proposal [name form predicate & [replaces]]
  (propose (cond-> {:name name :description (str "Labels " name " records.") :function_source (pr-str form)
                    :applicability_source (pr-str predicate)}
             replaces (assoc :replaces replaces))))

(def task-config
  (-> config (assoc :response-envelope wire/tool-envelope-version :sci-surface :raw :sci-results :raw)
      (assoc-in [:limits :history-records] Integer/MAX_VALUE)))

;; ---------------------------------------------------------------------------------------
;; Contexts and the controller-only development panel (FIXTURE data)

(def trec-header "The following lines contain questions. Categories: 'numeric value', 'human being', 'location', 'description and abstract concept', 'entity', 'abbreviation'.")
(def spam-header "The following lines contain text messages. Each text message can be classified as spam or ham (i.e., not spam).")
(defn- trec-text [i] (case (int (mod i 5)) 0 (str "Where is city " i " ?") 1 (str "Who wrote book " i " ?")
                       2 (str "How many legs does animal " i " have ?") 3 (str "What does ABC" i " stand for ?")
                       4 (str "What is the best fruit " i " ?")))
(defn- trec-label [i] (["location" "human being" "numeric value" "abbreviation" "entity"] (int (mod i 5))))
(def spam-items [["WIN a free prize now" "spam"] ["free entry txt now" "spam"] ["Call me later" "ham"] ["see you at noon" "ham"]
                 ["prize claim now" "spam"] ["ok lunch?" "ham"] ["Are you home" "ham"] ["you WIN cash" "spam"]
                 ["meeting moved" "ham"] ["thanks for the help" "ham"]])
(defn- context-of [header texts]
  (str header "\n\n" (str/join "\n" (map-indexed (fn [i t] (str "Date: Jan 01, 2023 || User: " (+ 100 i) " || Instance: " t " ")) texts)) "\n"))
(defn- trec-context [indices] (context-of trec-header (map trec-text indices)))
(def spam-context (context-of spam-header (map first spam-items)))

(def panel
  {:sha256 "fixture-panel"
   :windows [{:id "trec-p" :question "In the above data, which label is most common?" :context (trec-context (range 100 130))
              :items (mapv (fn [i] {:case (str "trec-p-" i) :text (trec-text i) :label (trec-label i)}) (range 100 130))}
             {:id "spam-p" :question "In the above data, how many messages are spam?" :context spam-context
              :items (vec (map-indexed (fn [i [t l]] {:case (str "spam-p-" i) :text t :label l}) spam-items))}]})

(def rule {:schema "aljure-promotion-rule-v1" :min_precision [19 20] :min_coverage [1 10] :min_panel_gain 1})
(def question-loc "In the above data, how many data points should be classified as label 'location'?")
(def question-spam "In the above data, how many data points should be classified as label 'spam'?")

;; ---------------------------------------------------------------------------------------
;; One task, as the external task runs it (prepare-artifacts!, run-session!, proposal turn)

(defn- events [store run type] (map :payload (filter #(= type (:type %)) (:events (c/get-run store run)))))

(defn run-task!
  [{:keys [root pin arm context question replies proposal script contract]}]
  (let [out (temp-root) store (str out "/controller.sqlite") run "external-task"
        cfg (cond-> task-config
              contract (update :contract merge contract)
              pin (assoc-in [:contract :artifacts] {:library root :library_sha256 pin})
              arm (assoc-in [:contract :acquisition] {:arm arm}))
        _ (c/create-run! store run cfg nil)
        _ (c/session! store run "root" nil)
        log (atom []) seen (atom [])
        backend (->FixtureBackend (or script {}) log)
        prov (->ScriptedToolProvider (atom {"root" replies "proposal" (if proposal [proposal] [])}) 0.01 seen)
        prewarmed (atom {}) recorded (atom nil)
        initialize (fn [_ worker] (swap! worker assoc :context context))
        result (with-redefs [execution/for-run (fn [_] backend) isolation/close-session! (fn [_] nil)]
                 (let [prepared (when pin (external/prepare-artifacts! {:store store :run run :spec {:library root :library_sha256 pin}
                                                                       :initialize initialize :question question
                                                                       :prewarmed prewarmed :context context}))]
                   (runtime/run-session!
                     (merge {:store store :run run :workers (atom {}) :prewarmed prewarmed :provider prov :initialize-worker initialize}
                            (:env prepared)
                            (when arm
                              {:after-root-done
                               (fn [d] (reset! recorded (external/proposal-turn! {:store store :run run :out out :arm arm :question question
                                                                                  :library-sha256 pin :provider prov} d)))}))
                     "root" (external/task-input {:question question} (:note prepared)))))]
    (when pin (c/update-run! store run #(c/event % :artifact-reuse-summary (skills/reuse-summary (:events %) result))))
    {:out out :store store :run run :result result :proposal @recorded :seen @seen :log @log
     :ledger (c/get-run store run)}))

(def validation-backend (->FixtureBackend {} (atom [])))
(defn- initialize-for [context] (fn [_ worker] (swap! worker assoc :context context)))

(defn- promote-task! [root arm pin task position]
  (when-let [p (:proposal task)]
    (acq/promote! {:arm arm :root root :pin pin :proposal-path (str (:out task) "/proposal.edn")
                   :proposal-sha256 (:proposal-sha256 p) :task-id (str "task-" position) :position position
                   :rule rule :panel panel :backend validation-backend :initialize initialize-for :deadline nil})))

(defn- empty-library! [root] (skills/write-library! root {:schema :aljure-library-v1 :parent nil :entries []}))

(defn trajectory!
  "The scripted fixture driver, mirroring benchmark/paired.py's trajectory runner: task k
  runs on the pin in force; its proposal is promoted only after its answer is recorded; the
  pin in force advances only on a complete, approved receipt. A crash keeps the pin."
  [root arm steps]
  (loop [pin (empty-library! root) rows [] [step & more] steps position 1]
    (cond
      (nil? step) {:rows rows :pin pin}
      (:rollback-to step)
      (recur (:rollback-to step) (conj rows {:type :rollback :from pin :to (:rollback-to step)}) more position)
      :else
      (let [before (set (.list (io/file root "libraries")))
            task (run-task! (merge {:root root :pin pin :arm arm} step))
            answered (:result task)
            receipt (try (binding [acq/*crash-hook* (or (:crash step) (fn [_] nil))] (promote-task! root arm pin task position))
                         (catch Exception e {:crashed (.getMessage e)}))
            committed (if (and (= :approved (:decision receipt)) (:receipt-sha256 receipt)) (:pin-after receipt) pin)]
        (recur committed
               (conj rows {:type :task :position position :pin-seen pin :pin-after committed :answer answered
                           :loaded (:library-sha256 (first (events (:store task) (:run task) :artifact-library-loaded)))
                           :proposal (:proposal task) :receipt receipt :libraries-before before :task task})
               more (inc position))))))

;; ---------------------------------------------------------------------------------------
;; The ten-task E fixture trajectory, reused by several tests

(def loc-script
  {'(count (filter (fn [q] (= "location" (trec-rules q))) records))
   (fn [w] (count (filter #(= "location" ((get-in @w [:defs "trec-rules"]) %)) (map trec-text (range 0 20)))))})

(def e-steps
  [{:context (trec-context (range 0 20)) :question question-loc :replies [(done "Answer: 4")]
    :proposal (e-proposal "trec-rules" where-who-form trec-taxonomy-form)}                      ; 1 approved
   {:context (trec-context (range 20 40)) :question question-loc :replies [(done "Answer: 4")]
    :proposal (e-proposal "entity-all" entity-all-form always-form)}                            ; 2 rejected: precision
   {:context (trec-context (range 40 60)) :question question-loc :replies [(done "Answer: 4")]
    :proposal (tool "skip_proposal" {})}                                                       ; 3 declined
   {:context (trec-context (range 60 80)) :question question-loc :replies [(done "Answer: 4")]
    :proposal (e-proposal "trec-rules" where-who-many-form trec-taxonomy-form "trec-rules")}    ; 4 approved: patch
   {:context (trec-context (range 80 100)) :question question-loc :replies [(done "Answer: 4")]
    :proposal (e-proposal "where-only" where-only-form trec-taxonomy-form)}                     ; 5 rejected: no gain
   {:context spam-context :question question-spam :replies [(done "Answer: 4")]
    :proposal (e-proposal "spam-words" spam-words-form spam-taxonomy-form)}                     ; 6 approved (F2)
   {:context (trec-context (range 0 20)) :question question-loc :script loc-script
    :replies [(tool "repl_eval" {:source "(count (filter (fn [q] (= \"location\" (trec-rules q))) records))"})
              (done "Answer: 4")]
    :proposal (e-proposal "trec-plus" trec-plus-form trec-taxonomy-form)}                       ; 7 approved: composition
   {:context (trec-context (range 20 40)) :question question-loc :replies [(done "Answer: 4")]
    :proposal (propose {:name "broken" :description "x" :function_source "(+ 1 2)" :applicability_source "(fn [i] true)"})} ; 8 malformed
   {:context spam-context :question question-spam :replies [(done "Answer: 4")]
    :proposal (text-reply "No proposal.")}                                                     ; 9 declined (text)
   {:context (trec-context (range 40 60)) :question question-loc :replies [(done "Answer: 4")]
    :proposal (e-proposal "where-who-again" where-who-form trec-taxonomy-form)}])               ; 10 rejected: no gain

(defonce e-run (delay (let [root (temp-root)] (assoc (trajectory! root "E" e-steps) :root root))))

;; ---------------------------------------------------------------------------------------
;; Tests

(deftest fixture-trajectory-carries-each-committed-pin-to-the-next-task
  (let [{:keys [rows]} @e-run tasks (filter #(= :task (:type %)) rows)]
    (is (= 10 (count tasks)))
    (is (= [:approved :rejected :no-proposal :approved :rejected :approved :approved :no-proposal :no-proposal :rejected]
           (mapv #(get-in % [:receipt :decision]) tasks)))
    (doseq [[a b] (partition 2 1 tasks)]
      ;; Task k+1 runs on exactly the pin committed after task k.
      (is (= (:pin-after a) (:pin-seen b)))
      (is (= (:pin-seen b) (:loaded b))))
    (doseq [t tasks]
      ;; The proposal names the pin the task saw; a task never sees its own promotion.
      (when (:proposal t) (is (= (:pin-seen t) (:library-sha256 (u/read-edn (slurp (str (get-in t [:task :out]) "/proposal.edn")))))))
      (when (not= (:pin-seen t) (:pin-after t))
        (is (not (contains? (:libraries-before t) (str (:pin-after t) ".edn"))))
        (is (= (:pin-seen t) (:parent (skills/load-library (:root @e-run) (:pin-after t)))))))
    ;; Rejections, declines and malformed proposals leave the pin in force.
    (doseq [t tasks :when (not= :approved (get-in t [:receipt :decision]))] (is (= (:pin-seen t) (:pin-after t))))
    (is (= [:proposed :proposed :declined :proposed :proposed :proposed :proposed :malformed :declined :proposed]
           (mapv #(get-in % [:proposal :decision]) tasks)))
    (is (= [:skipped :no-tool-call] (mapv #(get-in (nth tasks %) [:proposal :reason]) [2 8])))
    (is (= [:precision-below-minimum :library-precision-regression] (get-in (nth tasks 1) [:receipt :reasons])))
    (is (= [:insufficient-panel-gain] (get-in (nth tasks 4) [:receipt :reasons])))))

(deftest validation-records-patch-composition-and-the-library-panel-quality
  (let [{:keys [rows root pin]} @e-run tasks (vec (filter #(= :task (:type %)) rows))
        receipt (fn [k] (u/json-read (slurp (get-in (nth tasks k) [:receipt :receipt-path]))))
        library (skills/load-library root pin)
        statuses (mapv (juxt #(get-in % [:receipt :change]) :status) (:entries library))]
    ;; Task 4 edits the approved function structurally: one subtree, through artifact/patch.
    (is (= "patch" (get-in (receipt 3) [:candidate :change])))
    (is (= [2] (get-in (receipt 3) [:candidate :patch-path])))
    (is (= (get-in (receipt 0) [:candidate :artifact]) (get-in (receipt 3) [:candidate :parent])))
    ;; Task 7 composes: its function calls the approved trec-rules, pinned by exact hash.
    (is (= [(get-in (receipt 3) [:candidate :artifact])] (get-in (receipt 6) [:candidate :dependencies])))
    (is (= [[:new :superseded] [:patch :approved] [:new :approved] [:new :approved]] statuses))
    ;; Library quality per version on the panel (controller-only gold): coverage rises, precision holds.
    (is (= [{:items 40 :decided 12 :correct 12} {:items 40 :decided 18 :correct 18} {:items 40 :decided 22 :correct 22}
            {:items 40 :decided 28 :correct 28}]
           (mapv #(get-in (receipt %) [:library :proposed]) [0 3 5 6])))
    ;; The incompatible spam window refused the trec classifier; the always-true predicate was admitted there and lost precision.
    (is (= ["trec-p"] (get-in (receipt 0) [:candidate-panel :admitted-windows])))
    (is (= {:items 40 :decided 40 :correct 6} (select-keys (get-in (receipt 1) [:candidate-panel]) [:items :decided :correct])))
    ;; Receipts hold case ids, pass/fail and counts, never a gold label.
    (doseq [k [0 1 3 4 5 6 9]]
      (is (zero? (get (receipt k) :model-calls)))
      (is (number? (get (receipt k) :validation-ms)))
      (is (not (re-find #"numeric value|human being|abbreviation" (slurp (get-in (nth tasks k) [:receipt :receipt-path]))))))))

(deftest incompatible-taxonomy-classifier-is-refused-and-the-refusal-recorded
  (let [{:keys [rows root]} @e-run tasks (vec (filter #(= :task (:type %)) rows))
        refusals (fn [k] (let [t (get-in tasks [k :task])]
                           (mapv (juxt :name :decision :reason) (events (:store t) (:run t) :artifact-applicability))))
        summary (fn [k] (let [t (get-in tasks [k :task])] (first (events (:store t) (:run t) :artifact-reuse-summary))))]
    ;; Task 6 (spam): the approved trec classifier is refused by its predicate, before any model call.
    (is (= [["trec-rules" :refuse :inapplicable]] (refusals 5)))
    ;; Task 9 (spam): both trec functions refused, the spam function admitted.
    (is (= [["trec-rules" :refuse :inapplicable] ["spam-words" :preload :applicable] ["trec-plus" :refuse :inapplicable]]
           (refusals 8)))
    (is (= #{:inapplicable} (set (map :reason (:refused (summary 8))))))
    (is (= 2 (count (:refused (summary 8)))))
    ;; The F1 task 7 got trec-rules preloaded and called it; the call is recorded by code hash.
    (let [t (get-in tasks [6 :task]) batches (events (:store t) (:run t) :artifact-invocations)]
      (is (= [["trec-rules" :preload :applicable] ["spam-words" :refuse :inapplicable]] (refusals 6)))
      (is (= [20] (mapv :calls (mapcat :invocations batches))))
      (is (= (:code-hash (first (filter #(= "trec-rules" (get-in % [:function :interface :name]))
                                        (:approved (skills/discover root (get-in tasks [6 :pin-seen]))))))
             (:code-hash (first (mapcat :invocations batches))))))))

(deftest fresh-process-restoration-after-task-10-reads-only-the-bundle
  (let [{:keys [root pin]} @e-run
        bundle (str (temp-root) "/bundle")
        _ (doseq [f (file-seq (io/file root)) :when (.isFile f)
                  :let [rel (subs (str f) (inc (count root)))]
                  :when (re-find #"^(artifacts|libraries|memos|receipts)/" rel)]
            (io/make-parents (io/file bundle rel)) (io/copy f (io/file bundle rel)))
        request (str (temp-root) "/restore.json")
        _ (spit request (u/json-str {:library bundle :pin pin}))
        process (.start (ProcessBuilder. ^java.util.List ["python3" "scripts/clj.py" "-m" "repl-lab.acquisition" "restore" request]))
        output (future (slurp (.getInputStream process)))]
    (is (.waitFor process 180 java.util.concurrent.TimeUnit/SECONDS))
    (let [fresh (u/json-read (last (str/split-lines @output)))
          here (u/json-read (u/json-str (acq/restore root pin)))]
      ;; A new JVM reads the same bytes by pin and re-derives byte-identical code hashes.
      (is (= here fresh))
      (is (= pin (:pin fresh)))
      (is (= 3 (count (:approved fresh)))))
    ;; Task 11 runs from the bundle alone and preloads exactly the approved functions.
    (let [task (run-task! {:root bundle :pin pin :arm "E" :context (trec-context (range 0 20)) :question question-loc
                           :replies [(done "Answer: 4")] :proposal (tool "skip_proposal" {})})
          preloaded (first (events (:store task) (:run task) :artifact-preloaded))]
      (is (= (set (map :code-hash (filter #(= :export (:role %)) (:functions preloaded))))
             (set (keep #(when (#{"trec-rules" "trec-plus"} (get-in % [:function :interface :name])) (:code-hash %))
                        (:approved (skills/discover root pin)))))))))

(deftest rollback-a-failed-or-crashed-promotion-keeps-the-previous-pin
  (let [first-step {:context (trec-context (range 0 20)) :question question-loc :replies [(done "Answer: 4")]
                    :proposal (e-proposal "trec-rules" where-who-form trec-taxonomy-form)}
        patch-step (fn [crash] {:context (trec-context (range 20 40)) :question question-loc :replies [(done "Answer: 4")]
                                :proposal (e-proposal "trec-rules" where-who-many-form trec-taxonomy-form "trec-rules")
                                :crash (fn [stage] (when (= stage crash) (throw (ex-info (str "crash at " stage) {}))))})
        run (fn [crash] (let [root (temp-root)] (assoc (trajectory! root "E" [first-step (patch-step crash)]) :root root)))
        files (fn [root dir] (set (.list (io/file root dir))))]
    (doseq [crash [:after-artifacts :after-version-write :after-receipt]]
      (let [{:keys [rows root]} (run crash) [one two] rows]
        (is (= (:pin-after one) (:pin-seen two) (:pin-after two)) (str crash))
        (is (re-find #"crash at" (get-in two [:receipt :crashed])))
        ;; No partial library: every version on disk is complete and verifies; nothing is deleted.
        (doseq [f (files root "libraries")] (is (skills/load-library root (str/replace f ".edn" ""))))
        (case crash
          :after-artifacts (is (= 2 (count (files root "libraries"))))
          :after-version-write (do (is (= 3 (count (files root "libraries"))))
                                   (is (= 1 (count (files root "receipts")))))
          ;; The unknown state stays on disk for inspection; the trajectory never adopted it.
          :after-receipt (do (is (= 3 (count (files root "libraries")))) (is (= 2 (count (files root "receipts"))))))))
    ;; Explicit rollback to a prior pin: the next task sees it, and the next version builds on it.
    (let [root (temp-root)
          {:keys [rows]} (trajectory! root "E" [first-step
                                                {:context spam-context :question question-spam :replies [(done "Answer: 4")]
                                                 :proposal (e-proposal "spam-words" spam-words-form spam-taxonomy-form)}])
          pin1 (:pin-after (first rows)) pin2 (:pin-after (second rows))
          {rolled :rows} (trajectory! root "E" [first-step
                                                {:context spam-context :question question-spam :replies [(done "Answer: 4")]
                                                 :proposal (e-proposal "spam-words" spam-words-form spam-taxonomy-form)}
                                                {:rollback-to pin1}
                                                (patch-step nil)])
          rollback (nth rolled 2) after (nth rolled 3)]
      (is (not= pin1 pin2))
      (is (= {:type :rollback :from (:pin-after (second rolled)) :to pin1} rollback))
      (is (= pin1 (:pin-seen after) (:loaded after)))
      (is (= :approved (get-in after [:receipt :decision])))
      (is (= pin1 (:parent (skills/load-library root (:pin-after after))))))))

(deftest provenance-chain-names-parent-task-receipt-and-code-hashes
  (let [{:keys [root pin rows]} @e-run
        receipts (for [f (.listFiles (io/file root "receipts"))] (u/json-read (slurp f)))
        approved (filter #(= "approved" (:decision %)) receipts)
        chain (loop [p pin out []] (if p (recur (:parent (skills/load-library root p)) (conj out p)) out))]
    (is (= 5 (count chain)))
    (is (= (set (butlast chain)) (set (map :pin-after approved))))
    (doseq [r approved]
      (let [version (skills/load-library root (:pin-after r))
            entry (first (filter #(= (get-in r [:candidate :artifact]) (:artifact %)) (:entries version)))]
        (is (= (:parent-pin r) (:parent version)))
        (is (= (:task-id r) (get-in entry [:receipt :task])))
        (is (= (:position r) (get-in entry [:receipt :position])))
        (is (= (:proposal-sha256 r) (get-in entry [:receipt :proposal-sha256])))
        (is (= (get-in r [:candidate :code-hash]) (:code-hash entry) (a/code-hash (a/load! root (:artifact entry)))))
        (is (= (get-in r [:candidate :applicability-code-hash]) (:applicability-code-hash entry)))))
    ;; Every candidate is kept: 4 approved, 3 rejected, 3 recorded without a proposal.
    (is (= {"approved" 4 "rejected" 3 "no-proposal" 3} (frequencies (map :decision receipts))))
    (is (every? #(.exists (io/file root "artifacts" (str (get-in % [:candidate :artifact]) ".edn")))
                (filter :candidate receipts)))))

(deftest cost-accounting-charges-fallback-and-the-proposal-turn-apart
  (let [{:keys [rows root]} @e-run
        pin (:pin-after (first rows))
        records (map trec-text (range 0 20))
        script {'(mapv trec-rules records) (fn [w] (mapv (get-in @w [:defs "trec-rules"]) records))
                ;; Fallback: the model decides the records the library left unresolved.
                '(count (remove trec-rules records)) (fn [w] (count (remove (get-in @w [:defs "trec-rules"]) records)))}
        task (run-task! {:root root :pin pin :arm "E" :context (trec-context (range 0 20)) :question question-loc :script script
                         :replies [(tool "repl_eval" {:source "(mapv trec-rules records)"})
                                   (tool "repl_eval" {:source "(count (remove trec-rules records))"})
                                   (done "Answer: 4")]
                         :proposal (tool "skip_proposal" {})})
        ledger (:ledger task) spend (acq/acquisition-spend ledger)
        root-calls (filter #(= "root" (:session (val %))) (:provider-requests ledger))]
    (is (= {:summary "Answer: 4"} (:result task)))
    ;; Every call is charged: three task-inference calls (one of them fallback) and one proposal call.
    (is (= 4 (get-in ledger [:spent :calls])))
    (is (= 3 (count root-calls)))
    (is (= {:session "proposal" :calls 1 :unknown 0} (select-keys spend [:session :calls :unknown])))
    (is (< (Math/abs (- 0.01 (:usd spend))) 1e-9))
    (is (< (Math/abs (- 0.03 (- (get-in ledger [:spent :usd]) (:usd spend)))) 1e-9))
    (is (= 1 (count (:provider-ids spend))))
    ;; The proposal turn sees the whole conversation and the instruction, after the answer.
    (let [turn (last (:seen task)) last-message (last (:messages turn))]
      (is (= "proposal" (:session turn)))
      (is (str/includes? (get-in last-message [:content 0 :content]) "Answer recorded")))))

(deftest arm-a-never-offers-a-proposal-and-the-answer-path-is-unchanged
  (let [a (run-task! {:context (trec-context (range 0 20)) :question question-loc :replies [(done "Answer: 4")]})]
    (is (= {:summary "Answer: 4"} (:result a)))
    (is (= 1 (get-in a [:ledger :spent :calls])))
    (is (nil? (get-in a [:ledger :sessions "proposal"])))
    (is (empty? (events (:store a) (:run a) :artifact-proposal)))
    (is (not (.exists (io/file (:out a) "answer-recorded.json")))))
  ;; Arm E with the answer-format validator: the notice still comes first, the accepted answer
  ;; is recorded before the optional turn, and declining changes nothing.
  (let [e (run-task! {:arm "E" :root (temp-root) :pin nil :context (trec-context (range 0 20)) :question question-loc
                      :contract {:answer-format {:max-lines 1 :max-chars 64}}
                      :replies [(done "Answer: 4\nbecause four lines say location") (done "Answer: 4")]
                      :proposal (tool "skip_proposal" {})})]
    (is (= {:summary "Answer: 4"} (:result e)))
    (is (= 1 (count (events (:store e) (:run e) :answer-format-notice))))
    (is (= (u/sha "Answer: 4") (:sha256 (u/json-read (slurp (io/file (:out e) "answer-recorded.json"))))))
    (is (= "Answer: 4" (slurp (io/file (:out e) "answer.txt"))))
    (is (= :declined (get-in e [:proposal :decision])))
    (is (= :complete (get-in e [:ledger :sessions "root" :status]))))
  ;; No budget left: the turn is not offered, and the recorded answer stands.
  (let [e (with-redefs [task-config (assoc-in task-config [:limits :calls] 1)]
            (run-task! {:arm "E" :root (temp-root) :context (trec-context (range 0 20)) :question question-loc
                        :replies [(done "Answer: 4")] :proposal (tool "skip_proposal" {})}))]
    (is (= {:summary "Answer: 4"} (:result e)))
    (is (= :not-offered (get-in e [:proposal :decision])))
    (is (re-find #"budget" (get-in e [:proposal :reason])))))

(deftest arm-c-reuses-exact-items-and-exact-questions-only
  (let [root (temp-root)
        labels (fn [indices] (into {} (map (fn [i] [(str (trec-text i) " ") (trec-label i)]) indices)))
        ;; The model labelled the records in its session; memo_source reads them from that worker.
        session (fn [indices] {'(do labels) (fn [_] (labels indices)) '(count records) (fn [_] (count indices))})
        labelled (fn [& replies] (into [(tool "repl_eval" {:source "(count records)"})] replies))
        question-hum "In the above data, how many data points should be classified as label 'human being'?"
        exact-call '(exact-label "Where is city 10 ?")
        steps [{:context (trec-context (range 0 20)) :question question-loc :script (session (range 0 20))
                :replies (labelled (done "Answer: 4"))
                :proposal (propose {:name "loc-count" :description "Answer for this exact question." :memo_source "labels"
                                    :function_source (pr-str answer-six-form)})}
               {:context (trec-context (range 10 30)) :question question-hum
                :script (merge (session (range 10 30)) {exact-call (fn [w] ((get-in @w [:defs "exact-label"]) "Where is city 10 ?"))})
                :replies (labelled (tool "repl_eval" {:source (pr-str exact-call)}) (done "Answer: 4"))
                :proposal (propose {:name "hum-memo" :description "Labels from this context." :memo_source "labels"})}
               {:context spam-context :question question-spam :replies [(done "Answer: 4")] :proposal (tool "skip_proposal" {})}
               {:context (trec-context (range 0 20)) :question question-loc :replies [(done "Answer: 4")]
                :proposal (tool "skip_proposal" {})}]
        {:keys [rows]} (trajectory! root "C" steps)
        decisions (fn [k] (let [t (:task (nth rows k))] (mapv (juxt :name :decision :reason) (events (:store t) (:run t) :artifact-applicability))))
        hits (fn [k] (let [t (:task (nth rows k))] (:hits (first (events (:store t) (:run t) :artifact-memo-loaded)))))]
    (is (= [:approved :approved :no-proposal :no-proposal] (mapv #(get-in % [:receipt :decision]) rows)))
    (is (= {:proposed 20 :added 20 :conflicts-kept-earlier 0 :total 20} (u/read-edn (pr-str (:memo (u/json-read (slurp (get-in (first rows) [:receipt :receipt-path]))))))))
    ;; Task 2: ten exact item matches; the function keyed by another question is refused.
    (is (= [["loc-count" :refuse :inapplicable] ["exact-label" :preload :exact-match]] (decisions 1)))
    (is (= 10 (hits 1)))
    (let [t (:task (nth rows 1)) batch (first (events (:store t) (:run t) :artifact-invocations))]
      (is (= [{:name "exact-label" :calls 1 :values ["location"]}] (mapv #(select-keys % [:name :calls :values]) (:invocations batch))))
      ;; A memo without a session worker cannot be read: the model never evaluated anything.
      (is (= :malformed (get-in (run-task! {:arm "C" :root root :pin (:pin-after (first rows)) :context (trec-context (range 0 5))
                                            :question question-loc :replies [(done "Answer: 1")]
                                            :proposal (propose {:name "m" :description "d" :memo_source "labels"})})
                                [:proposal :decision]))))
    (is (= 30 (:total (:memo (u/json-read (slurp (get-in (second rows) [:receipt :receipt-path])))))))
    ;; Task 3 (spam): no exact match, no exact question: everything refused and recorded.
    (is (= [["loc-count" :refuse :inapplicable] ["exact-label" :refuse :no-exact-match]] (decisions 2)))
    ;; Task 4 asks exactly the first question again: its function and all twenty items return.
    (is (= [["loc-count" :preload :applicable] ["exact-label" :preload :exact-match]] (decisions 3)))
    (is (= 20 (hits 3)))
    ;; No validation and no panel in arm C.
    (is (every? #(nil? (get-in % [:receipt :validation-ms])) rows))))

(deftest a-committed-version-is-scored-offline-with-counts-only
  (let [{:keys [root pin]} @e-run
        scored (acq/score-version {:root root :pin pin :panel panel :backend validation-backend
                                   :initialize initialize-for :deadline nil})
        empty-root (temp-root)
        empty (acq/score-version {:root empty-root :pin (empty-library! empty-root) :panel panel :backend nil
                                  :initialize initialize-for :deadline nil})]
    ;; The same cascade the promotion rule used: the final version's receipt counts.
    (is (= {:items 40 :decided 28 :correct 28} (:metrics scored)))
    (is (= [3 0] [(:approved scored) (:model-calls scored)]))
    (is (= (:metrics scored) (apply merge-with + (map #(select-keys % [:items :decided :correct]) (:windows scored)))))
    ;; The spam window admits only the spam classifier; nothing errs.
    (is (= [["trec-p" 2 0] ["spam-p" 1 0]] (mapv (juxt :window :admitted :errors) (:windows scored))))
    (is (not (re-find #"numeric value|human being|abbreviation|location|\"spam\"|\"ham\"" (u/json-str scored))))
    ;; An empty version opens no worker (the backend is nil) and decides nothing.
    (is (= {:items 40 :decided 0 :correct 0} (:metrics empty)))))

(deftest promotion-rule-boundaries-use-exact-arithmetic
  (let [ok {:decided 0 :correct 0} evidence {:no-regression true :score-gain 1}
        cand (fn [items decided correct] {:items items :decided decided :correct correct :admitted-windows ["w"] :errors [] :non-labels 0})]
    (is (:approved (acq/decide rule (cand 100 10 10) ok {:decided 10 :correct 10} evidence)))
    (is (= [:coverage-below-minimum] (:reasons (acq/decide rule (cand 100 9 9) ok {:decided 9 :correct 9} evidence))))
    (is (:approved (acq/decide rule (cand 20 20 19) ok {:decided 20 :correct 19} evidence)))
    (is (= [:precision-below-minimum] (:reasons (acq/decide rule (cand 20 20 18) ok {:decided 20 :correct 18} evidence))))
    ;; A growing library is not assumed better: lower library precision or coverage is refused.
    (is (= [:library-precision-regression]
           (:reasons (acq/decide rule (cand 20 20 19) {:decided 10 :correct 10} {:decided 30 :correct 29} evidence))))
    (is (= [:library-coverage-regression]
           (:reasons (acq/decide rule (cand 20 20 20) {:decided 30 :correct 29} {:decided 25 :correct 25} evidence))))
    (is (= [:item-regression :insufficient-panel-gain]
           (:reasons (acq/decide rule (cand 20 20 20) ok {:decided 20 :correct 20} {:no-regression false :score-gain 0}))))
    (is (= [:no-applicable-panel-window :precision-below-minimum]
           (:reasons (acq/decide rule (assoc (cand 0 0 0) :admitted-windows []) ok ok evidence))))))

(deftest structural-diff-and-proposal-checks
  (is (= [2 4] (acq/diff-path '(fn [x] (cond a 1 b 2)) '(fn [x] (cond a 1 b 3)))))
  (is (= [2] (acq/diff-path '(fn [x] (cond a 1)) '(fn [x] (cond a 1 b 3)))))
  (is (= [] (acq/diff-path '(fn [x] 1) '(fn [x y] 2))))
  (let [root (temp-root) pin (empty-library! root)
        check (fn [input] (let [task (run-task! {:arm "E" :root root :pin pin :context (trec-context (range 0 5)) :question question-loc
                                                 :replies [(done "Answer: 1")] :proposal (propose input)})]
                            (:proposal task)))
        base {:name "x-rules" :description "d" :function_source (pr-str where-who-form) :applicability_source (pr-str always-form)}]
    (is (= :proposed (:decision (check base))))
    (doseq [bad [(assoc base :name "count") (assoc base :name "exact-label") (assoc base :name "aljure-x")
                 (assoc base :function_source "#(str %)") (assoc base :function_source "(fn [a b] a)")
                 (assoc base :applicability_source "true") (assoc base :description (apply str (repeat 241 "d")))]]
      (is (= :malformed (:decision (check bad))) (pr-str bad)))))

(deftest acquisition-sources-are-worker-readable-and-use-no-denied-symbol
  (let [denied (set (map str (u/read-edn (second (re-find #"(?s)\(def denied '(\[.*?\])\)" (slurp "worker/src/repl_lab/worker.clj"))))))
        sources (concat [(acq/label-source "trec-rules") (acq/memo-source "(into {} (map (fn [r] [r \"x\"]) rows))")
                         (acq/memo-page-source 0)]
                        (map first (acq/memo-chunks {"Where is x ?" "location"}))
                        (executable/preload-sources [(acq/exact-label-function)]))]
    (doseq [source sources]
      (let [form (u/read-edn source) symbols (set (map str (filter symbol? (tree-seq coll? seq form))))]
        (is (empty? (filter denied symbols)) source)
        (is (< (count (.getBytes ^String source "UTF-8")) 65000))))
    ;; A memo chunk stays below the worker's request bound for any number of hits.
    (let [hits (into {} (for [i (range 3000)] [(str "item text number " i " with some words ?") "description and abstract concept"]))]
      (doseq [[source bindings] (acq/memo-chunks hits)]
        (is (< (count (.getBytes (pr-str {:source source :bindings bindings}) "UTF-8")) 65535))))))
