(ns repl-lab.service-fixture
  "A synthetic external service for the programmatic-execution development benchmark
  (research/PROGRAMMATIC_EXECUTION.md). It lives in controller memory for one task, seeded from
  a fixture, so every effect is reversible and observable: the final state is scored against the
  task's expected state. Faults are scripted by the fixture, never random: a rate limit every
  n-th call, ids whose reads and writes fail, and ids whose first update is applied but reported
  as uncertain (a timeout after commit), which a correct program must not repeat."
  (:require [repl-lab.util :as u]))

(def page-limit 50)
(def field-chars 4096)

(defn open
  "The service state for one task. fixture: {:collections {name {id record}} :faults {...}}."
  [fixture]
  (u/ensure! (and (map? fixture) (map? (:collections fixture))
                  (every? (fn [[n rows]] (and (string? n) (map? rows) (every? (fn [[id r]] (and (string? id) (map? r))) rows)))
                          (:collections fixture)))
             "Invalid service fixture" {})
  (let [faults (or (:faults fixture) {})]
    (u/ensure! (and (map? faults) (every? #{:rate-limit-every :fail-ids :uncertain-ids} (keys faults))
                    (or (nil? (:rate-limit-every faults)) (pos-int? (:rate-limit-every faults)))
                    (every? #(every? string? (get faults % [])) [:fail-ids :uncertain-ids]))
               "Invalid service faults" {})
    (atom {:collections (:collections fixture)
           :faults {:rate-limit-every (:rate-limit-every faults) :fail-ids (set (:fail-ids faults))
                    :uncertain-ids (set (:uncertain-ids faults))}
           :calls 0 :log []})))

(defn- fault! [state op id]
  (let [{:keys [rate-limit-every fail-ids]} (:faults state)]
    (when (and rate-limit-every (zero? (mod (:calls state) rate-limit-every)))
      (u/fail "Service rate limit: retry this call" {:retryable true}))
    (when (and id (fail-ids id))
      (u/fail (str "Service error 500 on " id) {:retryable false}))))

(defn- counted! [service op id]
  ;; Every call counts toward the rate limit, including the ones it refuses.
  (let [state (swap! service #(-> % (update :calls inc) (update :log conj {:op op :id id})))]
    (fault! state op id)
    state))

(defn- rows-of [state name]
  (or (get-in state [:collections name]) (u/fail (str "Unknown collection: " name) {})))

(defn- matches? [record where]
  (every? (fn [[k v]] (= v (get record k))) where))

(defn list!
  "{:collection :offset :limit :where}: records of a collection, in id order, at most 50 per call."
  [service {:keys [collection offset limit where] :or {offset 0 limit page-limit}}]
  (u/ensure! (and (string? collection) (nat-int? offset) (pos-int? limit) (<= limit page-limit)
                  (or (nil? where) (and (map? where) (every? keyword? (keys where)))))
             "list needs :collection, optional :offset, :limit (1-50) and :where {field value}" {})
  (let [state (counted! service :list nil)
        rows (->> (rows-of state collection) (sort-by key) (map (fn [[id r]] (assoc r :id id)))
                  (filter #(matches? % where)))]
    {:total (count rows) :items (vec (->> rows (drop offset) (take limit)))}))

(defn get!
  "{:collection :id}: one record."
  [service {:keys [collection id]}]
  (u/ensure! (and (string? collection) (string? id)) "get needs :collection and :id" {})
  (let [state (counted! service :get id)]
    (or (some-> (get (rows-of state collection) id) (assoc :id id))
        (u/fail (str "Not found: " id) {}))))

(defn update!
  "{:collection :id :fields}: merges fields into one record and returns it. An id in
  :uncertain-ids is updated and then reported as uncertain, once."
  [service {:keys [collection id fields]}]
  (u/ensure! (and (string? collection) (string? id) (map? fields) (seq fields) (every? keyword? (keys fields))
                  (every? #(or (string? %) (number? %) (boolean? %) (nil? %)) (vals fields))
                  (every? #(or (not (string? %)) (<= (count %) field-chars)) (vals fields)))
             "update needs :collection, :id and :fields {keyword scalar}" {})
  (let [state (counted! service :update id)
        _ (rows-of state collection)
        _ (u/ensure! (get-in state [:collections collection id]) (str "Not found: " id) {})
        uncertain? (contains? (get-in state [:faults :uncertain-ids]) id)
        after (swap! service (fn [s] (cond-> (update-in s [:collections collection id] merge fields)
                                       uncertain? (update-in [:faults :uncertain-ids] disj id))))]
    (when uncertain?
      (u/fail (str "Service timeout on " id " after the request was sent") {:uncertain true}))
    (assoc (get-in after [:collections collection id]) :id id)))

(defn snapshot
  "The observable state: collections and the call log, for scoring and evidence."
  [service]
  (select-keys @service [:collections :calls :log]))

(defn collections [service] (:collections @service))
