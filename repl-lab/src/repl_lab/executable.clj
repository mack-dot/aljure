(ns repl-lab.executable
  "Load and call immutable exported functions through the selected worker backend."
  (:require [clojure.string :as str] [repl-lab.artifact :as artifact] [repl-lab.execution :as execution]
            [repl-lab.util :as u] [repl-lab.python-source :as python]))

(defn load! [backend worker target dependencies]
  (doseq [item (conj (vec dependencies) target)]
    (artifact/verify item)
    (u/ensure! (= (artifact/language target) (artifact/language item)) "Mixed executable languages" {})
    (u/ensure! (#{:analysis :policy :program} (:category item)) "Executable function required" {})
    (execution/evaluate! backend worker
      (case (artifact/language item)
        :clojure (str "(do (def " (get-in item [:interface :name]) " " (:source item) ") nil)")
        :python (:source item)) {})))

(defn call! [backend worker target arguments]
  (u/ensure! (and (vector? arguments) (= (count arguments) (get-in target [:interface :arity]))) "Export arity mismatch" {})
  (let [name (get-in target [:interface :name])]
    (execution/evaluate! backend worker
      (case (artifact/language target) :clojure (str "(apply " name " arguments)") :python (str name "(*arguments)"))
      {:arguments arguments})))

(defn invoke!
  "One call of a verified artifact in a fresh isolated worker. The optional initialize
  (external-task/initialize-context!) gives that worker the same context binding and
  assisted helpers as the session's workers, under which the artifact was validated."
  ([registry target arguments deadline] (invoke! registry target arguments deadline nil))
  ([registry target arguments deadline initialize]
   (binding [python/*deadline-ms* deadline]
   (let [dependencies (artifact/dependency-closure registry target)
         language (artifact/language target) _ (execution/require-tested! language)
         backend (execution/backend language) worker (execution/open! backend deadline)]
     (try
       (when initialize (initialize backend worker))
       (load! backend worker target dependencies)
       (call! backend worker target arguments)
       (finally (execution/close! backend worker)))))))

(defn validate!
  "Development cases for a candidate, in a fresh isolated worker. Expected values stay on
  the controller: the rows hold only case ids and pass/fail, the :verified-cases input of
  artifact/promotion-evidence. No model call is made."
  ([target dependencies cases deadline]
   (execution/require-tested! (artifact/language target))
   (validate! (execution/backend (artifact/language target)) target dependencies cases deadline))
  ([backend target dependencies cases deadline]
   (u/ensure! (and (vector? cases) (seq cases) (apply distinct? (map :case cases))
                   (every? #(and (string? (:case %)) (vector? (:arguments %)) (contains? % :expected)) cases))
              "Validation needs distinct development cases with arguments and expected values" {})
   (let [worker (execution/open! backend deadline)]
     (try
       (let [loaded (try (load! backend worker target dependencies) true (catch Exception _ false))]
         (mapv (fn [{:keys [case arguments expected]}]
                 {:case case :passed (and loaded (try (= expected (call! backend worker target arguments))
                                                      (catch Exception _ false)))})
               cases))
       (finally (execution/close! backend worker))))))

;; Task-path preload (aljure_contract.artifacts). Everything below runs in the session's
;; isolated SCI worker; the host only reads EDN results.

(defn printed
  "The verified forms as worker source: no comments, fixed print settings."
  [artifact]
  (binding [*print-namespace-maps* false *print-meta* false *print-length* nil *print-level* nil]
    (pr-str (:forms artifact))))

(defn applicability!
  "The entry's predicate on public input only ({:question, :context}), in the session's
  worker. Anything but true refuses the entry; an error or a non-boolean is a refusal too."
  [backend worker predicate public-input]
  (let [begin (System/nanoTime)
        result (try {:value (execution/evaluate! backend worker
                              (str "(let [aljure-p " (printed predicate) " "
                                   "aljure-v (aljure-p (assoc aljure-public-input :context external-context))] "
                                   "(if (boolean? aljure-v) aljure-v :aljure/not-boolean))")
                              {:aljure-public-input public-input})}
                    (catch Exception e {:error (let [m (str (.getMessage e))] (subs m 0 (min 300 (count m))))}))]
    (merge {:elapsed-ms (/ (- (System/nanoTime) begin) 1e6)}
           (cond (:error result) {:decision :refuse :reason :predicate-error :error (:error result)}
                 (true? (:value result)) {:decision :preload :reason :applicable}
                 (false? (:value result)) {:decision :refuse :reason :inapplicable}
                 :else {:decision :refuse :reason :not-boolean}))))

(def max-preloaded 16)
(declare wrapped-source)

(defn reserved-names
  "Names a preloaded function may not take: clojure.core, the worker's own definitions
  (context binding, binding names, the assisted and verification preludes) and aljure-*."
  []
  (into (set (map name (keys (ns-publics 'clojure.core))))
        (concat ["external-context" "context-lines" "chunk" "arguments"]
                (mapcat #(map second (re-seq #"\(def ([a-z][a-z0-9-]*)" (slurp %)))
                        ["resources/sci-prelude.edn" "resources/sci-verify.edn"]))))

(defn preload-plan
  "Which applicable approved entries enter the worker, in library order. An entry is refused,
  with its reason, if its predicate refused it, its language differs, a name is reserved or
  already taken by other code, or the function limit would be exceeded."
  [checked]
  (let [reserved (reserved-names)]
    (reduce
      (fn [{:keys [functions] :as plan} {:keys [function dependencies check summary] :as entry}]
        (let [items (mapv (fn [item role] {:name (get-in item [:interface :name]) :arity (get-in item [:interface :arity])
                                           :hash (:hash item) :code-hash (artifact/code-hash item) :role role :source (printed item)})
                          (conj (vec dependencies) function) (conj (vec (repeat (count dependencies) :dependency)) :export))
              taken (into {} (map (juxt :name :code-hash) functions))
              new (remove #(= (:code-hash %) (taken (:name %))) items)
              reason (cond (= :refuse (:decision check)) (:reason check)
                           (not-every? #(= :clojure (artifact/language %)) (conj (vec dependencies) function)) :unsupported-language
                           (some #(or (reserved (:name %)) (str/starts-with? (:name %) "aljure-")) items) :reserved-name
                           (some #(contains? taken (:name %)) new) :name-conflict
                           (> (+ (count functions) (count new)) max-preloaded) :limit
                           ;; The worker's request bound (isolation/request!), after escaping.
                           (some #(> (count (.getBytes (pr-str {:source (wrapped-source %) :bindings {}}) "UTF-8")) 65535) new) :too-large)
              decision (merge {:artifact (:artifact entry) :code-hash (:code-hash entry)
                               :applicability-code-hash (:applicability-code-hash entry) :name (get-in function [:interface :name])}
                              (select-keys check [:elapsed-ms :error])
                              (if reason {:decision :refuse :reason reason} {:decision :preload :reason :applicable}))]
          (cond-> (update plan :decisions conj decision)
            (nil? reason) (update :functions into (map #(cond-> % (and summary (= :export (:role %))) (assoc :summary summary)) new)))))
      {:functions [] :decisions []} checked)))

(def ^:private invocation-log-source
  (str "(do (def aljure-invocations (atom {})) "
       "(def aljure-record-call (fn [log h] (update log h (fn [r] (update (or r {:calls 0 :returns 0 :values []}) :calls inc))))) "
       "(def aljure-record-return (fn [log h v] (update log h (fn [r] "
       "(let [r (update (or r {:calls 0 :returns 0 :values []}) :returns inc) "
       "s (when (or (string? v) (number? v) (keyword? v) (boolean? v)) (str v))] "
       "(if (and s (<= (count s) 128) (< (count (:values r)) 8) (not (some (fn [x] (= x s)) (:values r)))) "
       "(update r :values conj s) r)))))) nil)"))

(defn wrapped-source
  "Defines one approved function under its exported name. Each call is counted under the
  function's code hash, with up to 8 distinct short scalar results; the value is unchanged."
  [{:keys [name code-hash source]}]
  (str "(do (def " name " (let [aljure-f " source "] (fn [& aljure-args] "
       "(swap! aljure-invocations aljure-record-call " (pr-str code-hash) ") "
       "(let [aljure-v (apply aljure-f aljure-args)] "
       "(swap! aljure-invocations aljure-record-return " (pr-str code-hash) " aljure-v) aljure-v)))) nil)"))

(defn preload-sources [functions] (into [invocation-log-source] (map wrapped-source functions)))

(defn install!
  "Preloads the planned functions, dependencies first, into one worker."
  [backend worker functions]
  (doseq [source (preload-sources functions)] (execution/evaluate! backend worker source {})))

(def drain-source "(let [aljure-v (deref aljure-invocations)] (reset! aljure-invocations {}) aljure-v)")

(defn drain!
  "Reads and clears the worker's invocation counts. Only known code hashes and bounded
  fields are kept; anything else is reported as malformed, never trusted."
  [backend worker known]
  (try
    (let [log (execution/evaluate! backend worker drain-source {})]
      (if (and (map? log) (every? (fn [[h r]] (and (known h) (map? r) (nat-int? (:calls r)) (nat-int? (:returns r))
                                                   (vector? (:values r)) (<= (count (:values r)) 8)
                                                   (every? #(and (string? %) (<= (count %) 128)) (:values r))))
                                  log))
        {:invocations (vec (for [[h r] (sort-by key log)] (assoc (select-keys r [:calls :returns :values]) :code-hash h)))}
        {:error "Malformed invocation log"}))
    (catch Exception e {:error (str (.getMessage e))})))
