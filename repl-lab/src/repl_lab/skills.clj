(ns repl-lab.skills
  "Controller-owned discovery metadata. Descriptions never confer execution authority."
  (:require [clojure.java.io :as io] [clojure.string :as str] [repl-lab.artifact :as a] [repl-lab.util :as u]))

(defn approved [registry active-hash]
  (let [active (a/load! registry active-hash)]
    (filterv #(#{:policy :analysis} (:category %))
             (conj (a/dependency-closure registry active) active))))

(defn reviewed-catalog []
  ;; Fixed controller config, never a path or description supplied by the model.
  (let [catalog (u/read-file "config/skill-descriptions-v1.edn")
        text (slurp (get-in catalog [:evidence :path]))]
    (u/ensure! (= (u/sha text) (get-in catalog [:evidence :sha256])) "Skill evidence changed" {})
    (assoc catalog :report (u/json-read text))))

(defn entry [artifact catalog]
  (a/verify artifact)
  (let [hash (:hash artifact) reviewed (get-in catalog [:descriptions hash])
        cases (filter #(= hash (:artifact %)) (get-in catalog [:report :cases]))
        healthy (filter #(and (nil? (:failure-stage %)) (nil? (:cleanup-error %))) cases)
        complete (filter #(= "complete" (get-in % [:metrics :status])) healthy)
        descriptor (or reviewed
                       {:name (str "approved-" (name (:category artifact)) "-" (subs hash 0 12))
                        :description (str "Approved executable export " (get-in artifact [:interface :name]) ". Behavior has not been described independently.")
                        :applicability {:status :unreviewed}
                        :limitations ["No independently reviewed behavior or applicability description."]})
        body (merge descriptor
               {:version-hash hash :interface (:interface artifact) :language (a/language artifact)
                :provenance (select-keys artifact [:author :provenance :parent :dependencies])
                :metadata-validation (if reviewed
                                       {:method (:review-method catalog) :catalog-version (:version catalog)
                                        :scope :exact-artifact-hash}
                                       {:method :derived-interface-only})
                :validation-evidence {:reference (when (seq cases) (:evidence catalog))
                                      :attempted (count cases) :healthy (count healthy)
                                      :completed (count complete) :infrastructure-or-execution-failures (- (count cases) (count healthy))
                                      :mean-completed-makespan (when (seq complete)
                                                                (/ (reduce + (map #(get-in % [:metrics :makespan]) complete)) (double (count complete))))
                                      :status (if (seq cases) :recorded-diagnostic :not-in-this-diagnostic)}
                :implementation {:op :artifact/inspect :hash hash}})]
    (assoc body :metadata-hash (u/hash-value body))))

(defn inventory [registry active-hash]
  (let [catalog (reviewed-catalog)]
    (mapv #(entry % catalog) (approved registry active-hash))))

(defn compact [entry]
  (select-keys entry [:name :description :interface :applicability :version-hash
                     :metadata-hash :limitations :metadata-validation :validation-evidence]))

(defn describe [registry active-hash hash]
  (or (first (filter #(= hash (:version-hash %)) (inventory registry active-hash)))
      (u/fail "Skill is not in this session's approved library" {})))

(defn select-policy [registry active-hash hash]
  (let [target (first (filter #(= hash (:hash %)) (approved registry active-hash)))]
    (u/ensure! (and target (= :policy (:category target)) (= {:name "decide" :arity 2} (:interface target)))
               "Policy is not in this session's approved library" {})
    target))

;; Artifact library versions. A version is an immutable, content-addressed list over the
;; existing registry (<root>/artifacts/<hash>.edn, artifact/save!): <root>/libraries/<sha256>.edn,
;; where sha256 is the hash of the file's bytes. A plan pins one version; a status change
;; or a promotion writes a new version whose :parent is the old one. Only :approved entries
;; are discoverable. Each entry pins its function and its applicability predicate by both
;; provenance hash and code hash.
(def library-statuses #{:approved :quarantined :unknown :rejected})
(def ^:private entry-keys #{:artifact :code-hash :applicability :applicability-code-hash :status :summary :receipt})

(defn- library-file [root sha]
  (u/ensure! (and (string? sha) (re-matches #"[a-f0-9]{64}" sha)) "Invalid library hash" {})
  (io/file root "libraries" (str sha ".edn")))

(defn- check-entry! [root entry]
  (u/ensure! (and (map? entry) (every? entry-keys (keys entry)) (library-statuses (:status entry))
                  (every? #(contains? entry %) [:artifact :code-hash :applicability :applicability-code-hash :status])
                  (or (nil? (:summary entry)) (and (string? (:summary entry)) (<= (count (:summary entry)) 240))))
             "Invalid library entry" {})
  (let [function (a/load! root (:artifact entry)) predicate (a/load! root (:applicability entry))]
    (u/ensure! (= (:code-hash entry) (a/code-hash function)) "Library code hash differs from its artifact" {:artifact (:artifact entry)})
    (u/ensure! (= (:applicability-code-hash entry) (a/code-hash predicate)) "Library predicate code hash differs" {:artifact (:artifact entry)})
    (u/ensure! (#{:analysis :policy} (:category function)) "A library entry exports a function" {})
    (u/ensure! (and (= :analysis (:category predicate)) (= 1 (get-in predicate [:interface :arity]))
                    (empty? (:dependencies predicate)) (= (a/language function) (a/language predicate)))
               "An applicability predicate is a dependency-free one-argument function" {})
    ;; Every dependency is present and verifies.
    (a/dependency-closure root function)
    entry))

(defn- check-version! [root version]
  (u/ensure! (and (map? version) (= #{:schema :parent :entries} (set (keys version)))
                  (= :aljure-library-v1 (:schema version)) (vector? (:entries version))
                  (or (nil? (:parent version)) (boolean (re-matches #"[a-f0-9]{64}" (str (:parent version)))))
                  (or (empty? (:entries version)) (apply distinct? (map :artifact (:entries version)))))
             "Invalid library version" {})
  (doseq [entry (:entries version)] (check-entry! root entry))
  version)

(defn write-library!
  "Writes one immutable version and returns its sha256. Every entry must verify first."
  [root version]
  (check-version! root version)
  (let [text (binding [*print-namespace-maps* false *print-length* nil *print-level* nil *print-meta* false]
               (str (pr-str (u/canonical version)) "\n"))
        sha (u/sha text) f (library-file root sha)]
    (if (.exists f)
      (u/ensure! (= text (slurp f)) "Immutable library conflict" {})
      (u/atomic-write! (str f) text))
    sha))

(defn load-library
  "Reads the pinned version from durable storage. Fails closed on a missing file, a hash
  mismatch, or any entry whose artifact, predicate, code hash or dependency does not verify."
  [root sha]
  (let [f (library-file root sha)]
    (u/ensure! (and (.isFile f) (not (java.nio.file.Files/isSymbolicLink (.toPath f)))) "Pinned library version is missing" {})
    (u/ensure! (<= (.length f) 1048576) "Library version too large" {})
    (let [text (slurp f)]
      (u/ensure! (= sha (u/sha text)) "Library hash mismatch" {})
      (assoc (check-version! root (u/read-edn text)) :sha256 sha))))

(defn discover
  "Controller-side discovery: only :approved entries of the pinned version are offered,
  each with its verified function, predicate and dependency closure. The model never
  chooses or names what is discovered."
  [root sha]
  (let [library (load-library root sha)]
    {:sha256 sha :statuses (frequencies (map :status (:entries library)))
     :approved (vec (for [entry (:entries library) :when (= :approved (:status entry))]
                      (let [function (a/load! root (:artifact entry))]
                        (assoc entry :function function :predicate (a/load! root (:applicability entry))
                               :dependencies (a/dependency-closure root function)))))}))

(defn update-library!
  "A new version derived from a pinned one; the old version stays loadable."
  [root sha f]
  (let [library (load-library root sha)]
    (write-library! root {:schema :aljure-library-v1 :parent sha :entries (vec (f (:entries library)))})))

(defn set-status!
  "Quarantine, mark unknown or reinstate one entry in a new version."
  [root sha artifact-hash status]
  (u/ensure! (library-statuses status) "Unknown library status" {})
  (update-library! root sha (fn [entries]
                              (u/ensure! (some #(= artifact-hash (:artifact %)) entries) "Not in this library" {})
                              (map #(if (= artifact-hash (:artifact %)) (assoc % :status status) %) entries))))

(defn add-entry!
  "Records a validated candidate in a new version. The status follows the frozen promotion
  rule's decision (artifact/promotion-evidence); a rejected candidate is kept, never offered."
  [root sha {:keys [artifact applicability summary]} evidence]
  (let [function (a/load! root (:hash artifact)) predicate (a/load! root (:hash applicability))]
    (update-library! root sha
      (fn [entries]
        (conj (vec entries)
              (cond-> {:artifact (:hash function) :code-hash (a/code-hash function)
                       :applicability (:hash predicate) :applicability-code-hash (a/code-hash predicate)
                       :status (if (:approved evidence) :approved :rejected)
                       :receipt (select-keys evidence [:approved :no-regression :score-gain :old :new :rule])}
                summary (assoc :summary summary)))))))

(defn capability-note
  "The task-message note for preloaded functions (aljure_contract.artifacts only): names,
  arities and reviewed summaries. Nil when nothing is preloaded, so the message is unchanged."
  [functions]
  (when-let [exports (seq (filter #(= :export (:role %)) functions))]
    {:note "Controller-validated functions already defined in your SCI worker. Using them is optional."
     :functions (mapv #(cond-> {:name (:name %) :arity (:arity %)} (:summary %) (assoc :summary (:summary %))) exports)}))

(defn reuse-summary
  "One task's reuse record from its controller events (research/ARTIFACT_TASK_PATH_V1.md).
  :eligible-reuse needs an applicable approved function that ran and whose output entered
  the answer: it ran inside the root's delivered done source, or one of its scalar results
  equals the trimmed answer. Refusals are listed apart; their correctness needs the task family."
  [events result]
  (let [of (fn [type] (map :payload (filter #(= type (:type %)) events)))
        decisions (of :artifact-applicability)
        exports (vec (distinct (keep #(when (= :preload (:decision %)) (:code-hash %)) decisions)))
        available (set (mapcat #(map :code-hash (:functions %)) (of :artifact-preloaded)))
        invocations (for [batch (of :artifact-invocations) item (:invocations batch)]
                      (merge item (select-keys batch [:session :op :call-sequence])))
        evaluations (count (filter #(#{:repl/eval :done/eval} (get-in % [:command :op])) (of :tool-call)))
        answer (when (and (not (:error result)) (string? (:summary result))) (:summary result))
        final (last (filter #(and (= "root" (:session %)) (= :ok (:status %)) (#{:done :done/eval} (:op %))) (of :tool-result)))
        mode (cond (nil? answer) :none
                   (some #(= "root" (:session %)) (of :terminal-text-accepted)) :terminal-text
                   (= :done/eval (:op final)) :done-eval
                   :else :done-summary)
        computed (set (keep #(when (and (= "root" (:session %)) (= :done/eval (:op %)) (= :done-eval mode)
                                        (= (:call-sequence final) (:call-sequence %)) (pos? (:returns %)))
                               (:code-hash %)) invocations))
        equal (set (keep #(when (and answer (some #{(str/trim answer)} (:values %))) (:code-hash %)) invocations))
        in-answer (into (sorted-map) (for [h available :when (or (computed h) (equal h))]
                                       [h (if (computed h) :computed-in-answer :value-equals-answer)]))
        invoked (reduce (fn [m i] (update m (:code-hash i) (fnil + 0) (:calls i))) (sorted-map) invocations)]
    {:schema :artifact-reuse-v1
     :library-sha256 (:library-sha256 (first (of :artifact-library-loaded)))
     :exports exports :available (vec (sort available))
     :refused (vec (keep #(when (= :refuse (:decision %)) (select-keys % [:artifact :code-hash :reason])) decisions))
     :invoked invoked :in-answer in-answer :answer-mode mode :model-evaluations evaluations
     :classification (cond (nil? answer) :no-answer
                           (zero? evaluations) :direct-answer
                           (empty? exports) :no-applicable-artifact
                           (seq in-answer) :eligible-reuse
                           (seq invoked) :invoked-not-in-answer
                           :else :available-not-invoked)}))
