(ns repl-lab.artifact (:require [repl-lab.util :as u] [repl-lab.store :as db]
                               [repl-lab.controller :as c] [clojure.java.io :as io]))

(def categories #{:policy :analysis :workflow})
(def ^:dynamic *crash-hook* (fn [_] nil))
(defn parse-source [source]
  (u/ensure! (and (string? source) (<= (count (.getBytes source "UTF-8")) 32768)) "Source limit" {})
  (u/read-edn source))
(defn make-artifact [{:keys [category source interface dependencies author parent provenance] :as input}]
  (u/ensure! (categories category) "Fixed host component is not learnable" {})
  (u/ensure! (and (map? interface) (string? (:name interface)) (boolean (re-matches #"[a-z][a-z0-9-]*" (:name interface)))
                  (vector? dependencies) (every? #(and (string? %) (boolean (re-matches #"[a-f0-9]{64}" %))) dependencies)
                  (string? author) (#{:developer-fixture :model-generated :human-edit} provenance)) "Invalid artifact metadata" {})
  (let [forms (parse-source source)
        _ (u/ensure! (if (= category :workflow) (map? forms)
                       (and (seq? forms) (= 'fn (first forms)) (vector? (second forms))
                            (= (:arity interface) (count (second forms))))) "Invalid exported interface" {})
        _ (when (= category :workflow)
            (let [strategy (:strategy forms)]
              (u/ensure! (and (= #{:strategy} (set (keys forms))) (map? strategy)
                              (every? #{:policy :context :delegate} (keys strategy))
                              (some #{(:policy strategy)} dependencies)) "Invalid workflow or undeclared policy dependency" {})
              (c/validate-context-query! (:context strategy))
              (when-let [delegation (:delegate strategy)]
                (u/ensure! (and (= #{:task} (set (keys delegation))) (string? (:task delegation))
                                (<= (count (:task delegation)) 1024)) "Invalid delegation" {}))))
        body (assoc (select-keys input [:category :source :interface :dependencies :author :parent :provenance]) :forms forms)]
    (assoc body :hash (u/hash-value body))))
(defn verify [a]
  (u/ensure! (= (:hash a) (u/hash-value (dissoc a :hash))) "Artifact hash mismatch" {})
  (u/ensure! (= (:forms a) (parse-source (:source a))) "Source and forms disagree" {}) a)
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
(defn patch [base {:keys [base-hash path expected-hash replacement author dependencies]}]
  (verify base)
  (u/ensure! (= base-hash (:hash base)) "Stale structural patch" {})
  (u/ensure! (and (vector? path) (seq path)) "Patch requires one explicit subtree path" {})
  (u/ensure! (= expected-hash (u/hash-value (subtree (:forms base) path))) "Ambiguous or changed target" {})
  (make-artifact (-> base (dissoc :hash :forms)
                     (assoc :source (pr-str (replace-subtree (:forms base) path replacement))
                            :parent (:hash base) :author author)
                     (cond-> dependencies (assoc :dependencies dependencies)))))

(defn promotion-evidence [old new config]
  (u/ensure! (and (seq old) (= (count old) (count new))) "Unpaired development panel" {})
  (doseq [[a b] (map vector old new)] (u/ensure! (= (:case a) (:case b)) "Mismatched paired case" {}))
  (let [safe? (every? #(zero? (:accepted-invariant-violations %)) new)
        no-loss? (every? (fn [[a b]] (and (>= (:completed b) (:completed a))
                                          (or (nil? (:makespan a)) (and (:makespan b) (<= (:makespan b) (:makespan a)))))) (map vector old new))
        gain (- (reduce + (map :score old)) (reduce + (map :score new)))
        approved (and safe? no-loss? (>= gain (:min-score-improvement config)))]
    {:approved (boolean approved) :safe safe? :no-regression no-loss? :score-gain gain :old old :new new :rule config}))

(defn promote! [store run root a evidence]
  (save! root a)
  (*crash-hook* :after-artifact-write)
  (doseq [dep (:dependencies a)] (load! root dep))
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
