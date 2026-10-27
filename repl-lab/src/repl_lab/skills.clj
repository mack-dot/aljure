(ns repl-lab.skills
  "Controller-owned discovery metadata. Descriptions never confer execution authority."
  (:require [repl-lab.artifact :as a] [repl-lab.util :as u]))

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
