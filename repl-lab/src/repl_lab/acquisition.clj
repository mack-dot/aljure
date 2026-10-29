(ns repl-lab.acquisition
  "Acquisition between tasks (aljure_contract.acquisition, off by default). Three parts:

  1. One optional proposal turn after the root's answer is final and recorded (arms C and
     E only). The model may submit a function and an applicability contract from its own
     session, or decline. The turn runs as session \"proposal\", so its cost is acquisition
     cost, never task inference.
  2. Validation of an arm-E proposal on a controller-only development panel, in fresh
     isolated SCI workers (one for the approved entries, one for the candidate), with no
     model call. Promotion follows the preregistered rule
     (research/THESIS_PILOT_PROTOCOL.md) and the corrected artifact/promotion-evidence path.
  3. Content-addressed promotion: a new immutable library version (skills.clj) whose
     :parent is the pin the task saw. Arm C keeps exact reuse only: an item-text memo and
     functions keyed by the exact task question, with no validation.

  Gold labels stay on the controller: receipts keep case ids, pass/fail and counts only."
  (:require [clojure.string :as str] [clojure.java.io :as io]
            [repl-lab.util :as u] [repl-lab.artifact :as a] [repl-lab.skills :as skills]
            [repl-lab.executable :as executable] [repl-lab.execution :as execution]
            [repl-lab.controller :as c] [repl-lab.provider :as provider]
            [repl-lab.model-protocol :as wire]))

(def ^:dynamic *crash-hook* (fn [_] nil))
(def arms #{"C" "E"})
(def max-memo-entries 20000)
(def exact-label-name "exact-label")
;; The controller's exact-reuse lookup (arm C). Item text is compared after trimming.
(def exact-label-form '(fn [text] (when (string? text) (get aljure-exact (clojure.string/trim text)))))

;; ---------------------------------------------------------------------------------------
;; 1. The proposal turn

(defn- object-schema [properties required]
  {:type "object" :properties properties :required required :additionalProperties false})

(def ^:private name-field
  {:type "string" :description "Exported function name: lowercase kebab-case, for example trec-rules. Not a clojure.core name."})
(def ^:private description-field
  {:type "string" :description "What the function does and when it applies, in at most 240 characters."})

(defn proposal-tools
  "The two proposal tools. They are offered only in the proposal turn, never during a task."
  [arm]
  (u/ensure! (arms arm) "Unknown acquisition arm" {:arm arm})
  [{:name "propose_artifact"
    :description (if (= "E" arm)
                   (str "Propose one function from this session for reuse in later tasks. The controller tests it on "
                        "labeled records from other contexts, without any model call, and keeps it only if the fixed "
                        "promotion rule passes. A kept function is defined in later tasks where its applicability "
                        "predicate returns true.")
                   (str "Propose exact reuse for later tasks: a memo of the labels you assigned to records in this "
                        "session, and optionally a function. Nothing is tested. The memo is used only for records "
                        "whose text matches exactly; the function only when a later task asks exactly this question."))
    :input_schema
    (if (= "E" arm)
      (object-schema
        {:name name-field :description description-field
         :function_source {:type "string" :description (str "One self-contained Clojure form (fn [text] ...). text is one record's "
                                                            "text (the part after 'Instance: '). Return its label exactly as the task names it, as a "
                                                            "string, or nil when the function cannot decide. It may call preloaded functions by name; "
                                                            "it cannot use other definitions from this session.")}
         :applicability_source {:type "string" :description (str "One self-contained Clojure form (fn [input] ...). input is "
                                                                 "{:question <task question> :context <the complete context text>}. Return true only when "
                                                                 "the function applies to that task's records and labels, otherwise false.")}
         :replaces {:type "string" :description "Optional: the name of a preloaded function that this one improves and replaces."}}
        ["name" "description" "function_source" "applicability_source"])
      (object-schema
        {:name name-field :description description-field
         :memo_source {:type "string" :description (str "Clojure evaluated in this session's SCI worker, with access to your "
                                                        "definitions. It must return a map from each record's exact text (the part after "
                                                        "'Instance: ') to the label you assigned it, as a string.")}
         :function_source {:type "string" :description (str "Optional. One self-contained Clojure form (fn [...] ...). It is "
                                                            "defined again only when a later task asks exactly this question.")}}
        ["name" "description"]))}
   {:name "skip_proposal" :description "Decline the optional proposal. There is no penalty."
    :input_schema (object-schema {} [])}])

(defn instruction
  "The tool result for the root's done call, in arms C and E only."
  [arm]
  (str "Answer recorded. It is final and will be scored as submitted; nothing in this turn can change it.\n"
       "Optional, one turn, no penalty: "
       (if (= "E" arm)
         (str "you may propose one function from this session that labels single records, for reuse in later tasks. "
              "The controller tests it, without any model call, on labeled records from other contexts. It keeps the "
              "function only if the labels it decides are at least 95% correct, it decides at least 10% of the records "
              "its applicability predicate accepts, and the library as a whole does not get worse. ")
         (str "you may propose exact reuse for later tasks: the labels you assigned to this context's records, and "
              "optionally a function for this exact question. Nothing is tested. "))
       "Call propose_artifact to propose, or skip_proposal to decline. Do not call any other tool."))

(def ^:private name-re #"[a-z][a-z0-9-]{0,47}")

(defn- read-fn-form!
  "One model form, read with Clojure syntax and no evaluation (wire/read-forms), as code data."
  [source what arity]
  (u/ensure! (and (string? source) (<= (count (.getBytes ^String source "UTF-8")) 32768))
             (str what " must be a string of at most 32 KB") {})
  (let [forms (wire/read-forms source) form (first forms)]
    (u/ensure! (and (= 1 (count forms)) (seq? form) (= 'fn (first form)) (vector? (second form))
                    (every? symbol? (second form)) (or (nil? arity) (= arity (count (second form)))))
               (str what " must be exactly one (fn [" (if (= 1 arity) "x" "...") "] ...) form") {})
    form))

(defn printed [form]
  (binding [*print-namespace-maps* false *print-meta* false *print-length* nil *print-level* nil
            *print-readably* true *print-dup* false]
    (pr-str form)))

(defn- check-proposal-input!
  "Structure only. The function itself is never run on the host."
  [arm input]
  (u/ensure! (map? input) "Proposal input must be an object" {})
  (let [{:keys [name description function_source applicability_source replaces memo_source]} input
        reserved (executable/reserved-names)]
    (u/ensure! (and (string? name) (re-matches name-re name) (not (reserved name)) (not (str/starts-with? name "aljure-"))
                    (not= exact-label-name name))
               "name must be lowercase kebab-case and not a reserved name" {})
    (u/ensure! (and (string? description) (<= 1 (count description) 240)) "description must be 1-240 characters" {})
    (if (= "E" arm)
      (let [function (read-fn-form! function_source "function_source" 1)
            predicate (read-fn-form! applicability_source "applicability_source" 1)]
        (u/ensure! (or (nil? replaces) (and (string? replaces) (re-matches name-re replaces))) "replaces must be a function name" {})
        (cond-> {:name name :description description :function-source (printed function)
                 :applicability-source (printed predicate)}
          replaces (assoc :replaces replaces)))
      (do
        (u/ensure! (or (string? memo_source) (string? function_source)) "Propose a memo, a function or both" {})
        (u/ensure! (or (nil? memo_source) (and (string? memo_source) (<= (count (.getBytes ^String memo_source "UTF-8")) 32768)))
                   "memo_source must be a string of at most 32 KB" {})
        (cond-> {:name name :description description}
          function_source (assoc :function-source (printed (read-fn-form! function_source "function_source" nil)))
          memo_source (assoc :memo-source memo_source))))))

(defn memo-key [text] (u/sha (str/trim text)))

(def ^:private memo-page-chars 6000)

(defn memo-source
  "Evaluates the model's memo expression in its own session worker and keeps only string
  keys (1-1024 characters) with string labels (1-64 characters), sorted, at most 20,000."
  [source]
  (str "(let [aljure-v " (printed (cons 'do (wire/read-forms source))) "] "
       "(def aljure-memo-map (if (map? aljure-v) aljure-v {})) "
       "(def aljure-memo-keys (vec (take " max-memo-entries " (sort (filter (fn [aljure-k] (and (string? aljure-k) "
       "(<= 1 (count (clojure.string/trim aljure-k)) 1024) (string? (get aljure-memo-map aljure-k)) "
       "(<= 1 (count (get aljure-memo-map aljure-k)) 64))) (keys aljure-memo-map)))))) "
       "[(map? aljure-v) (count aljure-memo-map) (count aljure-memo-keys)])"))

(defn memo-page-source
  "One page of the memo, below the worker's output bound for any text."
  [start]
  (str "(loop [aljure-i " start " aljure-n 0 aljure-out []] "
       "(if (or (>= aljure-i (count aljure-memo-keys)) (> aljure-n " memo-page-chars ")) [aljure-i aljure-out] "
       "(let [aljure-k (nth aljure-memo-keys aljure-i) aljure-l (get aljure-memo-map aljure-k)] "
       "(recur (inc aljure-i) (+ aljure-n (count aljure-k) (count aljure-l)) (conj aljure-out [aljure-k aljure-l])))))"))

(defn read-memo!
  "The model's memo from its session worker, as {sha256-of-trimmed-text label}."
  [backend worker source]
  (u/ensure! worker "No session worker: the memo needs this session's definitions" {})
  (let [[is-map total kept] (execution/evaluate! backend worker (memo-source source) {})]
    (u/ensure! (true? is-map) "memo_source must return a map" {})
    (u/ensure! (and (nat-int? kept) (<= kept max-memo-entries)) "Memo readout failed" {})
    (loop [start 0 entries {}]
      (if (>= start kept)
        {:entries entries :returned total :kept (count entries) :dropped (- total (count entries))}
        (let [[end page] (execution/evaluate! backend worker (memo-page-source start) {})]
          (u/ensure! (and (int? end) (< start end) (<= end kept) (vector? page)
                          (every? #(and (vector? %) (= 2 (count %)) (string? (first %)) (string? (second %))
                                        (<= 1 (count (second %)) 64)) page))
                     "Memo page malformed" {})
          (recur end (reduce (fn [m [k label]] (let [h (memo-key k)] (if (contains? m h) m (assoc m h label)))) entries page)))))))

(defn proposal-call
  "Which proposal tool the reply called. Anything else is a decline; nothing is run."
  [response]
  (let [calls (filter #(= "tool_use" (:type %)) (:content response))]
    (cond (empty? calls) [:declined :no-tool-call nil]
          (> (count calls) 1) [:declined :multiple-calls nil]
          (= "skip_proposal" (:name (first calls))) [:declined :skipped nil]
          (= "propose_artifact" (:name (first calls))) [:proposed nil (:input (first calls))]
          :else [:declined :other-tool nil])))

(defn propose!
  "The optional proposal turn. Runs after the root's answer is recorded and before the
  root's workers close. The answer cannot change. One provider call at most, under the
  task's own caps, in session \"proposal\". Writes <out>/proposal.edn and returns its summary."
  [{:keys [store run arm provider config backend out question library-sha256]} {:keys [messages response worker]}]
  (let [base {:schema :aljure-proposal-v1 :arm arm :question question :library-sha256 library-sha256}
        record (try
                 (c/session! store run "proposal" nil)
                 (let [history (into (vec messages) (wire/result-messages config response {:value (instruction arm)}))
                       reply (provider/invoke! provider store run "proposal" history)
                       [decision reason input] (proposal-call reply)]
                   (merge base {:request-id (:request-id reply) :provider-id (:provider-id reply)}
                          (if (= :proposed decision)
                            (try
                              (let [checked (check-proposal-input! arm input)
                                    memo (when (:memo-source checked) (read-memo! backend worker (:memo-source checked)))]
                                (merge {:decision :proposed} checked
                                       (when memo {:memo (:entries memo) :memo-counts (dissoc memo :entries)})))
                              (catch Exception e
                                {:decision :malformed :reason (let [m (str (.getMessage e))] (subs m 0 (min 300 (count m))))
                                 :input-keys (vec (sort (map name (keys input))))}))
                            {:decision decision :reason reason})))
                 (catch Exception e
                   (merge base {:decision :not-offered :reason (let [m (str (.getMessage e))] (subs m 0 (min 300 (count m))))})))
        _ (when (get-in (c/get-run store run) [:sessions "proposal"])
            (try (c/finish-session! store run "proposal" :complete {:decision (:decision record)}) (catch Exception _ nil)))
        path (str out "/proposal.edn")
        _ (u/write-edn! path record)
        summary (merge (select-keys record [:decision :reason :request-id :provider-id :name :replaces :memo-counts])
                       {:proposal-sha256 (u/sha (slurp path))})]
    (c/update-run! store run #(c/event % :artifact-proposal summary))
    summary))

(defn acquisition-spend
  "The proposal session's provider calls, apart from task inference."
  [ledger]
  (let [requests (filter #(= "proposal" (:session (val %))) (:provider-requests ledger))]
    {:session "proposal" :calls (count requests)
     :usd (reduce + 0.0 (keep #(get-in (val %) [:response :usd]) requests))
     :provider-ids (vec (keep #(get-in (val %) [:response :provider-id]) requests))
     :unknown (count (remove #(= :complete (:status (val %))) requests))}))

;; ---------------------------------------------------------------------------------------
;; 2. Exact-reuse memo in a task worker (arm C)

(defn context-keys
  "Exact item texts a record of this context can have: each line, and each ' || ' field
  without a leading 'Name: ' label, trimmed. Public input only."
  [context]
  (into #{} (comp (mapcat (fn [line] (cons line (map #(str/replace-first % #"^[A-Za-z][A-Za-z ]{0,30}: " "")
                                                     (str/split line #" \|\| ")))))
                  (map str/trim) (remove str/blank?))
        (str/split-lines context)))

(defn memo-hits [memo context]
  (into (sorted-map) (keep (fn [k] (when-let [label (get (:entries memo) (memo-key k))] [k label]))) (context-keys context)))

(defn memo-chunks
  "Worker sources that define aljure-exact with the hits, each request below the wire bound."
  [hits]
  (let [chunks (reduce (fn [chunks [k v]]
                         (let [current (peek chunks) size (+ (count (.getBytes (pr-str [k v]) "UTF-8")) 2)]
                           (if (and (seq (:items current)) (> (+ (:bytes current) size) 40000))
                             (conj chunks {:items {k v} :bytes size})
                             (conj (pop chunks) {:items (assoc (:items current) k v) :bytes (+ (:bytes current) size)}))))
                       [{:items {} :bytes 0}] hits)]
    (into [["(do (def aljure-exact {}) nil)" {}]]
          (for [{:keys [items]} chunks :when (seq items)]
            ["(do (def aljure-exact (merge aljure-exact aljure-chunk)) nil)" {:aljure-chunk items}]))))

(defn exact-label-function []
  {:name exact-label-name :arity 1 :hash nil :code-hash (a/forms-code-hash exact-label-form) :role :export
   :source (printed exact-label-form) :summary "Labels assigned earlier to records with exactly this text (trimmed); nil otherwise."})

;; ---------------------------------------------------------------------------------------
;; 3. Development panel (controller-only) and the preregistered rule

(defn load-panel
  "The panel bytes must hash to the pin the plan froze. Items keep gold on the controller."
  [path sha]
  (let [text (slurp path)]
    (u/ensure! (= sha (u/sha text)) "Development panel changed after plan freeze" {})
    (let [panel (u/json-read text)]
      (u/ensure! (and (= "aljure-panel-v1" (:schema panel)) (vector? (:windows panel)) (seq (:windows panel))
                      (every? #(and (string? (:id %)) (string? (:question %)) (string? (:context %)) (vector? (:items %))
                                    (seq (:items %))
                                    (every? (fn [i] (and (string? (:case i)) (string? (:text i)) (string? (:label i)))) (:items %)))
                              (:windows panel))
                      (apply distinct? (mapcat #(map :case (:items %)) (:windows panel))))
                 "Invalid development panel" {})
      (assoc panel :sha256 sha))))

(defn label-source [name]
  (str "(mapv (fn [aljure-t] (let [aljure-v (" name " aljure-t)] "
       "(if (or (nil? aljure-v) (and (string? aljure-v) (<= (count aljure-v) 64))) aljure-v :aljure/not-a-label))) "
       "aljure-items)"))

(defn- pages [texts]
  (reduce (fn [pages text]
            (let [current (peek pages) size (+ 4 (count (.getBytes (pr-str text) "UTF-8")))]
              (if (and (seq current) (or (> (+ (reduce + (map #(+ 4 (count (.getBytes (pr-str %) "UTF-8"))) current)) size) 40000)
                                         (>= (count current) 400)))
                (conj pages [text])
                (conj (pop pages) (conj current text)))))
          [[]] texts))

(defn label-items!
  "One label (a string of at most 64 characters, nil, or :aljure/not-a-label) per item."
  [backend worker name texts]
  (u/ensure! (re-matches name-re name) "Invalid function name" {})
  (vec (mapcat (fn [page]
                 (when (seq page)
                   (let [labels (execution/evaluate! backend worker (label-source name) {:aljure-items page})]
                     (u/ensure! (and (vector? labels) (= (count page) (count labels))
                                     (every? #(or (nil? %) (= :aljure/not-a-label %) (and (string? %) (<= (count %) 64))) labels))
                                "Malformed label page" {})
                     labels)))
               (pages texts))))

(defn panel-run!
  "The given entries on every panel window in one fresh isolated worker; no model call. Each
  window's public text is bound as in a task; the entry's predicate decides admission; an
  admitted entry labels the window's items. Entries load just before they run, so each
  sees its own dependency closure."
  [backend initialize panel entries deadline]
  (let [worker (execution/open! backend deadline)]
    (try
      (reduce
        (fn [acc window]
          ((initialize (:context window)) backend worker)
          (reduce (fn [acc {:keys [key function dependencies predicate]}]
                    (assoc-in acc [key (:id window)]
                      (let [check (executable/applicability! backend worker predicate {:question (:question window)})]
                        (if (not= :preload (:decision check))
                          {:admitted false :reason (:reason check)}
                          (try (executable/load! backend worker function dependencies)
                               {:admitted true :labels (label-items! backend worker (get-in function [:interface :name])
                                                                     (mapv :text (:items window)))}
                               (catch Exception e {:admitted true :error (let [m (str (.getMessage e))] (subs m 0 (min 300 (count m))))}))))))
                  acc entries))
        {} (:windows panel))
      (finally (execution/close! backend worker)))))

(defn- entry-labels
  "case -> label or nil for one entry; nil where its predicate refused."
  [panel results key]
  (into {} (for [window (:windows panel) :let [r (get-in results [key (:id window)])]
                 [i item] (map-indexed vector (:items window))]
             [(:case item) (when (and (:admitted r) (:labels r)) (nth (:labels r) i))])))

(defn- counts [panel labels cases]
  (let [gold (into {} (for [w (:windows panel) i (:items w)] [(:case i) (:label i)]))
        decided (filter #(string? (labels %)) cases)]
    {:items (count cases) :decided (count decided) :correct (count (filter #(= (labels %) (gold %)) decided))}))

(defn candidate-metrics
  "The candidate alone, over the panel windows its predicate admits."
  [panel results key]
  (let [labels (entry-labels panel results key)
        admitted (filter #(get-in results [key (:id %) :admitted]) (:windows panel))
        cases (mapv :case (mapcat :items admitted))]
    (merge (counts panel labels cases)
           {:admitted-windows (mapv :id admitted)
            :errors (vec (keep #(when-let [e (get-in results [key (:id %) :error])] {:window (:id %) :error e}) (:windows panel)))
            :non-labels (count (filter #(= :aljure/not-a-label %) (vals labels)))})))

(defn cascade
  "A library version's label per case: the first approved entry, in library order, that
  its predicate admits and that decides the case."
  [panel results keys]
  (let [by-entry (mapv #(entry-labels panel results %) keys)]
    (into {} (for [w (:windows panel) i (:items w) :let [k (:case i)]]
               [k (some #(let [v (get % k)] (when (string? v) v)) by-entry)]))))

(defn library-metrics [panel results keys]
  (let [labels (cascade panel results keys)
        cases (mapv :case (mapcat :items (:windows panel)))]
    {:metrics (counts panel labels cases)
     :rows (let [gold (into {} (for [w (:windows panel) i (:items w)] [(:case i) (:label i)]))]
             (mapv (fn [k] {:case k :passed (= (labels k) (gold k))}) cases))}))

(defn check-rule! [rule]
  (u/ensure! (and (map? rule) (= "aljure-promotion-rule-v1" (name (:schema rule)))
                  (let [[pn pd] (:min_precision rule) [cn cd] (:min_coverage rule)]
                    (and (pos-int? pn) (pos-int? pd) (<= pn pd) (pos-int? cn) (pos-int? cd) (<= cn cd)))
                  (nat-int? (:min_panel_gain rule)))
             "Invalid promotion rule" {})
  rule)

(defn decide
  "The preregistered rule (research/THESIS_PILOT_PROTOCOL.md §4), in exact integer arithmetic."
  [rule candidate current proposed evidence]
  (let [[pn pd] (:min_precision rule) [cn cd] (:min_coverage rule)
        {:keys [items decided correct]} candidate
        reasons (cond-> []
                  (seq (:errors candidate)) (conj :execution-failure)
                  (pos? (:non-labels candidate)) (conj :non-label-result)
                  (empty? (:admitted-windows candidate)) (conj :no-applicable-panel-window)
                  (and (seq (:admitted-windows candidate)) (< (* decided cd) (* cn items))) (conj :coverage-below-minimum)
                  (or (zero? decided) (< (* correct pd) (* pn decided))) (conj :precision-below-minimum)
                  (< (:decided proposed) (:decided current)) (conj :library-coverage-regression)
                  (and (pos? (:decided current)) (< (* (:correct proposed) (:decided current)) (* (:correct current) (:decided proposed))))
                  (conj :library-precision-regression)
                  (not (:no-regression evidence)) (conj :item-regression)
                  (< (:score-gain evidence) (:min_panel_gain rule)) (conj :insufficient-panel-gain))]
    {:approved (empty? reasons) :reasons reasons}))

;; ---------------------------------------------------------------------------------------
;; 4. Candidates and promotion

(defn diff-path
  "The path to the smallest subtree that holds every difference between two forms, or []
  when the top level differs (a rewrite). Only same-kind, same-length lists and vectors
  are descended."
  [a b]
  (loop [a a b b path []]
    (if (and (sequential? a) (sequential? b) (= (seq? a) (seq? b)) (= (count a) (count b)))
      (let [differing (keep-indexed (fn [i [x y]] (when (not= x y) i)) (map vector a b))]
        (if (= 1 (count differing))
          (let [i (first differing)] (recur (nth (vec a) i) (nth (vec b) i) (conj path i)))
          path))
      path)))

(defn- model-artifact [source name arity author parent dependencies]
  (a/make-artifact {:category :analysis :source source :interface {:name name :arity arity}
                    :dependencies (vec dependencies) :author author :parent parent :provenance :model-generated}))

(defn- referenced-names [form]
  (set (map str (filter symbol? (tree-seq coll? seq form)))))

(defn build-candidate
  "Arm E: the candidate artifact, built as code data. A function that names approved
  library exports depends on them by exact hash (composition). With :replaces, the new
  forms are compared to the replaced function: one differing subtree becomes an
  artifact/patch of it; anything else is a rewrite whose :parent is the replaced artifact."
  [root found proposal author]
  (let [forms (u/read-edn (:function-source proposal))
        exports (into {} (for [e (:approved found) f (conj (vec (:dependencies e)) (:function e))]
                           [(get-in f [:interface :name]) f]))
        base (when-let [n (:replaces proposal)]
               (or (some #(when (= n (get-in % [:function :interface :name])) %) (:approved found))
                   (u/fail "replaces names no approved function in this library" {:replaces n})))
        dependencies (vec (sort (for [n (referenced-names forms) :let [f (exports n)]
                                      :when (and f (not= n (:name proposal)))] (:hash f))))
        name (:name proposal)]
    (if-not base
      {:change :new :artifact (model-artifact (:function-source proposal) name 1 author nil dependencies)}
      (let [function (:function base) path (diff-path (:forms function) forms)]
        (if (and (seq path) (= (get-in function [:interface :name]) name))
          (let [patched (a/patch function {:base-hash (:hash function) :path path
                                           :expected-hash (u/hash-value (a/subtree (:forms function) path))
                                           :replacement (a/subtree forms path) :author author
                                           :dependencies dependencies :provenance :model-generated})]
            (u/ensure! (= (a/code-hash patched) (a/forms-code-hash forms)) "Patch differs from the proposed forms" {})
            {:change :patch :path path :replaced (:artifact base) :artifact patched})
          {:change :rewrite :replaced (:artifact base)
           :artifact (model-artifact (:function-source proposal) name 1 author (:hash function) dependencies)})))))

(defn structural-reasons
  "Checks the task path would also apply (executable/preload-plan): reserved names, name
  conflicts with other approved functions, the 16-function limit."
  [root found candidate replaced]
  (let [closure (conj (a/dependency-closure root candidate) candidate)
        others (remove #(= replaced (:artifact %)) (:approved found))
        taken (into {} (for [e others f (conj (vec (:dependencies e)) (:function e))]
                         [(get-in f [:interface :name]) (a/code-hash f)]))
        reserved (executable/reserved-names)
        names (map #(get-in % [:interface :name]) closure)]
    (cond-> []
      (some #(or (reserved %) (str/starts-with? % "aljure-") (= exact-label-name %)) names) (conj :reserved-name)
      (some (fn [f] (let [h (taken (get-in f [:interface :name]))] (and h (not= h (a/code-hash f))))) closure) (conj :name-conflict)
      (> (count (distinct (concat (keys taken) names))) executable/max-preloaded) (conj :limit))))

(defn- entry-for [function predicate status summary receipt]
  (cond-> {:artifact (:hash function) :code-hash (a/code-hash function)
           :applicability (:hash predicate) :applicability-code-hash (a/code-hash predicate)
           :status status :receipt receipt}
    summary (assoc :summary summary)))

(defn- write-receipt! [root receipt]
  (let [text (str (u/json-str (u/canonical receipt)) "\n") sha (u/sha text)
        path (str (io/file root "receipts" (str sha ".json")))]
    (when-not (.exists (io/file path)) (u/atomic-write! path text))
    {:receipt-sha256 sha :receipt-path path}))

(defn- exact-question-predicate [question]
  (a/make-artifact {:category :analysis :source (printed (list 'fn '[input] (list '= '(:question input) question)))
                    :interface {:name "applicable" :arity 1} :dependencies [] :author "controller"
                    :parent nil :provenance :controller-generated}))

(defn- promote-c! [{:keys [root pin proposal task-id position]} library base-receipt]
  (let [function (when-let [source (:function-source proposal)]
                   (let [forms (u/read-edn source)]
                     (model-artifact source (:name proposal) (count (second forms)) task-id nil [])))
        predicate (when function (exact-question-predicate (:question proposal)))
        old-memo (if (:memo library) (:entries (skills/load-memo root (:memo library))) {})
        added (into {} (remove #(contains? old-memo (key %)) (:memo proposal)))
        conflicts (count (filter #(and (contains? old-memo (key %)) (not= (old-memo (key %)) (val %))) (:memo proposal)))
        memo (merge old-memo added)
        provenance {:task task-id :position position :proposal-sha256 (:proposal-sha256 base-receipt) :decision :approved
                    :validation :none-exact-reuse}]
    (when function (a/save! root function) (a/save! root predicate))
    (*crash-hook* :after-artifacts)
    (if (and (nil? function) (empty? added))
      (assoc base-receipt :decision :unchanged :reasons [:nothing-new] :pin-after pin)
      (let [memo-sha (when (seq memo) (skills/write-memo! root {:schema :aljure-memo-v1 :entries memo}))
            sha (skills/write-library! root (cond-> {:schema :aljure-library-v1 :parent pin
                                                      :entries (cond-> (vec (:entries library))
                                                                 function (conj (entry-for function predicate :approved (:description proposal) provenance)))}
                                              memo-sha (assoc :memo memo-sha)))]
        (*crash-hook* :after-version-write)
        (merge base-receipt
               {:decision :approved :reasons [] :pin-after sha :memo-sha256 memo-sha
                :memo {:proposed (count (:memo proposal)) :added (count added) :conflicts-kept-earlier conflicts :total (count memo)}}
               (when function {:candidate {:artifact (:hash function) :code-hash (a/code-hash function)
                                           :applicability (:hash predicate) :applicability-code-hash (a/code-hash predicate)
                                           :name (:name proposal) :key :exact-question}}))))))

(defn- promote-e! [{:keys [root pin proposal panel rule task-id position backend initialize deadline]} library base-receipt]
  (let [found (skills/discover root pin)
        {:keys [artifact change path replaced]} (build-candidate root found proposal task-id)
        predicate (model-artifact (:applicability-source proposal) "applicable" 1 task-id nil [])
        _ (doseq [x [artifact predicate]] (a/save! root x))
        _ (*crash-hook* :after-artifacts)
        candidate {:artifact (:hash artifact) :code-hash (a/code-hash artifact) :applicability (:hash predicate)
                   :applicability-code-hash (a/code-hash predicate) :name (:name proposal) :change change
                   :dependencies (:dependencies artifact) :parent (:parent artifact)}
        candidate (cond-> candidate path (assoc :patch-path path) replaced (assoc :replaces replaced))
        structural (structural-reasons root found artifact replaced)]
    (if (seq structural)
      (assoc base-receipt :decision :rejected :reasons structural :pin-after pin :candidate candidate)
      (let [current-keys (mapv :artifact (:approved found))
            entries (mapv (fn [e] {:key (:artifact e) :function (:function e) :dependencies (:dependencies e)
                                   :predicate (:predicate e)}) (:approved found))
            begin (System/nanoTime)
            ;; The candidate runs in its own fresh worker, so a candidate that stops its worker
            ;; (deadline, output bound) is rejected for itself and never fails an approved entry.
            results (merge (when (seq entries) (panel-run! backend initialize panel entries deadline))
                           (panel-run! backend initialize panel
                                       [{:key :candidate :function artifact :dependencies (a/dependency-closure root artifact)
                                         :predicate predicate}] deadline))
            validation-ms (/ (- (System/nanoTime) begin) 1e6)
            _ (doseq [k current-keys]
                (u/ensure! (every? #(nil? (:error (get-in results [k (:id %)]))) (:windows panel))
                           "An approved entry failed on the panel; promotion stopped" {:artifact k}))
            proposed-keys (let [ks (vec (remove #(= replaced %) current-keys))
                                at (if replaced (.indexOf ^java.util.List current-keys replaced) (count ks))]
                            (vec (concat (take at ks) [:candidate] (drop at ks))))
            metrics (candidate-metrics panel results :candidate)
            current (library-metrics panel results current-keys)
            proposed (library-metrics panel results proposed-keys)
            evidence (a/promotion-evidence (:rows current) (:rows proposed)
                                           {:objective :verified-cases :min-score-improvement (:min_panel_gain rule)})
            {:keys [approved reasons]} (decide rule metrics (:metrics current) (:metrics proposed) evidence)
            summary {:candidate-panel (dissoc metrics :errors) :candidate-errors (:errors metrics)
                     :library {:current (:metrics current) :proposed (:metrics proposed)}
                     :evidence (select-keys evidence [:approved :no-regression :score-gain :old :new])
                     :validation-ms validation-ms :model-calls 0}]
        (if-not approved
          (merge base-receipt summary {:decision :rejected :reasons reasons :pin-after pin :candidate candidate})
          (let [provenance {:task task-id :position position :proposal-sha256 (:proposal-sha256 base-receipt)
                            :decision :approved :change change :panel-sha256 (:sha256 panel) :rule-sha256 (u/hash-value rule)
                            :candidate-panel (select-keys metrics [:items :decided :correct])}
                new-entry (entry-for artifact predicate :approved (:description proposal) provenance)
                entries (vec (mapcat (fn [e] (if (= replaced (:artifact e)) [(assoc e :status :superseded) new-entry] [e]))
                                     (:entries library)))
                entries (if replaced entries (conj entries new-entry))
                sha (skills/write-library! root (cond-> {:schema :aljure-library-v1 :parent pin :entries entries}
                                                  (:memo library) (assoc :memo (:memo library))))]
            (*crash-hook* :after-version-write)
            (merge base-receipt summary {:decision :approved :reasons [] :pin-after sha :candidate candidate})))))))

(defn promote!
  "Validates and promotes one task's proposal against the pin that task saw. Nothing here
  calls a model. The receipt is written last; a crash before it leaves no receipt, so the
  trajectory keeps the previous pin, and any version written before the crash stays on
  disk, unreferenced, for inspection. Rejected candidates are kept (artifacts and receipt)."
  [{:keys [arm root pin proposal-path proposal-sha256 task-id position rule panel] :as request}]
  (u/ensure! (arms arm) "Unknown acquisition arm" {})
  (let [library (skills/load-library root pin)
        text (slurp proposal-path)
        _ (u/ensure! (= proposal-sha256 (u/sha text)) "Proposal changed after the task" {})
        proposal (u/read-edn text)
        _ (u/ensure! (and (= :aljure-proposal-v1 (:schema proposal)) (= arm (:arm proposal))
                          (= pin (:library-sha256 proposal)))
                     "Proposal does not belong to this pin or arm" {})
        base {:schema :aljure-promotion-receipt-v1 :arm arm :task-id task-id :position position :parent-pin pin
              :proposal-sha256 proposal-sha256 :proposal-decision (:decision proposal)
              :rule (when (= "E" arm) rule) :rule-sha256 (when (= "E" arm) (u/hash-value rule))
              :panel-sha256 (when (= "E" arm) (:sha256 panel)) :model-calls 0}
        receipt (if (not= :proposed (:decision proposal))
                  (assoc base :decision :no-proposal :reasons [(:decision proposal)] :pin-after pin)
                  (if (= "C" arm)
                    (promote-c! (assoc request :proposal proposal) library base)
                    (do (check-rule! rule) (promote-e! (assoc request :proposal proposal) library base))))
        written (write-receipt! root receipt)]
    (*crash-hook* :after-receipt)
    (merge (select-keys receipt [:decision :reasons :pin-after :parent-pin :validation-ms]) written)))

(defn restore
  "A library version read back from disk by its pin alone (bundle-only state)."
  [root pin]
  (let [library (skills/load-library root pin)]
    {:pin pin :parent (:parent library) :memo (:memo library)
     :entries (mapv (fn [e] [(:artifact e) (:status e) (a/code-hash (a/load! root (:artifact e)))
                             (a/code-hash (a/load! root (:applicability e)))])
                    (:entries library))
     :approved (mapv :code-hash (:approved (skills/discover root pin)))}))

(defn -main [& [command path & more]]
  (try
    (let [request (u/json-read (slurp path))
          value (case command
                  "promote"
                  (let [initialize-context! (requiring-resolve 'repl-lab.external-task/initialize-context!)
                        panel (when (= "E" (:arm request)) (load-panel (:panel request) (:panel_sha256 request)))
                        backend (when (= "E" (:arm request))
                                  ((requiring-resolve 'repl-lab.isolation/require-tested!))
                                  (execution/backend :clojure))]
                    (promote! {:arm (:arm request) :root (:library request) :pin (:pin request)
                               :proposal-path (:proposal request) :proposal-sha256 (:proposal_sha256 request)
                               :task-id (:task_id request) :position (:position request) :rule (:rule request)
                               :panel panel :backend backend
                               :deadline (+ (System/currentTimeMillis) (* 1000 (or (:seconds request) 600)))
                               :initialize (fn [context] (fn [backend worker]
                                                           (initialize-context! context (boolean (:assisted request))
                                                                                (boolean (:structured_labels request)) backend worker)))}))
                  "restore" (restore (:library request) (:pin request))
                  (u/fail "Unknown acquisition command" {}))]
      (println (u/json-str value))
      (shutdown-agents)
      (System/exit 0))
    (catch Exception e
      (println (u/json-str {:error (str (.getMessage e))}))
      (shutdown-agents)
      (System/exit 2))))
