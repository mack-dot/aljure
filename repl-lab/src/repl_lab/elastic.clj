(ns repl-lab.elastic
  "Controller-owned asynchronous child sessions: spawn, status, collect and
  cancel, as a ledger state machine plus a small executor. Phase A of
  research/ELASTIC_IMPLEMENTATION_PLAN.md.

  Off by default. Every operation refuses unless the run config sets
  [:contract :elastic-children] to a settings map, and refuses before writing
  anything. Nothing model-facing uses this namespace yet: no tool schema, prompt
  text, provider adapter, runner or benchmark plan changes with it.

  Budget rule. A child provider call is reserved in the run's shared :reserved
  counter in the same compare-and-set transaction that checks
  (1) the run limit, less a floor kept back for the root session, and
  (2) the quota of the child and of every elastic ancestor; a quota bounds a
  whole subtree.
  A call settles from its receipt. It is released only when it was provably never
  sent. Otherwise it stays reserved as :unknown, and the elastic layer halts for
  the task until an operator settles it. Terminal child states never change."
  (:require [repl-lab.controller :as c] [repl-lab.util :as u]))

(def defaults
  {:max-depth 1 :max-active 2 :max-children 8
   :child-calls 8 :child-tokens 400000 :child-usd 2.0 :child-wall-ms 120000
   :root-floor {:calls 2} :result-chars 4000 :profiles #{:inherit}})

(def active-states #{:spawned :running :cancelling})
;; :unknown is neither active nor terminal: the child cannot run, and its
;; reservation is held until an operator settles the request from a receipt.
(def terminal-states #{:completed :failed :cancelled :timed-out :budget-exhausted :orphaned})
(def spec-keys #{:id :task :context :profile :quota})
(def id-pattern #"[a-z0-9][a-z0-9_-]{0,63}")
(def budget-denials #{:child-quota :run-budget})

(defn- now [] (System/currentTimeMillis))
(defn- finite-nonneg? [x] (and (number? x) (<= 0 x) (Double/isFinite (double x))))
(defn- deny [reason data]
  (throw (ex-info (str "Elastic request denied: " (name reason)) (assoc data :elastic-denied reason))))

(defn settings
  "The validated settings map, or a refusal that carries no :elastic-denied, so
  that nothing, not even a denial event, is written while the switch is off."
  [r]
  (let [value (get-in r [:config :contract :elastic-children])]
    (u/ensure! (some? value) "Elastic execution is disabled" {})
    (u/ensure! (and (map? value) (every? (set (keys defaults)) (keys value))) "Invalid elastic settings" {})
    (let [s (merge defaults value) floor (:root-floor s)]
      (u/ensure! (and (every? pos-int? (map s [:max-depth :max-active :max-children :child-calls
                                              :child-tokens :child-wall-ms :result-chars]))
                      (finite-nonneg? (:child-usd s)) (pos? (:child-usd s)) (<= (:result-chars s) 65536)
                      (<= (:max-depth s) (get-in r [:config :limits :recursion-depth] 0))
                      (map? floor) (every? #{:calls :tokens :usd} (keys floor))
                      (nat-int? (get floor :calls 0)) (nat-int? (get floor :tokens 0)) (finite-nonneg? (get floor :usd 0))
                      (set? (:profiles s)) (every? keyword? (:profiles s)) (contains? (:profiles s) :inherit))
                 "Invalid elastic settings" {})
      s)))

;; ---------------------------------------------------------------------------
;; Ledger queries

(defn child [r id] (get-in r [:elastic :children id]))
(defn children [r] (get-in r [:elastic :children] {}))
(defn- requests [r] (get-in r [:elastic :requests] {}))
(defn pending
  "Request ids of this child's calls that are in flight."
  [r id]
  (vec (keep (fn [[rid q]] (when (and (= id (:child q)) (= :pending (:status q))) rid)) (requests r))))
(defn- elastic-chain
  "The child and its elastic ancestors, nearest first."
  [r id]
  (loop [x id out []] (if (child r x) (recur (:parent (child r x)) (conj out x)) out)))
(defn- lineage
  "Every ancestor id of a child, up to and including the root session."
  [r id]
  (loop [x (:parent (child r id)) out []] (if (child r x) (recur (:parent (child r x)) (conj out x)) (conj out x))))
(defn descendants [r id]
  (loop [ids #{id}]
    (let [more (into ids (keep (fn [[k v]] (when (ids (:parent v)) k)) (children r)))]
      (if (= more ids) (disj ids id) (recur more)))))
(defn- in-root [r task-root] (filter #(= task-root (:task-root %)) (vals (children r))))
(defn- add-chain [r id field amounts]
  (reduce (fn [r x] (update-in r [:elastic :children x field] #(merge-with + % amounts))) r (elastic-chain r id)))
(defn- transition [r id state reason t]
  (-> r (update-in [:elastic :children id] assoc :state state :reason reason :changed-ms t)
      (c/event :elastic-state {:child id :state state :reason reason})))
(defn- stop
  "Stops each listed child that is still spawned or running. One with a call in
  flight moves to :cancelling and reaches target when that call ends."
  [r ids reason target t]
  (reduce (fn [r x]
            (cond (not (#{:spawned :running} (:state (child r x)))) r
                  (seq (pending r x)) (-> (transition r x :cancelling reason t)
                                          (assoc-in [:elastic :children x :cancel-target] target))
                  :else (transition r x target reason t)))
          r ids))
(defn- halt [r reason data]
  (if (get-in r [:elastic :halted]) r
    (-> r (assoc-in [:elastic :halted] (assoc data :reason reason)) (c/event :elastic-halted (assoc data :reason reason)))))
(defn- headroom
  "What the run limit leaves for children after the root floor; nil if unlimited."
  [r s k]
  (when-let [limit (get-in r [:config :limits k])]
    (- limit (get-in r [:spent k] 0) (get-in r [:reserved k] 0) (get-in s [:root-floor k] 0))))

(defn view [r id]
  (when-let [ch (child r id)]
    (-> (select-keys ch [:id :parent :depth :state :reason :quota :used :held :result :error :collected :worker])
        (assoc :pending (count (pending r id))))))

;; ---------------------------------------------------------------------------
;; Transitions: pure functions of the run ledger. Each throws on an illegal
;; transition and is applied inside one compare-and-set transaction.

(defn- caller-node [r caller]
  (if-let [ch (child r caller)]
    (do (when-not (= :running (:state ch)) (deny :caller-not-running {:caller caller}))
        {:depth (:depth ch) :task-root (:task-root ch) :elastic ch})
    (let [s (get-in r [:sessions caller])]
      (when-not (and s (not (c/terminal-statuses (:status s)))) (deny :caller-not-active {:caller caller}))
      {:depth (:depth s) :task-root (:task-root s)})))

(defn- quota-for [s spec parent t]
  (let [base {:calls (:child-calls s) :tokens (:child-tokens s) :usd (:child-usd s) :wall-ms (:child-wall-ms s)}
        asked (get spec :quota {})]
    (when-not (and (map? asked) (every? (set (keys base)) (keys asked))
                   (every? pos-int? (keep asked [:calls :tokens :wall-ms]))
                   (or (nil? (:usd asked)) (and (finite-nonneg? (:usd asked)) (pos? (:usd asked))))
                   (every? (fn [[k v]] (<= v (get base k))) asked))
      (deny :quota-schema {}))
    (let [quota (merge base asked)]
      (if-not parent
        quota
        (let [left (- (:deadline-ms parent) t)]
          (doseq [k [:calls :tokens :usd]]
            (when (> (get quota k) (- (get-in parent [:quota k]) (get-in parent [:used k]) (get-in parent [:held k])))
              (deny :quota-exceeds-parent {:resource k})))
          ;; The default wall time shrinks to the parent's remaining time; an
          ;; explicit request for more than that is refused.
          (when (or (< left 1) (and (:wall-ms asked) (> (:wall-ms asked) left)))
            (deny :quota-exceeds-parent {:resource :wall-ms}))
          (update quota :wall-ms min left))))))

(defn spawn
  "Admits one child. A repeated spawn with the same id, parent and spec is a
  no-op, so a retried request never reserves twice; any other reuse of an id is
  refused."
  [r caller spec t]
  (let [s (settings r)]
    (c/within-time! r)
    (when (get-in r [:elastic :halted]) (deny :halted {}))
    (when-not (and (map? spec) (every? spec-keys (keys spec)) (contains? spec :id) (contains? spec :task))
      (deny :spec-schema {}))
    (let [spec (merge {:context [] :profile :inherit} spec)
          {:keys [id task context profile]} spec
          hash (u/hash-value spec) prior (child r id)]
      (when-not (and (string? id) (re-matches id-pattern id)) (deny :child-id {}))
      (if prior
        (if (and (= caller (:parent prior)) (= hash (:spec-hash prior))) r (deny :conflicting-duplicate {:child id}))
        (let [_ (when (get-in r [:sessions id]) (deny :child-id {:child id}))
              _ (when-not (and (string? task) (<= 1 (count task) 8192)) (deny :task-size {}))
              _ (when-not (and (vector? context) (<= (count context) 8) (every? string? context)
                               (every? #(contains? (:contexts r) %) context))
                  (deny :context {}))
              _ (when-not (contains? (:profiles s) profile) (deny :unauthorized-profile {}))
              {:keys [depth task-root elastic]} (caller-node r caller)
              ;; A child never receives a context its parent was not granted.
              _ (when (and elastic (not (every? (set (get-in elastic [:spec :context])) context)))
                  (deny :context-amplification {}))
              depth (inc depth)
              _ (when (> depth (:max-depth s)) (deny :depth {}))
              siblings (in-root r task-root)
              _ (when (>= (count (filter #(or (active-states (:state %)) (= :unknown (:state %))) siblings)) (:max-active s))
                  (deny :active-limit {}))
              _ (when (>= (count siblings) (:max-children s)) (deny :child-limit {}))
              _ (when-let [room (headroom r s :calls)] (when (< room 1) (deny :run-budget {:resource :calls})))
              quota (quota-for s spec elastic t)
              deadline (min (+ t (:wall-ms quota)) (+ (:started-ms r) (get-in r [:config :limits :wall-ms])))
              zero {:calls 0 :tokens 0 :usd 0.0}]
          (-> r
              (assoc-in [:elastic :children id]
                        {:id id :parent caller :task-root task-root :depth depth :state :spawned :reason :spawned
                         :spec spec :spec-hash hash :quota quota :used zero :held zero
                         :created-ms t :changed-ms t :deadline-ms deadline :worker :none :collected false})
              (c/event :elastic-spawned {:child id :parent caller :depth depth :spec-hash hash
                                         :task-sha256 (u/sha task) :context context :profile profile :quota quota})))))))

(defn start [r id t]
  (settings r)
  (c/within-time! r)
  (when-not (= :spawned (:state (child r id))) (deny :not-spawned {:child id :state (:state (child r id))}))
  (transition r id :running :started t))

(defn admit-call
  "Reserves one provider call for a running child, atomically against the run
  limit less the root floor, and against every quota on the child's chain."
  [r id request-id tokens usd t]
  (let [s (settings r) ch (child r id)]
    (c/within-time! r)
    (when (get-in r [:elastic :halted]) (deny :halted {:child id}))
    (when-not ch (deny :missing-child {}))
    (when-not (= :running (:state ch)) (deny :not-running {:child id :state (:state ch)}))
    (when (>= t (:deadline-ms ch)) (deny :child-deadline {:child id}))
    (u/ensure! (and (string? request-id) (seq request-id) (pos-int? tokens) (finite-nonneg? usd)) "Invalid reservation" {})
    (when (or (get (requests r) request-id) (get-in r [:provider-requests request-id])) (deny :request-id-reused {}))
    (let [amounts {:calls 1 :tokens tokens :usd usd}]
      (doseq [x (elastic-chain r id) :let [a (child r x)] [k amount] amounts]
        (when (> (+ amount (get-in a [:used k]) (get-in a [:held k])) (get-in a [:quota k]))
          (deny :child-quota {:child x :resource k})))
      (doseq [[k amount] amounts :let [room (headroom r s k)] :when room]
        (when (> amount room) (deny :run-budget {:child id :resource k})))
      (-> r (update :reserved #(merge-with + % amounts))
          (add-chain id :held amounts)
          (assoc-in [:elastic :requests request-id] {:child id :tokens tokens :usd usd :status :pending})
          (c/event :elastic-call-admitted {:child id :request-id request-id :tokens tokens :usd usd})))))

(defn- after-call
  "A cancelling or expiring child reaches its terminal state when its last call ends."
  [r id t]
  (let [ch (child r id)]
    (if (and (= :cancelling (:state ch)) (empty? (pending r id)))
      (transition r id (:cancel-target ch) (:reason ch) t)
      r)))

(defn settle-call
  "Charges a call from its receipt. Settling an :unknown call is the operator's
  resolution: it charges what the receipt shows and fails the child."
  [r request-id {:keys [tokens usd] :as receipt} t]
  (settings r)
  (let [q (get (requests r) request-id) id (:child q)]
    (u/ensure! (#{:pending :unknown} (:status q)) "Request not pending" {})
    (u/ensure! (and (nat-int? tokens) (finite-nonneg? usd)) "Invalid usage" {})
    (let [held {:calls 1 :tokens (:tokens q) :usd (:usd q)} actual {:calls 1 :tokens tokens :usd usd}
          over (or (> tokens (:tokens q)) (> usd (:usd q)))
          r (-> r (update :reserved #(merge-with - % held)) (update :spent #(merge-with + % actual))
                (add-chain id :held (update-vals held -)) (add-chain id :used actual)
                (assoc-in [:elastic :requests request-id]
                          (assoc q :status :complete :overrun over
                                   :receipt (select-keys receipt [:tokens :usd :model :provider-id])))
                (c/event :elastic-call-settled {:child id :request-id request-id :tokens tokens :usd usd
                                                :overrun over :resolved-unknown (= :unknown (:status q))}))
          state (:state (child r id))]
      (cond
        over (-> r (assoc :status :budget-overrun) (halt :budget-overrun {:request-id request-id})
                 (cond-> (not (terminal-states state)) (transition id :failed :budget-overrun t)))
        (= :unknown state) (transition r id :failed :resolved-unknown t)
        :else (after-call r id t)))))

(defn release-call
  "Returns the reservation of a call that was provably never sent."
  [r request-id t]
  (settings r)
  (let [q (get (requests r) request-id) id (:child q)
        held {:calls 1 :tokens (:tokens q) :usd (:usd q)}]
    (u/ensure! (= :pending (:status q)) "Request not pending" {})
    (-> r (update :reserved #(merge-with - % held)) (add-chain id :held (update-vals held -))
        (assoc-in [:elastic :requests request-id :status] :not-dispatched)
        (c/event :elastic-call-released {:child id :request-id request-id})
        (after-call id t))))

(defn call-unknown
  "The call may or may not have run. Its reservation stays held, the child stops
  as :unknown, and no further elastic work is admitted in this task."
  [r request-id t]
  (settings r)
  (let [q (get (requests r) request-id) id (:child q)]
    (u/ensure! (= :pending (:status q)) "Request not pending" {})
    (-> r (assoc-in [:elastic :requests request-id :status] :unknown)
        (c/event :elastic-call-unknown {:child id :request-id request-id})
        (halt :provider-outcome-unknown {:request-id request-id})
        (cond-> (not (terminal-states (:state (child r id)))) (transition id :unknown :provider-outcome-unknown t)))))

(defn finish
  "The child's own end. A result that arrives after a cancel, a deadline or an
  unknown outcome is recorded as discarded and changes nothing else."
  [r id outcome {:keys [summary error]} t]
  (let [s (settings r) ch (child r id)]
    (u/ensure! (#{:completed :failed :budget-exhausted} outcome) "Invalid child outcome" {})
    (u/ensure! ch "Missing child" {})
    (if-not (= :running (:state ch))
      (c/event r :elastic-late-result-discarded {:child id :state (:state ch) :outcome outcome})
      (do
        (u/ensure! (empty? (pending r id)) "Child finished with a provider call in flight" {:child id})
        (u/ensure! (or (not= :completed outcome) (string? summary)) "A completed child needs a summary" {})
        ;; A child's end also ends its subtree: no descendant outlives it.
        (-> r (transition id outcome outcome t)
            (stop (sort (descendants r id)) :parent-finished :cancelled t)
            (cond-> (= :completed outcome)
              (assoc-in [:elastic :children id :result]
                        {:summary (subs summary 0 (min (count summary) (:result-chars s))) :chars (count summary)
                         :sha256 (u/sha summary) :truncated (> (count summary) (:result-chars s))})
              (not= :completed outcome)
              (assoc-in [:elastic :children id :error] (let [e (str error)] (subs e 0 (min 500 (count e)))))))))))

(defn request-cancel
  "Cancels a child and its whole subtree. Only an ancestor may cancel. A child
  with a call in flight moves to :cancelling and ends when the call ends;
  terminal and unknown children are untouched, so cancelling twice is harmless."
  [r caller id t]
  (settings r)
  (let [ch (child r id)]
    (when-not ch (deny :missing-child {}))
    (when-not (some #{caller} (lineage r id)) (deny :not-ancestor {:caller caller :child id}))
    (let [ids (into [id] (sort (descendants r id)))]
      (-> (stop r ids :cancelled :cancelled t)
          (c/event :elastic-cancel-requested {:by caller :child id :ids ids})))))

(defn expire [r t]
  (settings r)
  (let [due (sort (keep (fn [[id ch]] (when (and (#{:spawned :running} (:state ch)) (>= t (:deadline-ms ch))) id)) (children r)))]
    (if (empty? due) r
      (-> (stop r due :timed-out :timed-out t)
          (c/event :elastic-expired {:ids (vec due)})))))

(defn- parent-only [r caller id]
  (let [ch (child r id)]
    (when-not ch (deny :missing-child {}))
    (when-not (= caller (:parent ch)) (deny :not-parent {:caller caller :child id}))
    ch))

(defn collect [r caller id]
  (settings r)
  (let [ch (parent-only r caller id)]
    (if (and (terminal-states (:state ch)) (not (:collected ch)))
      (-> r (assoc-in [:elastic :children id :collected] true)
          (c/event :elastic-collected {:by caller :child id :state (:state ch)}))
      r)))

(defn status-view [r caller id]
  (settings r)
  (parent-only r caller id)
  (let [v (view r id)]
    (if (terminal-states (:state v)) v (assoc (dissoc v :result :error) :status :pending))))

(defn worker-lease [r id lease t]
  (settings r)
  (u/ensure! (#{:open :closed :close-failed} lease) "Invalid worker lease" {})
  (-> r (assoc-in [:elastic :children id :worker] lease)
      (c/event :elastic-worker {:child id :lease lease})
      (cond-> (= :close-failed lease) (halt :worker-cleanup-unconfirmed {:child id}))))

(defn recover
  "Exclusive restart, or a parent that is exiting. Calls in flight become
  :unknown and keep their reservations. Active children without a call become
  :orphaned. Workers never confirmed closed become :unconfirmed. Nothing is
  retried. Idempotent; a ledger with no elastic state is returned unchanged."
  [r reason t]
  (if-not (:elastic r) r
    (let [in-flight (vec (sort (keep (fn [[rid q]] (when (= :pending (:status q)) rid)) (requests r))))
          orphans (vec (sort (keep (fn [[id ch]] (when (and (active-states (:state ch)) (empty? (pending r id))) id))
                                   (children r))))
          open (vec (sort (keep (fn [[id ch]] (when (= :open (:worker ch)) id)) (children r))))
          report {:unknown in-flight :orphaned orphans :unconfirmed-workers open}]
      (if (every? empty? (vals report)) r
        (as-> (halt r reason report) r
          (reduce #(call-unknown %1 %2 t) r in-flight)
          (reduce #(transition %1 %2 :orphaned reason t) r orphans)
          (reduce #(assoc-in %1 [:elastic :children %2 :worker] :unconfirmed) r open)
          (c/event r :elastic-recovered (assoc report :reason reason)))))))

;; ---------------------------------------------------------------------------
;; Atomic wrappers. Correctness rests on the store's compare-and-set; the
;; in-process lock only spares concurrent children from retry storms.

(def ^:dynamic *serialize-writes* true)
(defonce ^:private write-locks (atom {}))
(defn- lock-for [store run]
  (let [k [(str store) run]] (get (swap! write-locks update k #(or % (Object.))) k)))
(defn- tx! [store run f]
  (if *serialize-writes* (locking (lock-for store run) (c/update-run! store run f)) (c/update-run! store run f)))
(defn- denying
  "Applies f; an elastic denial is also recorded as an event, for the
  experiment's count of refused actions. Refusals made while the switch is off
  carry no :elastic-denied and write nothing."
  [store run op f]
  (try (tx! store run f)
       (catch clojure.lang.ExceptionInfo e
         (when-let [reason (:elastic-denied (ex-data e))]
           (try (tx! store run #(c/event % :elastic-denied (merge {:op op :reason reason}
                                                                  (select-keys (ex-data e) [:child :caller :resource :state]))))
                (catch Exception _ nil)))
         (throw e))))

(defn spawn! [store run caller spec] (view (denying store run :spawn #(spawn % caller spec (now))) (:id spec)))
(defn start! [store run id] (tx! store run #(start % id (now))))
(defn admit-call! [store run id request-id tokens usd]
  (denying store run :call #(admit-call % id request-id tokens usd (now))))
(defn settle-call! [store run request-id receipt] (tx! store run #(settle-call % request-id receipt (now))))
(defn release-call! [store run request-id] (tx! store run #(release-call % request-id (now))))
(defn call-unknown! [store run request-id] (tx! store run #(call-unknown % request-id (now))))
(defn finish! [store run id outcome result] (tx! store run #(finish % id outcome result (now))))
(defn cancel! [store run caller id] (denying store run :cancel #(request-cancel % caller id (now))))
(defn expire! [store run] (tx! store run #(expire % (now))))
(defn collect! [store run caller id]
  (status-view (denying store run :collect #(collect % caller id)) caller id))
(defn status [store run caller id] (status-view (c/get-run store run) caller id))
(defn recover!
  "Run once, exclusively, when a controller process opens an existing ledger."
  [store run]
  (when (:elastic (c/get-run store run)) (tx! store run #(recover % :controller-restart (now)))))

;; ---------------------------------------------------------------------------
;; Executor: one thread per child. env holds :store :run, atoms :tasks and
;; :leases, and the injected :open-worker and :close-worker functions. A child
;; body gets {:id :task :context :worker :call! :stopping?} and returns {:summary s}.
;; Cancellation is cooperative: a provider call in flight is never interrupted,
;; so its outcome is never made ambiguous by the controller itself.

(defn- call-fn [store run id]
  (fn [tokens usd transport]
    (let [request-id (str (java.util.UUID/randomUUID))]
      (admit-call! store run id request-id tokens usd)
      (let [response (try (transport)
                          (catch Exception e
                            (if (= :not-dispatched (:outcome (ex-data e)))
                              (release-call! store run request-id)
                              (call-unknown! store run request-id))
                            (throw e)))]
        ;; A receipt that cannot be charged leaves the outcome unknown.
        (try (settle-call! store run request-id response)
             (catch Exception e (call-unknown! store run request-id) (throw e)))
        response))))

(defn- release-lease! [{:keys [store run leases close-worker]} id]
  (let [[old _] (swap-vals! leases dissoc id)]
    (when (contains? old id)
      (let [closed (try (close-worker (get old id)) true (catch Exception _ false))]
        (tx! store run #(worker-lease % id (if closed :closed :close-failed) (now)))))))

(defn- release-stopped! [env r]
  (doseq [[id ch] (children r) :when (or (terminal-states (:state ch)) (= :cancelling (:state ch)))]
    (release-lease! env id)))

(defn launch! [{:keys [store run tasks leases open-worker] :as env} id body]
  (start! store run id)
  (let [stopping? #(not= :running (:state (child (c/get-run store run) id)))
        f (future
            (let [[outcome result]
                  (try
                    (let [worker (open-worker id)]
                      (swap! leases assoc id worker)
                      (tx! store run #(worker-lease % id :open (now)))
                      (let [spec (:spec (child (c/get-run store run) id))
                            result (body {:id id :task (:task spec) :context (:context spec) :worker worker
                                          :call! (call-fn store run id) :stopping? stopping?})]
                        (u/ensure! (and (map? result) (string? (:summary result))) "Child body must return a summary" {})
                        [:completed result]))
                    (catch Exception e
                      [(if (budget-denials (:elastic-denied (ex-data e))) :budget-exhausted :failed)
                       {:error (.getMessage e)}]))]
              ;; Record the result first: confirming a real worker's removal can take
              ;; tens of seconds. Finishing also stops the child's subtree, so close
              ;; those workers too.
              (let [r (try (finish! store run id outcome result) (catch Exception _ (c/get-run store run)))]
                (release-lease! env id)
                (release-stopped! env r))
              outcome))]
    (swap! tasks assoc id f)
    f))

(defn cancel-child!
  "Cancels in the ledger, then closes the workers of every child that stopped."
  [{:keys [store run] :as env} caller id]
  (cancel! store run caller id)
  (release-stopped! env (c/get-run store run)))

(defn sweep!
  "Watchdog step: expires children past their deadline and closes their workers."
  [{:keys [store run] :as env}]
  (release-stopped! env (expire! store run)))

(defn await-child [{:keys [tasks]} id timeout-ms]
  (when-let [f (get @tasks id)] (deref f timeout-ms ::timeout)))

(defn shutdown!
  "Parent exit. Cancels the root's children, waits up to grace-ms in total, closes
  every worker lease, then marks calls still in flight :unknown and remaining
  active children :orphaned. Afterwards no child is active and no lease is open."
  [{:keys [store run tasks leases] :as env} root grace-ms]
  (doseq [[id ch] (children (c/get-run store run)) :when (and (= root (:parent ch)) (active-states (:state ch)))]
    (cancel! store run root id))
  (let [deadline (+ (now) grace-ms)]
    (doseq [[_ f] @tasks] (deref f (max 0 (- deadline (now))) nil)))
  (doseq [id (keys @leases)] (release-lease! env id))
  (let [r (tx! store run #(recover % :parent-exit (now)))]
    {:active (vec (keep (fn [[id ch]] (when (active-states (:state ch)) id)) (children r)))
     :unknown (vec (keep (fn [[id ch]] (when (= :unknown (:state ch)) id)) (children r)))
     :open-leases (vec (keys @leases))}))
