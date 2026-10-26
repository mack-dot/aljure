(ns repl-lab.bundle (:require [repl-lab.artifact :as a] [repl-lab.util :as u]
                             [clojure.java.io :as io] [clojure.walk :as walk]))

(defn audit [artifact]
  (let [strings (atom []) numbers (atom []) symbols (atom [])
        python? (and (= :python (a/language artifact)) (not= :workflow (:category artifact)))
        nodes (when python? (filter #(and (map? %) (:node %)) (tree-seq coll? seq (:forms artifact))))]
    (walk/postwalk #(do (cond (string? %) (swap! strings conj %)
                              (number? %) (swap! numbers conj %)
                              (symbol? %) (swap! symbols conj (str %))) %) (:forms artifact))
    (when python?
      (reset! symbols (vec (mapcat #(keep (get % :fields) [:id :name :attr]) nodes)))
      (reset! strings (vec (keep #(when (and (= "Constant" (:node %)) (string? (get-in % [:fields :value])))
                                 (get-in % [:fields :value])) nodes)))
      (reset! numbers (vec (keep #(when (and (= "Constant" (:node %)) (number? (get-in % [:fields :value])))
                                 (get-in % [:fields :value])) nodes))))
    {:hash (:hash artifact) :language (a/language artifact) :source-bytes (count (.getBytes (:source artifact) "UTF-8"))
     :comments :removed-by-canonical-export
     :docstrings (if python? {:retained true :values (vec (keep (fn [node]
                            (let [first-node (first (get-in node [:fields :body]))
                                  value (get-in first-node [:fields :value :fields :value])]
                              (when (and (#{"Module" "FunctionDef" "AsyncFunctionDef" "ClassDef"} (:node node))
                                         (= "Expr" (:node first-node)) (string? value)) value))) nodes))}
                    :not-supported-in-fn-contract)
     :encoded-literals (vec (keep #(let [v (get-in % [:fields :value])] (when (and (map? v) (:literal v)) v)) nodes))
     :string-literals @strings :numeric-literals @numbers
     :suspicious-identifiers (vec (filter #(and (string? %) (re-find #"(?i)seed|answer|transcript|cache|workload|j[0-9]{3}" %)) @symbols))
     :large-embedded-literals (vec (filter #(> (count %) 128) @strings))
     :claim "Inspection aid only. Human review is still required for model-generated artifacts."}))

(defn export! [registry output active provenance]
  (u/ensure! (not (.exists (io/file output))) "Export destination already exists" {})
  (let [all (loop [todo [active] artifacts {}]
              (if (empty? todo) artifacts
                (let [hash (peek todo) todo (pop todo)]
                  (if (contains? artifacts hash) (recur todo artifacts)
                    (let [item (a/load! registry hash)]
                      (recur (into todo (:dependencies item)) (assoc artifacts hash item)))))))
        ;; Only executable source/forms and minimal API/dependency metadata cross
        ;; this boundary. Parent/provenance/session receipts stay in controller data.
        files (into (sorted-map)
                    (map (fn [[hash artifact]]
                           [(str hash ".edn") (pr-str (select-keys artifact [:language :category :forms :interface :dependencies :provenance]))]) all))
        manifest {:schema-version 2 :active active :provenance provenance
                  :files (into (sorted-map) (map (fn [[path body]] [path {:sha256 (u/sha body) :bytes (count (.getBytes body "UTF-8"))}]) files))
                  :audit (mapv audit (vals all)) :artifact-count (count all)
                  :bytes (reduce + (map #(count (.getBytes % "UTF-8")) (vals files)))}]
    (let [destination (.getAbsoluteFile (io/file output)) parent (.getParentFile destination)
          _ (.mkdirs parent)
          staging (java.nio.file.Files/createTempDirectory (.toPath parent) ".bundle-staging-"
                                                           (make-array java.nio.file.attribute.FileAttribute 0))]
      (doseq [[path body] files] (u/atomic-write! (str (.resolve staging path)) body))
      (u/write-edn! (str (.resolve staging "manifest.edn")) manifest)
      (java.nio.file.Files/move staging (.toPath destination)
                               (into-array java.nio.file.CopyOption [java.nio.file.StandardCopyOption/ATOMIC_MOVE])))
    manifest))

(defn load-bundle [path]
  (let [root (io/file path) manifest (u/read-file (io/file root "manifest.edn"))
        expected (conj (set (keys (:files manifest))) "manifest.edn")
        actual (set (map #(.getName %) (.listFiles root)))]
    (u/ensure! (#{1 2} (:schema-version manifest)) "Unsupported bundle" {})
    (u/ensure! (= expected actual) "Bundle whitelist mismatch" {})
    (let [artifacts (into {} (for [[file info] (:files manifest)]
                             (do
                               (u/ensure! (boolean (re-matches #"[a-f0-9]{64}\.edn" file)) "Invalid bundle path" {})
                               (let [f (io/file root file)
                                     _ (u/ensure! (not (java.nio.file.Files/isSymbolicLink (.toPath f))) "Bundle symlink rejected" {})
                                     _ (u/ensure! (<= (.length f) 65536) "Bundle file too large" {})
                                     body (slurp f)]
                                 (u/ensure! (= (:sha256 info) (u/sha body)) "Bundle content hash mismatch" {:file file})
                                 (u/ensure! (= (:bytes info) (count (.getBytes body "UTF-8"))) "Bundle size mismatch" {})
                                 [(subs file 0 64) (u/read-edn body)]))))]
      (u/ensure! (contains? artifacts (:active manifest)) "Missing active artifact" {})
      (doseq [[_ artifact] artifacts]
        (u/ensure! (and (every? #{:language :category :forms :interface :dependencies :provenance} (keys artifact))
                        (every? #(contains? artifact %) [:category :forms :interface :dependencies])
                        (#{:clojure :python} (a/language artifact))) "Unexpected executable bundle fields" {})
        (doseq [dep (:dependencies artifact)]
          (u/ensure! (contains? artifacts dep) "Missing bundle dependency" {})))
      {:manifest manifest :artifacts artifacts})))
