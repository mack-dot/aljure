(ns repl-lab.program-library
  "Orchestration programs as code-as-data artifacts (research/PROGRAMMATIC_EXECUTION.md, Phase 3).
  A program artifact is an immutable (fn [...] ...) of category :program that declares the tool
  capabilities it needs. Its identity is the envelope hash (artifact/make-artifact) and its exact
  code identity the code hash; its validation (cases on service fixtures, run through the real
  bridge) and its execution context (the grant, the session) are separate records that name it.
  Nothing here promotes anything: a validated program is a candidate until the frozen rule and
  the library version machinery (skills/add-entry!) record a receipt. Capture reads recorded
  program sources and never evaluates them; every reason it finds quarantines the candidate."
  (:require [clojure.string :as str] [clojure.walk :as walk] [repl-lab.util :as u] [repl-lab.artifact :as a]
            [repl-lab.capture :as capture] [repl-lab.programs :as programs] [repl-lab.service-fixture :as service]
            [repl-lab.model-protocol :as wire] [repl-lab.controller :as c]))

;; ---- identity --------------------------------------------------------------------------------

(defn- tool-names
  "The tool names a form asks for: the string in every (tool \"name\" ...) call. A call whose
  name is not a literal string is reported as :dynamic, which capture refuses."
  [form]
  (let [calls (filter #(and (seq? %) (= 'tool (first %))) (tree-seq coll? seq form))]
    {:names (vec (distinct (keep #(when (string? (second %)) (second %)) calls)))
     :dynamic (count (remove #(string? (second %)) calls))}))

(defn make-program
  "A program artifact from source: (fn [args...] body). Its capabilities are exactly the tool
  names the body asks for, so a program cannot claim less than it uses or use more than it claims;
  each must be a known bridge tool."
  [{:keys [source name author provenance parent dependencies]}]
  (let [forms (a/parse-source source :clojure :program)
        {:keys [names dynamic]} (tool-names forms)]
    (u/ensure! (and (seq? forms) (= 'fn (first forms)) (vector? (second forms))) "A program is one (fn [...] ...) form" {})
    (u/ensure! (zero? dynamic) "Every tool call names its tool with a literal string" {})
    (u/ensure! (seq names) "A program performs at least one tool call" {})
    (u/ensure! (every? programs/tools names) (str "Unknown tools: " (pr-str (remove programs/tools names))) {})
    (a/make-artifact {:category :program :source source :interface {:name name :arity (count (second forms))}
                      :dependencies (or dependencies []) :author author :parent parent :provenance provenance
                      :capabilities (vec (sort names))})))

(defn requires-within?
  "Whether a grant covers every capability a program declares."
  [program grant]
  (every? (set (keys (:tools grant))) (:capabilities program)))

;; ---- validation: cases on fixtures, through the real bridge ----------------------------------

(defn- normalize-state [collections]
  (into (sorted-map) (for [[n rows] collections] [n (into (sorted-map) rows)])))

(defn validate!
  "Runs the program on development cases, each in a fresh service seeded from its fixture, and
  returns rows {:case :passed :value-ok :state-ok :ops :effects :error}. A case passes when the
  value equals :expected and the final collections equal :expected-state (when given), and no
  operation named a tool outside the program's capabilities. Expected values stay here; the
  program sees only its arguments and the service. run is (fn [source bindings tools handler])
  over an open worker; grant is the plan's; every operation is recorded on the store given."
  [{:keys [store run-id grant]} program cases run]
  (u/ensure! (and (vector? cases) (seq cases) (apply distinct? (map :case cases))
                  (every? #(and (string? (:case %)) (map? (:fixture %)) (vector? (:arguments %)) (contains? % :expected)) cases))
             "Validation needs distinct cases with a fixture, arguments and an expected value" {})
  (u/ensure! (requires-within? program grant) "The grant does not cover the program's capabilities" {})
  (a/verify program)
  (let [name (get-in program [:interface :name])
        source (str "(do (def " name " " (:source program) ") nil)")]
    (run source {} nil nil)
    (vec (for [{:keys [case fixture arguments expected expected-state]} cases]
           (let [svc (service/open fixture)
                 env {:store store :run run-id :programs {:grant grant :state (programs/state) :service svc}}
                 before (count (:events (c/get-run store run-id)))
                 outcome (try {:value (programs/run-program! env (str "validate/" case) (str "(apply " name " arguments)")
                                                            {:arguments arguments} run)}
                              (catch Exception e {:error (.getMessage e)}))
                 ops (filter #(and (= :program-op (:type %)) (= (str "validate/" case "/program-1") (get-in % [:payload :origin])))
                             (drop before (:events (c/get-run store run-id))))
                 outside (remove (set (:capabilities program)) (map #(get-in % [:payload :name]) ops))
                 value-ok (and (not (:error outcome)) (= expected (:value outcome)))
                 state-ok (or (nil? expected-state) (= (normalize-state expected-state) (normalize-state (service/collections svc))))]
             (cond-> {:case case :passed (boolean (and value-ok state-ok (empty? outside)))
                      :value-ok (boolean value-ok) :state-ok (boolean state-ok) :ops (count ops)
                      :effects (count (filter #(= :effect (get-in % [:payload :class])) ops))}
               (seq outside) (assoc :outside-capabilities (vec (distinct outside)))
               (:error outcome) (assoc :error (:error outcome))))))))

;; ---- the frozen rule for programs -------------------------------------------------------------

(def rule
  "program-rule-v1: every case passes, on at least two distinct fixtures. A program is never
  promoted on one fixture, which it could have memorized."
  {:name "program-rule-v1" :min-cases 2 :min-distinct-fixtures 2 :statement "all cases pass on >= 2 distinct fixtures"})

(defn decide
  "The decision for validation rows against the cases they came from."
  [rows cases]
  (let [fixtures (count (distinct (map #(u/hash-value (:fixture %)) cases)))
        passed (count (filter :passed rows))]
    {:approved (and (= (count rows) (count cases)) (= passed (count rows))
                    (>= (count rows) (:min-cases rule)) (>= fixtures (:min-distinct-fixtures rule)))
     :passed passed :cases (count rows) :distinct-fixtures fixtures :rule rule}))

;; ---- capture: recorded program sources, read and never run ---------------------------------------

(defn candidates
  "Program candidates from a session's recorded program_run sources, one per distinct form.
  A candidate's reasons quarantine it: :session-data (it reads the task's bindings), :unresolved
  (a free symbol that is neither core, prelude nor tool), :literal-data-set, :embedded-task-data
  (a string literal equal to a record id of this task's fixture, a hardcoded answer), :dynamic-tool,
  :too-large. A candidate is a (fn [] body) over the recorded form; its arguments are what the
  controller or a later adaptation parameterizes (parameterize)."
  [sources fixture-ids]
  (let [ids (set fixture-ids)]
    (->> (map-indexed vector sources)
         (keep (fn [[i source]]
                 (let [forms (try (wire/read-forms source) (catch Exception _ nil))]
                   (when (seq forms)
                     (let [body (if (= 1 (count forms)) (first forms) (cons 'do forms))
                           form (capture/plain-gensyms (list 'fn [] body))
                           free (disj (capture/free-symbols form) 'tool)
                           {:keys [names dynamic]} (tool-names form)
                           literals (filter string? (tree-seq coll? seq form))
                           text (capture/printed form)
                           reasons (cond-> []
                                     (some capture/data-symbols free) (conj [:session-data (str (first (filter capture/data-symbols free)))])
                                     (seq (remove capture/data-symbols free)) (into (map #(vector :unresolved (str %)) (sort (remove capture/data-symbols free))))
                                     (some ids literals) (conj [:embedded-task-data (first (filter ids literals))])
                                     (pos? dynamic) (conj [:dynamic-tool])
                                     (empty? names) (conj [:no-tool-call])
                                     (< capture/max-candidate-bytes (count (.getBytes ^String text "UTF-8"))) (conj [:too-large]))]
                       {:index i :source-sha256 (u/sha source) :form-sha256 (u/sha text) :source text
                        :capabilities (vec (sort names)) :reasons reasons})))))
         reverse (reduce (fn [[seen out] c] (if (seen (:source c)) [seen out] [(conj seen (:source c)) (conj out c)])) [#{} []])
         second reverse
         (map-indexed (fn [k c] (assoc c :id (str "p" (inc k)))))
         vec)))

;; ---- structural adaptation: parameterize a literal ---------------------------------------------

(defn parameterize
  "A new program whose parameter list grows by one and whose subtree at path (a literal value in
  the parent, pinned by its hash) is replaced by that parameter. The transformation is on code
  data: no text is rewritten, the parent is pinned, and the result is only a candidate."
  [parent {:keys [path expected-hash parameter author provenance]}]
  (a/verify parent)
  (u/ensure! (= :program (:category parent)) "Only programs are parameterized" {})
  (u/ensure! (and (symbol? parameter) (not (some #{parameter} (second (:forms parent))))) "A new parameter symbol" {})
  (let [target (a/subtree (:forms parent) path)]
    (u/ensure! (= expected-hash (u/hash-value target)) "Ambiguous or changed target" {})
    (u/ensure! (not (coll? target)) "Parameterize a literal value, not a form" {})
    (let [forms (a/replace-subtree (:forms parent) path parameter)
          forms (apply list 'fn (conj (second forms) parameter) (drop 2 forms))]
      (make-program {:source (capture/printed forms) :name (get-in parent [:interface :name])
                     :author author :provenance provenance :parent (:hash parent) :dependencies (:dependencies parent)}))))
