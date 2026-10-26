(ns repl-lab.sim
  (:require [clojure.set :as set] [repl-lab.util :as u]))

(def event-order {:failure 0 :recover 1 :completion 2})
(defn- queue-event [s e]
  (-> s (update :events conj (assoc e :seq (:next-event s))) (update :next-event inc)))
(defn- ordered [events] (sort-by (juxt :at #(get event-order (:type %)) :seq) events))
(defn- log-event [s event] (update s :history conj (assoc event :time (:time s))))
(defn fits? [need available] (every? (fn [[r n]] (<= n (get available r 0))) need))
(defn- add-res [a b] (merge-with + a b))
(defn- sub-res [a b] (merge-with - a b))
(defn available [w] (sub-res (:capacity w) (:used w)))
(defn ready? [s job]
  (and (= :pending (:status job))
       (every? #(= :committed (get-in s [:jobs % :status])) (:deps job))))

(defn workload-errors [{:keys [jobs workers horizon faults]}]
  (let [ids (set (map :id jobs)) worker-ids (set (map :id workers))]
    (vec (concat
      (when-not (and (pos-int? horizon) (seq jobs) (seq workers)) [:empty-or-invalid-horizon])
      (when-not (= (count ids) (count jobs)) [:duplicate-job])
      (when-not (= (count worker-ids) (count workers)) [:duplicate-worker])
      (for [w workers :when (not (and (string? (:id w)) (pos-int? (:speed w))
                                      (seq (:capacity w)) (every? pos-int? (vals (:capacity w)))))] [:bad-worker (:id w)])
      (for [j jobs :when (not (and (string? (:id j)) (vector? (:deps j))
                                   (every? ids (:deps j)) (pos-int? (:estimate j))
                                   (pos-int? (:actual j)) (nat-int? (get j :delay 0))
                                   (seq (:resources j)) (every? pos-int? (vals (:resources j)))))]
        [:bad-job (:id j)])
      (for [f faults :when (not (and (#{:failure :recover} (:type f))
                                    (nat-int? (:at f)) (worker-ids (:worker f))))] [:bad-fault f])))))

(defn feasible? [{:keys [jobs workers]}]
  (and (every? (fn [j] (some #(fits? (:resources j) (:capacity %)) workers)) jobs)
       (loop [done #{} remaining jobs]
         (if (empty? remaining) true
           (let [ready (filter #(set/subset? (set (:deps %)) done) remaining)]
             (and (seq ready)
                  (recur (into done (map :id ready))
                         (remove (set ready) remaining))))))))

(declare advance)
(defn initial-state [world]
  (u/ensure! (empty? (workload-errors world)) "Invalid workload" {:errors (workload-errors world)})
  (let [s {:time 0 :horizon (:horizon world) :status (if (feasible? world) :running :impossible)
           :jobs (into (sorted-map) (map (fn [j] [(:id j) (assoc j :status :pending :attempt nil :commits 0)]) (:jobs world)))
           :workers (into (sorted-map) (map (fn [w] [(:id w) (assoc w :generation 0 :up true :used {} :attempts #{})]) (:workers world)))
           :attempts {} :events [] :next-event 0 :next-attempt 0 :history [] :steps 0
           :metrics {:rejected-actions 0 :stale-events 0 :retry-work 0 :busy-resource-time 0
                     :accepted-invariant-violations 0 :world-events 0}}
        s (reduce queue-event s (:faults world))]
    (advance s 0)))

(defn observe [s _agent-view]
  {:time (:time s) :horizon (:horizon s)
   :jobs (mapv #(assoc (select-keys % [:id :deps :resources :estimate :status :deadline])
                       :ready (boolean (ready? s %))) (vals (:jobs s)))
   :workers (mapv #(assoc (select-keys % [:id :capacity :speed :generation :up])
                          :available (available %)) (vals (:workers s)))
   :history (vec (take-last 64 (:history s)))})

(defn validate-action [s a]
  (cond
    (not= :running (:status s)) :episode-terminal
    (not (map? a)) :not-a-map
    (= :wait (:op a)) (when-not (and (= #{:op :ticks} (set (keys a)))
                                    (pos-int? (:ticks a)) (<= (:ticks a) 50)) :invalid-wait)
    (= :dispatch (:op a))
    (let [j (get-in s [:jobs (:job a)]) w (get-in s [:workers (:worker a)])]
      (cond (not= #{:op :job :worker} (set (keys a))) :invalid-schema
            (nil? j) :unknown-job (nil? w) :unknown-worker
            (not (ready? s j)) :not-ready (not (:up w)) :worker-down
            (not (fits? (:resources j) (available w))) :capacity))
    :else :unknown-action))

(defn check-invariants [s]
  (vec (concat
    (for [[id w] (:workers s)
          :let [running (filter #(and (= :running (:status %)) (= id (:worker %))) (vals (:attempts s)))
                allocated (reduce add-res {} (map :resources running))]
          :when (or (not (fits? allocated (:capacity w)))
                    (not= (into {} (filter (comp pos? val) allocated))
                          (into {} (filter (comp pos? val) (:used w))))
                    (some neg? (vals (:used w)))
                    (not= (set (map :id running)) (:attempts w))
                    (some #(or (not (:up w)) (not= (:generation %) (:generation w))) running))]
      [:worker-accounting id])
    (for [[id j] (:jobs s) :when (or (> (:commits j) 1)
                                     (not= (= :committed (:status j)) (= 1 (:commits j))))] [:commit-count id])
    (for [[id a] (:attempts s) :when
          (or (some #(let [t (get-in s [:jobs % :committed-at])] (or (nil? t) (> t (:start a)))) (:deps (get-in s [:jobs (:job a)])))
              (and (= :running (:status a))
                   (not= id (get-in s [:jobs (:job a) :attempt]))))] [:attempt-ownership id])
    (for [[id j] (:jobs s) :when (and (= :running (:status j))
                                      (not= :running (get-in s [:attempts (:attempt j) :status])))] [:job-ownership id])
    (for [[id j] (:jobs s) :when (and (= :committed (:status j))
                                      (not= :committed (get-in s [:attempts (:attempt j) :status])))] [:commit-evidence id]))))

(defn- release [s a]
  (-> s (update-in [:workers (:worker a) :used] sub-res (:resources a))
      (update-in [:workers (:worker a) :attempts] disj (:id a))))

(defn- apply-world-event [s e]
  (let [s (update-in s [:metrics :world-events] inc) wid (:worker e)]
    (case (:type e)
      :failure
      (let [attempts (get-in s [:workers wid :attempts])
            s (reduce (fn [st id]
                        (let [a (get-in st [:attempts id])]
                          (-> st (release a) (assoc-in [:attempts id :status] :failed)
                              (assoc-in [:attempts id :end] (:time st))
                              (assoc-in [:jobs (:job a) :status] :pending)
                              (assoc-in [:jobs (:job a) :attempt] nil)
                              (update-in [:metrics :retry-work] + (min (:duration a) (- (:time st) (:start a))))
                              (log-event {:type :attempt-failed :attempt id :job (:job a) :worker wid})))) s attempts)]
        (-> s (assoc-in [:workers wid :up] false) (update-in [:workers wid :generation] inc)
            (log-event {:type :failure :worker wid})))
      :recover (-> s (assoc-in [:workers wid :up] true) (log-event {:type :recover :worker wid}))
      :completion
      (let [a (get-in s [:attempts (:attempt e)]) j (get-in s [:jobs (:job a)]) w (get-in s [:workers (:worker a)])]
        (if (and a (= :running (:status a)) (= (:id a) (:attempt j))
                 (= (:generation a) (:generation w)) (:up w)
                 (= (:seq e) (:completion-seq a)))
          (-> s (release a) (assoc-in [:attempts (:id a) :status] :committed)
              (assoc-in [:attempts (:id a) :end] (:time s))
              (assoc-in [:jobs (:job a) :status] :committed)
              (assoc-in [:jobs (:job a) :committed-at] (:time s))
              (update-in [:jobs (:job a) :commits] inc)
              (log-event {:type :committed :attempt (:id a) :job (:job a) :worker (:worker a)}))
          (-> s (update-in [:metrics :stale-events] inc)
              (log-event {:type :stale-completion :attempt (:attempt e)})))))))

(defn- tick-to [s t]
  (let [busy (reduce + 0 (for [a (vals (:attempts s)) :when (= :running (:status a))]
                           (* (reduce + (vals (:resources a)))
                              (max 0 (- (min t (+ (:start a) (:duration a))) (:time s))))))]
    (-> s (update-in [:metrics :busy-resource-time] + busy) (assoc :time t))))

(defn advance
  ([s target] (advance s target Long/MAX_VALUE))
  ([s target world-event-limit]
  (loop [s s]
    (let [e (first (ordered (:events s))) target (min target (:horizon s))]
      (cond
        (and e (<= (:at e) target) (>= (get-in s [:metrics :world-events]) world-event-limit)) (assoc s :status :event-budget)
        (and e (<= (:at e) target))
        (let [next (-> s (tick-to (:at e)) (update :events #(vec (remove (fn [x] (= (:seq x) (:seq e))) %))))
              next (apply-world-event next e)]
          (u/ensure! (empty? (check-invariants next)) "World event violated invariants" {:event e :errors (check-invariants next)})
          (recur next))
        :else (tick-to s target))))))

(defn- terminal [s]
  (if (not= :running (:status s)) s
    (assoc s :status
      (cond (every? #(= :committed (:status %)) (vals (:jobs s))) :complete
            (>= (:time s) (:horizon s)) :horizon
            (and (not-any? #(= :running (:status %)) (vals (:jobs s)))
                 (not-any? #(= :recover (:type %)) (:events s))
                 (not-any? (fn [j] (and (ready? s j) (some #(and (:up %) (fits? (:resources j) (available %))) (vals (:workers s))))) (vals (:jobs s)))) :deadlock
            :else :running))))

(defn step
  ([s action] (step s action Long/MAX_VALUE))
  ([s action world-event-limit]
  (if-let [error (validate-action s action)]
    {:state s :accepted false :error error}
    (let [next
          (if (= :wait (:op action)) (advance s (+ (:time s) (:ticks action)) world-event-limit)
            (let [j (get-in s [:jobs (:job action)]) w (get-in s [:workers (:worker action)])
                  id (str "a" (:next-attempt s)) duration (quot (+ (:actual j) (dec (:speed w))) (:speed w))
                  a {:id id :job (:id j) :worker (:id w) :generation (:generation w)
                     :status :running :resources (:resources j) :start (:time s) :duration duration
                     :completion-seq (:next-event s)}]
              (-> s (assoc-in [:attempts id] a) (update :next-attempt inc)
                  (assoc-in [:jobs (:id j) :status] :running) (assoc-in [:jobs (:id j) :attempt] id)
                  (update-in [:workers (:id w) :used] add-res (:resources j))
                  (update-in [:workers (:id w) :attempts] conj id)
                  (queue-event {:type :completion :at (+ (:time s) duration (get j :delay 0)) :attempt id})
                  (log-event {:type :dispatch :job (:id j) :worker (:id w) :attempt id :generation (:generation w)}))))
          next (-> next (update :steps inc) terminal)]
      (u/ensure! (empty? (check-invariants next)) "Action violated invariants" {:errors (check-invariants next)})
      {:state next :accepted true}))))

(defn state-hash [s] (u/hash-value s))
(defn metrics [s]
  (let [jobs (vals (:jobs s)) n (count jobs) completed (count (filter #(= :committed (:status %)) jobs))
        capacity (reduce + (mapcat (comp vals :capacity) (vals (:workers s))))]
    (merge (:metrics s)
           {:status (:status s) :jobs n :completed completed :completion-rate (double (/ completed n))
            :makespan (when (= n completed) (reduce max 0 (map :committed-at jobs)))
            :score (+ (if (= n completed) (reduce max 0 (map :committed-at jobs)) (:horizon s))
                      (* (- n completed) (:horizon s)))
            :deadline-misses (count (filter #(and (:deadline %) (or (nil? (:committed-at %)) (> (:committed-at %) (:deadline %)))) jobs))
            :worker-utilization (if (pos? (:time s)) (double (/ (get-in s [:metrics :busy-resource-time]) (* capacity (:time s)))) 0.0)
            :virtual-time (:time s)})))

(defn run-episode [world decide {:keys [event-budget] :or {event-budget 10000}}]
  (loop [s (terminal (initial-state world)) memory {} records [] calls 0 nanos 0]
    (cond
      (not= :running (:status s))
      {:state s :final-hash (state-hash s) :records records
       :metrics (assoc (metrics s) :policy-calls calls :policy-nanos nanos)}
      (>= (+ calls (:steps s) (get-in s [:metrics :rejected-actions]) (get-in s [:metrics :world-events])) event-budget)
      (recur (assoc s :status :event-budget) memory records calls nanos)
      :else
      (let [start (System/nanoTime)
            result (try {:value (decide (observe s nil) memory)} (catch Exception e {:error (.getMessage e)}))
            elapsed (- (System/nanoTime) start) response (:value result)]
        (if (or (:error result) (not (map? response)) (not (vector? (:actions response)))
                (> (count (:actions response)) 128) (not (map? (:memory response))))
          (recur (assoc s :status :policy-error) {} (conj records {:type :policy-error :message (:error result)}) (inc calls) (+ nanos elapsed))
          (let [actions (if (seq (:actions response)) (:actions response) [{:op :wait :ticks 1}])
                [next rows] (reduce (fn [[st rows] a]
                                     (let [remaining (- event-budget (inc calls) (:steps st)
                                                        (get-in st [:metrics :rejected-actions]) (get-in st [:metrics :world-events]))]
                                     (cond (not= :running (:status st)) [st rows]
                                           (<= remaining 0) [(assoc st :status :event-budget) rows]
                                           :else
                                       (let [limit (+ (get-in st [:metrics :world-events]) (dec remaining))
                                             before (state-hash st) r (step st a limit)
                                             after (if (:accepted r) (:state r) (update-in st [:metrics :rejected-actions] inc))]
                                         [after (conj rows {:type :action :action a :accepted (:accepted r) :error (:error r)
                                                           :world-event-limit limit :before before :after (state-hash after)})])))) [s []] actions)]
            (recur next (:memory response)
                   (into (conj records {:type :policy-call :observation (observe s nil) :memory memory :response response}) rows)
                   (inc calls) (+ nanos elapsed))))))))

(defn replay [world records expected-hash terminal-status]
  (let [end (reduce (fn [s row]
                     (case (:type row)
                       :policy-error (assoc s :status :policy-error)
                       :policy-call (do (u/ensure! (= (:observation row) (observe s nil)) "Replay observation mismatch" {}) s)
                       (do (u/ensure! (= (:before row) (state-hash s)) "Replay before mismatch" {})
                           (let [r (step s (:action row) (get row :world-event-limit Long/MAX_VALUE))
                                 next (if (:accepted r) (:state r) (update-in s [:metrics :rejected-actions] inc))]
                             (u/ensure! (= [(:accepted row) (:error row) (:after row)]
                                            [(:accepted r) (:error r) (state-hash next)]) "Replay after mismatch" {}) next))))
                   (terminal (initial-state world)) records)
        end (if (= terminal-status :event-budget) (assoc end :status :event-budget) end)]
    (u/ensure! (= expected-hash (state-hash end)) "Replay final mismatch" {}) end))
