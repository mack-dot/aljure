(ns repl-lab.artifact (:require [repl-lab.util :as u] [repl-lab.store :as db]
                               [repl-lab.controller :as c] [clojure.java.io :as io]
                               [repl-lab.python-source :as python]))

(def categories #{:policy :analysis :workflow})
(def ^:dynamic *crash-hook* (fn [_] nil))
(defn language [artifact] (get artifact :language :clojure))
(defn parse-source
  ([source] (parse-source source :clojure :analysis))
  ([source lang category]
  (u/ensure! (and (string? source) (<= (count (.getBytes source "UTF-8")) 32768)) "Source limit" {})
  (u/ensure! (#{:clojure :python} lang) "Unsupported artifact language" {})
  (if (and (= lang :python) (not= category :workflow)) (python/parse! source) (u/read-edn source))))

(defn forms-source [forms lang category]
  (if (and (= lang :python) (not= category :workflow)) (python/render! forms) (pr-str forms)))

(defn python-interface? [forms interface]
  (let [exports (filter #(and (= "FunctionDef" (:node %)) (= (:name interface) (get-in % [:fields :name])))
                        (get-in forms [:fields :body]))
        args (get-in (first exports) [:fields :args :fields])]
    (and (= "Module" (:node forms)) (= 1 (count exports))
         (= (:arity interface) (+ (count (:posonlyargs args)) (count (:args args))))
         (nil? (:vararg args)) (nil? (:kwarg args)) (empty? (:kwonlyargs args))
         (empty? (:defaults args)) (empty? (:kw_defaults args)))))

(defn make-artifact [{:keys [category source interface dependencies author parent provenance] :as input}]
  (u/ensure! (categories category) "Fixed host component is not learnable" {})
  (u/ensure! (and (map? interface) (string? (:name interface))
                  (boolean (re-matches (if (= :python (language input)) #"[a-z][a-z0-9_]*" #"[a-z][a-z0-9-]*") (:name interface)))
                  (or (= category :workflow) (nat-int? (:arity interface)))
                  (vector? dependencies) (every? #(and (string? %) (boolean (re-matches #"[a-f0-9]{64}" %))) dependencies)
                  (string? author) (#{:developer-fixture :model-generated :human-edit} provenance)) "Invalid artifact metadata" {})
  (let [forms (parse-source source (language input) category)
        _ (u/ensure! (if (= category :workflow) (map? forms)
                       (if (= :python (language input)) (python-interface? forms interface)
                         (and (seq? forms) (= 'fn (first forms)) (vector? (second forms))
                              (= (:arity interface) (count (second forms)))))) "Invalid exported interface" {})
        _ (when (= category :workflow)
            (let [strategy (:strategy forms)]
              (u/ensure! (and (= #{:strategy} (set (keys forms))) (map? strategy)
                              (every? #{:policy :context :delegate} (keys strategy))
                              (some #{(:policy strategy)} dependencies)) "Invalid workflow or undeclared policy dependency" {})
              (c/validate-context-query! (:context strategy))
              (when-let [delegation (:delegate strategy)]
                (u/ensure! (and (= #{:task} (set (keys delegation))) (string? (:task delegation))
                                (<= (count (:task delegation)) 1024)) "Invalid delegation" {}))))
        body (assoc (select-keys input [:language :category :source :interface :dependencies :author :parent :provenance]) :forms forms)]
    (assoc body :hash (u/hash-value body))))
(defn verify [a]
  (u/ensure! (= (:hash a) (u/hash-value (dissoc a :hash))) "Artifact hash mismatch" {})
  (u/ensure! (= a (make-artifact a)) "Source, forms, or exported interface disagree" {}) a)
(defn path-for [root hash]
  (u/ensure! (and (string? hash) (re-matches #"[a-f0-9]{64}" hash)) "Invalid artifact hash" {})
  (str (io/file root "artifacts" (str hash ".edn"))))
(defn save! [root a]
  (verify a)
  (let [path (path-for root (:hash a))]
    (if (.exists (io/file path)) (u/ensure! (= a (verify (u/read-file path))) "Immutable artifact conflict" {})
      (u/write-edn! path a))) (:hash a))
(defn load! [root hash] (let [a (verify (u/read-file (path-for root hash)))]
                          (u/ensure! (= hash (:hash a)) "Wrong artifact file" {}) a))

(defn dependency-closure [root artifact]
  (let [seen (atom #{}) names (atom {})]
    (letfn [(visit [item stack]
              (u/ensure! (not (contains? stack (:hash item))) "Dependency cycle" {})
              (u/ensure! (= (language artifact) (language item)) "Mixed execution languages in one library" {})
              (if (contains? @seen (:hash item)) []
                (let [deps (mapcat #(visit (load! root %) (conj stack (:hash item))) (:dependencies item))
                      ;; Realize before recording this node, for deterministic topological order.
                      deps (vec deps) name (get-in item [:interface :name])]
                  (when-not (= :workflow (:category item))
                    (u/ensure! (or (nil? (get @names name)) (= (:hash item) (get @names name)))
                               "Conflicting exported dependency names" {:name name})
                    (swap! names assoc name (:hash item)))
                  (swap! seen conj (:hash item))
                  (conj deps item))))]
      (vec (butlast (visit artifact #{}))))))

(defn subtree [form path]
  (reduce (fn [node key]
            (cond (map? node) (do (u/ensure! (contains? node key) "Patch target missing" {}) (get node key))
                  (sequential? node) (do (u/ensure! (and (nat-int? key) (< key (count node))) "Invalid patch index" {}) (nth node key))
                  :else (u/fail "Patch target is not a container" {}))) form path))
(defn replace-subtree [form [key & more :as path] replacement]
  (if (empty? path) replacement
    (let [next (replace-subtree (subtree form [key]) more replacement)]
      (cond (map? form) (assoc form key next)
            (vector? form) (assoc form key next)
            (seq? form) (apply list (assoc (vec form) key next))))))
(defn patch [base {:keys [base-hash path expected-hash replacement author dependencies provenance]}]
  (verify base)
  (u/ensure! (= base-hash (:hash base)) "Stale structural patch" {})
  (u/ensure! (and (vector? path) (seq path)) "Patch requires one explicit subtree path" {})
  (u/ensure! (= expected-hash (u/hash-value (subtree (:forms base) path))) "Ambiguous or changed target" {})
  (make-artifact (-> base (dissoc :hash :forms)
                     (assoc :source (forms-source (replace-subtree (:forms base) path replacement) (language base) (:category base))
                            :parent (:hash base) :author author)
                     (cond-> dependencies (assoc :dependencies dependencies)
                             provenance (assoc :provenance provenance)))))

(defn promotion-evidence [old new config]
  (u/ensure! (and (seq old) (= (count old) (count new))) "Unpaired development panel" {})
  (doseq [[a b] (map vector old new)] (u/ensure! (= (:case a) (:case b)) "Mismatched paired case" {}))
  (if (= :verified-cases (:objective config))
    (do
      (u/ensure! (every? #(and (string? (:case %)) (boolean? (:passed %))) (concat old new))
                 "Verified-case evidence requires explicit independent outcomes" {})
      (let [no-loss? (every? (fn [[a b]] (or (not (:passed a)) (:passed b))) (map vector old new))
            gain (- (count (filter :passed new)) (count (filter :passed old)))]
        {:approved (and no-loss? (>= gain (:min-score-improvement config)))
         :no-regression no-loss? :score-gain gain :old old :new new :rule config}))
  (let [safe? (every? #(zero? (:accepted-invariant-violations %)) new)
        no-loss? (every? (fn [[a b]] (and (>= (:completed b) (:completed a))
                                          (or (nil? (:makespan a)) (and (:makespan b) (<= (:makespan b) (:makespan a)))))) (map vector old new))
        gain (- (reduce + (map :score old)) (reduce + (map :score new)))
        approved (and safe? no-loss? (>= gain (:min-score-improvement config)))]
    {:approved (boolean approved) :safe safe? :no-regression no-loss? :score-gain gain :old old :new new :rule config})))

(defn promote! [store run root a evidence]
  (save! root a)
  (*crash-hook* :after-artifact-write)
  (dependency-closure root a)
  (let [result (c/update-run! store run
    (fn [r]
      (u/ensure! (= evidence (promotion-evidence (:old evidence) (:new evidence) (get-in r [:config :promotion])))
                 "Promotion evidence does not match frozen rule" {})
      (u/ensure! (= (:parent a) (:active r)) "Stale candidate; reevaluate against current parent" {})
      (u/ensure! (not-any? #(not (c/terminal-statuses (:status %))) (vals (:sessions r))) "Promotion requires safe session boundary" {})
      (u/ensure! (nil? (:episode r)) "Promotion requires safe episode boundary" {})
      (let [receipt {:artifact (:hash a) :parent (:parent a) :evidence evidence
                     :status (if (:approved evidence) :approved :rejected)}]
        (*crash-hook* :before-promotion-commit)
        (-> r (update :candidates conj receipt)
            (cond-> (:approved evidence) (assoc :active (:hash a))
                    (:approved evidence) (update :promotions conj receipt))
            (c/event :candidate-decision receipt)))))]
    (*crash-hook* :after-promotion-commit)
    result))

(defn recover-registry! [store run root]
  (let [r (c/recover! store run) active (load! root (:active r))]
    (doseq [dependency (:dependencies active)] (load! root dependency)) r))

(defn rollback! [store run root hash]
  (let [target (load! root hash)]
    (doseq [dependency (:dependencies target)] (load! root dependency))
    (c/update-run! store run
      (fn [r]
        (u/ensure! (or (= hash (:initial-artifact r)) (some #(= hash (:artifact %)) (:promotions r))) "Rollback target was not approved" {})
        (u/ensure! (and (nil? (:episode r)) (not-any? #(not (c/terminal-statuses (:status %))) (vals (:sessions r)))) "Unsafe rollback boundary" {})
        (-> r (assoc :active hash) (c/event :rollback {:from (:active r) :to hash}))))))
