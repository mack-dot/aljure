(ns repl-lab.controller (:require [repl-lab.store :as db] [repl-lab.util :as u]))

(def terminal-statuses #{:complete :failed :cancelled :unknown})
(defn event [run type payload]
  (let [n (:sequence run)]
    (-> run (update :sequence inc) (update :events conj {:sequence n :type type :payload payload}))))
(defn create-run! [store id config artifact]
  (db/transact! store id
    (fn [old]
      (u/ensure! (nil? old) "Run already exists" {:id id})
      {:id id :created (u/now) :sequence 0 :events [] :config config :active artifact :initial-artifact artifact
       :sessions {} :mailbox {} :provider-requests {} :contexts {} :candidates [] :promotions []
       :status :running :spent {:calls 0 :tokens 0 :usd 0.0 :messages 0 :candidates 0 :evaluation-episodes 0}
       :reserved {:calls 0 :tokens 0 :usd 0.0} :started-ms (System/currentTimeMillis)})))
(defn update-run! [store run f] (db/transact! store run f))
(defn get-run [store run] (db/read-value store run))
(defn within-time! [run]
  (u/ensure! (and (= :running (:status run))
                  (< (- (System/currentTimeMillis) (:started-ms run)) (get-in run [:config :limits :wall-ms])))
             "Run stopped or wall budget exhausted" {}))

(defn session! [store run id parent]
  (update-run! store run
    (fn [r]
      (within-time! r)
      (u/ensure! (nil? (get-in r [:sessions id])) "Session exists" {:id id})
      (let [p (get-in r [:sessions parent]) depth (if p (inc (:depth p)) 0)
            active (filter #(and (:parent %) (not (terminal-statuses (:status %)))) (vals (:sessions r)))]
        (u/ensure! (or (and (nil? parent) (every? #(terminal-statuses (:status %)) (vals (:sessions r))))
                       (and p (not (terminal-statuses (:status p))))) "Invalid parent" {})
        (u/ensure! (<= depth (get-in r [:config :limits :recursion-depth])) "Recursion budget exhausted" {})
        (u/ensure! (or (nil? parent) (< (count active) (get-in r [:config :limits :concurrent-subagents]))) "Subagent limit" {})
        (-> r (assoc-in [:sessions id] {:id id :parent parent :task-root (if p (:task-root p) id) :depth depth :status :ready
                                        :artifact (:active r) :history [] :effects {} :acks #{}})
            (event :session-created {:id id :parent parent :artifact (:active r)}))))))

(defn resume-session! [store run id]
  (update-run! store run
    (fn [r]
      (within-time! r)
      (let [s (get-in r [:sessions id])
            active (count (filter #(and (:parent %) (not (terminal-statuses (:status %)))) (vals (:sessions r))))]
        (u/ensure! (and s (= :complete (:status s)) (= (:artifact s) (:active r))) "Cannot resume session" {})
        (u/ensure! (< active (get-in r [:config :limits :concurrent-subagents])) "Subagent limit" {})
        (-> r (assoc-in [:sessions id :status] :ready) (event :session-resumed {:id id}))))))

(defn finish-session! [store run id status summary]
  (update-run! store run
    (fn [r]
      (u/ensure! (and (get-in r [:sessions id]) (terminal-statuses status)) "Invalid terminal session" {})
      (let [current (get-in r [:sessions id :status])]
        (if (terminal-statuses current)
          ;; Terminal states are absorbing: a late or racing finish never rewrites an
          ;; outcome, so an unknown or failed session cannot later read as complete.
          (event r :session-finish-refused {:id id :status status :current current})
          (-> r (assoc-in [:sessions id :status] status)
              (update-in [:sessions id :history] #(vec (take-last (get-in r [:config :limits :history-records]) (conj % summary))))
              (event :session-finished {:id id :status status :summary summary})))))))

(defn cancel! [store run id]
  (update-run! store run
    (fn [r]
      (u/ensure! (get-in r [:sessions id]) "Missing session" {})
      (let [ids (loop [ids #{id}]
                  (let [more (into ids (map :id (filter #(ids (:parent %)) (vals (:sessions r)))))]
                    (if (= ids more) ids (recur more))))]
        ;; Cancelling revokes live or resumable sessions; it never masks a failed or unknown outcome.
        (-> (reduce #(if (#{:failed :unknown} (get-in %1 [:sessions %2 :status])) %1 (assoc-in %1 [:sessions %2 :status] :cancelled)) r ids)
            (event :sessions-cancelled {:ids ids}))))))

(defn send! [store run envelope]
  (update-run! store run
    (fn [r]
      (within-time! r)
      (u/ensure! (= #{:message-id :run-id :sender :recipient :correlation-id :schema-version :payload}
                     (set (keys envelope))) "Invalid message schema" {})
      (u/ensure! (and (= run (:run-id envelope)) (= 1 (:schema-version envelope))
                      (every? #(and (string? %) (<= 1 (count %) 128))
                              ((juxt :message-id :sender :recipient :correlation-id) envelope))
                      (map? (:payload envelope))) "Invalid envelope" {})
      (u/ensure! (<= (count (.getBytes (pr-str envelope) "UTF-8")) (get-in r [:config :limits :message-bytes])) "Message too large" {})
      (let [id (:message-id envelope) prior (get-in r [:mailbox id])]
        (if prior
          (do (u/ensure! (= envelope (dissoc prior :sequence :status :deliveries)) "Conflicting duplicate" {}) r)
          (do
            (u/ensure! (= (get-in r [:sessions (:sender envelope) :task-root])
                           (get-in r [:sessions (:recipient envelope) :task-root])) "Cross-task messages are denied" {})
            (doseq [who [(:sender envelope) (:recipient envelope)]]
              (u/ensure! (and (get-in r [:sessions who]) (not (terminal-statuses (get-in r [:sessions who :status])))) "Missing or terminal recipient/sender" {:id who}))
            (u/ensure! (< (get-in r [:spent :messages]) (get-in r [:config :limits :messages])) "Message budget exhausted" {})
            (-> r (assoc-in [:mailbox id] (assoc envelope :sequence (:sequence r) :status :pending :deliveries 0))
                (update-in [:spent :messages] inc) (event :message-sent envelope))))))))

(defn deliver! [store run recipient]
  (let [r (update-run! store run
            (fn [r]
              (u/ensure! (get-in r [:sessions recipient]) "Missing recipient" {})
              (reduce (fn [r [id m]] (if (and (= recipient (:recipient m)) (= :pending (:status m)))
                                       (update-in r [:mailbox id :deliveries] inc) r)) r (:mailbox r))))]
    (vec (sort-by :sequence (filter #(and (= recipient (:recipient %)) (= :pending (:status %))) (vals (:mailbox r)))))))

;; effects are data. The broker, not the caller, chooses their interpretation.
(defn acknowledge! [store run recipient message-id effects]
  (update-run! store run
    (fn [r]
      (let [m (get-in r [:mailbox message-id])]
        (u/ensure! (and m (= recipient (:recipient m)) (map? effects)) "Bad acknowledgement" {})
        (if (= :acked (:status m)) r
          (-> r (assoc-in [:mailbox message-id :status] :acked)
              (update-in [:sessions recipient :acks] conj message-id)
              (assoc-in [:sessions recipient :effects message-id] effects)
              (event :message-acknowledged {:id message-id :recipient recipient})))))))

(defn await-status [store run id]
  (let [s (get-in (get-run store run) [:sessions id])]
    (cond (nil? s) {:status :missing}
          (terminal-statuses (:status s)) (select-keys s [:status :history])
          :else {:status :pending})))

(defn reserve! [store run request-id session tokens usd]
  (update-run! store run
    (fn [r]
      (within-time! r)
      (u/ensure! (and (pos-int? tokens) (number? usd) (<= 0 usd) (Double/isFinite (double usd))) "Invalid reservation" {})
      (u/ensure! (= :ready (get-in r [:sessions session :status])) "Session not ready" {})
      (u/ensure! (nil? (get-in r [:provider-requests request-id])) "Request ID already used" {})
      (doseq [[k amount] [[:calls 1] [:tokens tokens] [:usd usd]]
              :let [limit (get-in r [:config :limits k])] :when limit]
        (u/ensure! (<= (+ amount (get-in r [:spent k]) (get-in r [:reserved k])) limit) "Global provider budget exhausted" {:resource k}))
      (-> r (update :reserved #(merge-with + % {:calls 1 :tokens tokens :usd usd}))
          (assoc-in [:sessions session :status] :calling)
          (assoc-in [:provider-requests request-id] {:session session :reserved-tokens tokens :reserved-usd usd :status :pending})
          (event :provider-reserved {:request-id request-id :session session :tokens tokens :usd usd})))))

(defn reconcile! [store run request-id response]
  (update-run! store run
    (fn [r]
      (let [q (get-in r [:provider-requests request-id]) {:keys [tokens usd model]} response]
        (u/ensure! (#{:pending :unknown} (:status q)) "Request not pending" {})
        (u/ensure! (and (nat-int? tokens) (number? usd) (<= 0 usd) (Double/isFinite (double usd))) "Invalid usage" {})
        (let [over (or (> tokens (:reserved-tokens q)) (> usd (:reserved-usd q)))]
          (-> r (update :reserved #(merge-with - % {:calls 1 :tokens (:reserved-tokens q) :usd (:reserved-usd q)}))
              (update :spent #(merge-with + % {:calls 1 :tokens tokens :usd usd}))
              (assoc-in [:provider-requests request-id :status] :complete)
              (assoc-in [:provider-requests request-id :response] response)
              (assoc-in [:sessions (:session q) :status] (if (= :cancelled (get-in r [:sessions (:session q) :status]))
                                                         :cancelled (if over :failed :ready)))
              (cond-> over (assoc :status :budget-overrun))
              (event :provider-result {:request-id request-id :model model :tokens tokens :usd usd :overrun over})))))))

(defn- mark-unknown [r id q]
  (-> r (assoc-in [:provider-requests id :status] :unknown)
      (assoc-in [:sessions (:session q) :status] :unknown)
      (event :provider-outcome-unknown {:request-id id})))

(defn recover!
  "An uncertain call keeps its reservation; the operator must reconcile it. With a
  request id, only that request is marked unknown, so a per-call failure leaves
  concurrent sibling calls alone. Without one, every pending request is marked:
  process-restart recovery only, when no call can still be in flight."
  ([store run]
   (update-run! store run
     (fn [r] (reduce (fn [r [id q]] (if (= :pending (:status q)) (mark-unknown r id q) r)) r (:provider-requests r)))))
  ([store run request-id]
   (update-run! store run
     (fn [r] (let [q (get-in r [:provider-requests request-id])]
               (if (= :pending (:status q)) (mark-unknown r request-id q) r))))))

(defn consume! [store run resource amount]
  (update-run! store run (fn [r]
                          (within-time! r)
                          (u/ensure! (and (pos-int? amount) (contains? #{:candidates :evaluation-episodes} resource)) "Invalid resource charge" {})
                          (u/ensure! (<= (+ amount (get-in r [:spent resource])) (get-in r [:config :limits resource])) "Budget exhausted" {:resource resource})
                          (update-in r [:spent resource] + amount))))

(defn put-context! [store run handle records]
  (update-run! store run #(assoc-in % [:contexts handle] records)))

(defn put-context-block! [store run handle records]
  ;; Large immutable traces must not be read, canonicalized and rewritten with
  ;; every controller event. Reuse the same SQLite store, under a content hash.
  ;; Publish the handle only after its complete immutable block is durable.
  (u/ensure! (vector? records) "Context block must contain records" {})
  (let [hash (u/hash-value records) key (str run "/context/" hash)]
    (db/transact! store key
      (fn [old]
        (u/ensure! (or (nil? old) (= old records)) "Immutable context block conflict" {})
        records))
    (update-run! store run #(assoc-in % [:contexts handle]
                              {:storage :immutable-record :hash hash :count (count records)}))))

(defn context-records [store run entry]
  (if (vector? entry) entry
    (do
      (u/ensure! (and (map? entry) (= #{:storage :hash :count} (set (keys entry)))
                      (= :immutable-record (:storage entry)) (nat-int? (:count entry))
                      (string? (:hash entry)) (re-matches #"[a-f0-9]{64}" (:hash entry)))
                 "Unknown approved context handle" {})
      (let [records (db/read-value store (str run "/context/" (:hash entry)))]
        (u/ensure! (and (vector? records) (= (:count entry) (count records))
                        (= (:hash entry) (u/hash-value records))) "Context block is missing or corrupt" {})
        records))))
(defn validate-context-query! [query]
  (u/ensure! (and (map? query) (every? #{:offset :limit :where :select} (keys query))
                  (nat-int? (get query :offset 0)) (pos-int? (get query :limit 20)) (<= (get query :limit 20) 64)
                  (or (nil? (:where query)) (map? (:where query)))
                  (or (nil? (:select query)) (and (vector? (:select query)) (every? keyword? (:select query))))) "Invalid context query" {})
  query)
(defn context [store run handle query]
  (validate-context-query! query)
  (let [r (get-run store run) rows (context-records store run (get-in r [:contexts handle]))
        selected (->> rows (filter #(every? (fn [[k v]] (= v (get % k))) (:where query)))
                      (drop (get query :offset 0)) (take (get query :limit 20))
                      (mapv #(if (:select query) (select-keys % (:select query)) %)))]
    (u/ensure! (<= (count (.getBytes (pr-str selected) "UTF-8")) (get-in r [:config :limits :context-bytes])) "Context slice too large" {})
    {:handle handle :total (count rows) :records selected}))
