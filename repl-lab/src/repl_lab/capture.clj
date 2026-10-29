(ns repl-lab.capture
  "Controller-assisted capture (mechanism C of research/UNBLOCK_ACQUISITION.md). The controller
  reads, and never evaluates, the root session's recorded repl/eval sources and finds the
  one-argument functions the model defined during ordinary work: defn, (def name (fn ...)) and
  let-bound (fn ...). A candidate keeps its recorded forms verbatim; the session definitions and
  earlier bindings of the same let that it calls are inlined, also verbatim. Session data (the
  context, its lines, anything that reads them) and literal record or index sets disqualify a
  candidate, so temporary state and hardcoded answers are never captured. Nothing here decides
  promotion: a chosen candidate is validated like any other proposal."
  (:require [clojure.string :as str] [clojure.walk] [repl-lab.util :as u] [repl-lab.model-protocol :as wire]))

(def data-symbols
  "Worker bindings that hold this task's input or results; a candidate that reads them is task state."
  '#{external-context context-lines library-labels last-result full-result})

(def ^:private special '#{if do let* fn* quote var def loop* recur throw try catch finally new set! . letfn* case* & import})
(def ^:private namespaces #{"clojure.string" "clojure.set" "clojure.walk"})
(def ^:private binders '#{let let* loop loop* for doseq binding dotimes when-let if-let when-some if-some with-open})
(def ^:private fns '#{fn fn*})
(def max-candidate-bytes 16384)

(defn plain-gensyms
  "The reader expands #(...) into (fn* [p1__123#] ...). The artifact store's EDN reader refuses
  the trailing #, and an exported function must be an (fn ...) form. Each such parameter becomes
  arg__1, arg__2, ... in order of first appearance, consistently within the form, and fn* in head
  position becomes fn, which means the same; nothing else changes."
  [form]
  (let [found (distinct (filter #(and (symbol? %) (str/ends-with? (name %) "#")) (tree-seq coll? seq form)))
        renames (zipmap found (map #(symbol (str "arg__" %)) (iterate inc 1)))]
    (clojure.walk/postwalk #(cond (and (symbol? %) (renames %)) (renames %)
                                  (and (seq? %) (= 'fn* (first %))) (cons 'fn (rest %))
                                  :else %)
                           form)))

(defn printed
  "Forms as code text (the same printing as acquisition/printed, which requires this namespace)."
  [form]
  (binding [*print-namespace-maps* false *print-meta* false *print-length* nil *print-level* nil
            *print-readably* true *print-dup* false]
    (pr-str form)))

(def ^:private prelude
  "Helpers every assisted worker defines (resources/sci-prelude.edn), so a candidate may call them."
  (delay (set (for [form (rest (first (wire/read-forms (slurp "resources/sci-prelude.edn"))))
                    :when (and (seq? form) (= 'def (first form)))]
                (second form)))))

(defn- symbols-in [form] (filter symbol? (tree-seq coll? seq form)))

(defn- binding-names
  "Symbols a binding vector introduces, destructuring included; for/doseq :let and :when handled."
  [bindings]
  (loop [[lhs rhs & more] bindings names #{}]
    (cond (nil? lhs) names
          (= :let lhs) (recur more (into names (binding-names rhs)))
          (keyword? lhs) (recur more names)
          :else (recur more (into names (symbols-in lhs))))))

(defn- local-names
  "Every symbol any binding form inside form introduces (an over-approximation: a name bound in
  one branch counts everywhere). Over-approximating only hides a free symbol, which then fails
  validation in the worker; it never admits session data."
  [form]
  (reduce (fn [names f]
            (if-not (seq? f)
              names
              (let [[head a b] f]
                (cond (and (binders head) (vector? a)) (into names (binding-names a))
                      (fns head) (let [arities (cond (vector? a) [a] (vector? b) [b]
                                                     :else (keep #(when (and (seq? %) (vector? (first %))) (first %)) (rest f)))]
                                   (cond-> (into names (mapcat symbols-in arities)) (symbol? a) (conj a)))
                      (= 'letfn head) (into names (mapcat #(cons (first %) (symbols-in (second %))) a))
                      :else names))))
          #{} (tree-seq coll? seq form)))

(defn free-symbols
  "Unqualified symbols form uses that are not local, not clojure.core, not a prelude helper and
  not special; qualified ones outside clojure.string/set/walk."
  [form]
  (let [core (set (keys (ns-publics 'clojure.core))) local (local-names form)]
    (set (for [s (symbols-in form)
               :let [ns (namespace s)]
               :when (if ns
                       (not (namespaces ns))
                       (not (or (local s) (core s) (special s) (@prelude s) (str/starts-with? (name s) "."))))]
           s))))

(defn- fn-form
  "The (fn [x] ...) of a one-argument defn or fn form, or nil."
  [form]
  (when (seq? form)
    (let [[head & more] form]
      (cond (fns head) (let [[a b] more params (if (vector? a) a (when (vector? b) b))]
                         (when (= 1 (count params)) form))
            (= 'defn head) (let [body (drop-while #(or (string? %) (map? %)) (rest more))]
                             (when (and (vector? (first body)) (= 1 (count (first body))))
                               (list* 'fn (first body) (rest body))))))))

(defn- literal-data-set?
  "A literal collection of many numbers or many strings: an index set or a list of record texts."
  [form]
  (let [leaves (remove coll? (tree-seq coll? seq form))]
    (and (coll? form) (not (seq? form))
         (or (< 20 (count (filter number? leaves))) (< 50 (count (filter string? leaves)))))))

(defn session-definitions
  "name -> {:form :index} for top-level def and defn forms (inside do too), latest first-class
  definition winning, in source order."
  [sources]
  (reduce (fn [defs [i source]]
            (reduce (fn [defs form]
                      (if (and (seq? form) (#{'def 'defn} (first form)) (symbol? (second form)))
                        (assoc defs (second form) {:form (if (= 'defn (first form)) (or (fn-form form) form) (last form)) :index i})
                        defs))
                    defs
                    (mapcat #(if (and (seq? %) (= 'do (first %))) (rest %) [%])
                            (try (wire/read-forms source) (catch Exception _ [])))))
          {} (map-indexed vector sources)))

(def ^:private predicate-heads '#{filter filterv remove some every? not-any? group-by})
(def ^:private text-tests
  "A record classifier tests text; a candidate that calls none of these is a helper, not a classifier."
  '#{re-find re-matches re-seq re-pattern clojure.string/includes? clojure.string/starts-with?
     clojure.string/ends-with? clojure.string/lower-case clojure.string/upper-case .toLowerCase .contains})

(defn- regex-form? [v]
  (or (instance? java.util.regex.Pattern v) (and (seq? v) (= 're-pattern (first v)) (string? (second v)))))

(defn- regex-detector
  "A named pattern, used as the model used it: (fn [text] (re-find pattern text)). The wrapper is
  controller-generated (adapter regex-detector-v1); the pattern is the model's, verbatim."
  [pattern]
  (list 'fn '[text] (list 're-find pattern 'text)))

(defn- scoped-candidates
  "One-argument fns and named patterns inside form, each with the earlier bindings of every
  enclosing let in scope: let-bound fns, let-bound patterns, and anonymous predicates passed to
  filter, remove, keep, some, every?, not-any? or group-by."
  [form scope]
  (cond
    (and (seq? form) ('#{let let*} (first form)) (vector? (second form)))
    (let [[found scope] (reduce (fn [[found scope] [sym value]]
                                  (let [here (when (symbol? sym)
                                               (cond (fn-form value) [{:name sym :form (fn-form value) :scope scope :kind :function}]
                                                     (regex-form? value) [{:name sym :form (regex-detector value) :scope scope :kind :regex}]))]
                                    [(-> found (into here) (into (scoped-candidates value scope)))
                                     (cond-> scope (symbol? sym) (assoc sym {:form value}))]))
                                [[] scope] (partition 2 (second form)))]
      (into found (mapcat #(scoped-candidates % scope) (drop 2 form))))
    (and (seq? form) (predicate-heads (first form)) (fn-form (second form)))
    (into [{:name nil :form (fn-form (second form)) :scope scope :kind :function}]
          (mapcat #(scoped-candidates % scope) (rest form)))
    (map? form) (vec (mapcat #(scoped-candidates % scope) (mapcat identity form)))
    (coll? form) (vec (mapcat #(scoped-candidates % scope) form))
    :else []))

(defn- closure
  "Dependencies of form in order (dependencies before users), or the reasons it is ineligible."
  [form scope defs]
  (loop [todo (vec (free-symbols form)) seen #{} order [] reasons []]
    (if-let [s (first todo)]
      (cond (seen s) (recur (subvec todo 1) seen order reasons)
            (data-symbols s) (recur (subvec todo 1) (conj seen s) order (conj reasons [:session-data s]))
            :else (if-let [{dep :form} (or (scope s) (defs s))]
                    (recur (into (subvec todo 1) (free-symbols dep)) (conj seen s) (conj order [s dep])
                           (cond-> reasons (literal-data-set? dep) (conj [:literal-data-set s])))
                    (recur (subvec todo 1) (conj seen s) order (conj reasons [:unresolved s]))))
      {:dependencies (vec (distinct (reverse order))) :reasons (vec (distinct reasons))})))

(defn candidates
  "Capture candidates from the root session's repl/eval sources, in source order, one per
  distinct portable form (the latest recording kept). Eligible candidates have no reasons."
  [sources]
  (let [defs (session-definitions sources)
        found (for [[i source] (map-indexed vector sources)
                    :let [forms (try (wire/read-forms source) (catch Exception _ []))]
                    c (concat (for [form forms
                                    f (if (and (seq? form) (= 'do (first form))) (rest form) [form])
                                    :let [def? (and (seq? f) (#{'def 'defn} (first f)) (symbol? (second f)))
                                          fnf (when def? (if (= 'defn (first f)) (fn-form f) (fn-form (last f))))
                                          pattern (when (and def? (= 'def (first f)) (regex-form? (last f))) (last f))]
                                    :when (or fnf pattern)]
                                (if fnf
                                  {:name (second f) :form fnf :scope {} :kind :function}
                                  {:name (second f) :form (regex-detector pattern) :scope {} :kind :regex}))
                              (mapcat #(scoped-candidates % {}) forms))]
                (assoc c :index i :source-sha256 (u/sha source)))
        built (for [{:keys [name form scope index source-sha256 kind]} found
                    :let [{:keys [dependencies reasons]} (closure form scope (dissoc defs name))
                          form (plain-gensyms form)
                          dependencies (mapv (fn [[s d]] [s (plain-gensyms d)]) dependencies)
                          [_ params & body] form
                          portable (if (seq dependencies)
                                     (list 'fn params (list* 'let (vec (mapcat identity dependencies)) body))
                                     form)
                          text (printed portable)
                          reasons (cond-> reasons
                                    (< max-candidate-bytes (count (.getBytes ^String text "UTF-8"))) (conj [:too-large])
                                    (not-any? text-tests (filter symbol? (tree-seq coll? seq portable))) (conj [:not-a-text-test]))]]
                {:name (if name (str name) "anonymous") :kind kind :index index :source-sha256 source-sha256
                 :form-sha256 (u/sha (printed form)) :adapter (when (= :regex kind) "regex-detector-v1")
                 :dependencies (mapv (comp str first) dependencies) :source text
                 :reasons (mapv (fn [[r s]] (if s [r (str s)] [r])) reasons)})]
    (->> (reverse built)
         (reduce (fn [[seen out] c] (if (seen (:source c)) [seen out] [(conj seen (:source c)) (conj out c)])) [#{} []])
         second reverse
         (map-indexed (fn [k c] (assoc c :id (str "c" (inc k)))))
         vec)))

(defn adapted-source
  "The function a chosen candidate becomes. A candidate that returns true or false for one label
  is wrapped so it returns that label (the model names it) or nil; otherwise it is kept as is.
  The wrapper is controller-generated; the candidate's forms inside it are the model's."
  [candidate label]
  (if label
    (printed (list 'fn '[text] (list 'when (list (first (wire/read-forms (:source candidate))) 'text) label)))
    (:source candidate)))
