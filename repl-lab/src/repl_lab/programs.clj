(ns repl-lab.programs
  "The controller half of the programmatic tool bridge (research/PROGRAMMATIC_EXECUTION.md).
  A program is model-written SCI code that performs controller operations through
  (tool \"name\" input) without each result returning to the model; only the program's final
  value does. Every operation is authorized here, against the frozen plan's grant: a tool is
  denied unless the grant lists it, reads and effects are distinguished, effects need a
  preapproval in the grant and an idempotency key in the call, budgets are enforced per
  operation, per tool, per program and per task, and every request, decision, result and
  error is recorded as an event. The worker never gains a capability: it can only ask."
  (:require [clojure.string :as str] [repl-lab.util :as u] [repl-lab.controller :as c]
            [repl-lab.service-fixture :as service]))

;; ---- the typed tools a program may ask for ------------------------------------------------

(defn- keys-ok! [input required optional what]
  (u/ensure! (map? input) (str what " input must be a map") {})
  (u/ensure! (and (every? (set (concat required optional)) (keys input)) (every? #(contains? input %) required))
             (str what " input takes " (pr-str (vec (concat required optional))) ", requiring " (pr-str (vec required))) {}))

(defn- service! [env]
  (or (get-in env [:programs :service]) (u/fail "No service is attached to this task" {})))

(def ^:private string-schema {:type "string"})
(def ^:private object-schema {:type "object"})

(def tools
  "name -> {:class :read or :effect, :required, :optional, :properties (JSON schema for the
  direct tools), :describe, :run (fn [env input])}. Reads change nothing outside the task;
  effects change the service's observable state."
  {"context_query"
   {:class :read :required [:handle] :optional [:offset :limit :select]
    :properties {:handle string-schema :offset {:type "integer" :minimum 0} :limit {:type "integer" :minimum 1 :maximum 64}
                 :select {:type "array" :items {:type "string" :enum ["line" "text"]}}}
    :describe "context_query {:handle \"context\" :offset n :limit 1-64 :select [:line :text]} returns {:total :records [{:line :text}]} of a context handle"
    :run (fn [env input] (keys-ok! input [:handle] [:offset :limit :select] "context_query")
           (u/ensure! (string? (:handle input)) "context_query needs a string handle" {})
           (c/context (:store env) (:run env) (:handle input)
                      (cond-> (dissoc input :handle)
                        (vector? (:select input)) (update :select #(mapv (fn [x] (if (string? x) (keyword x) x)) %)))))}
   "context_metadata"
   {:class :read :required [:handle] :optional [] :properties {:handle string-schema}
    :describe "context_metadata {:handle \"context\"} returns {:total} without records"
    :run (fn [env input] (keys-ok! input [:handle] [] "context_metadata")
           (dissoc (c/context (:store env) (:run env) (:handle input) {:limit 1 :select []}) :records))}
   "service_list"
   {:class :read :required [:collection] :optional [:offset :limit :where]
    :properties {:collection string-schema :offset {:type "integer" :minimum 0} :limit {:type "integer" :minimum 1 :maximum 50}
                 :where object-schema}
    :describe "service_list {:collection \"name\" :offset n :limit 1-50 :where {:field value}} returns {:total :items [records with :id]}"
    :run (fn [env input] (keys-ok! input [:collection] [:offset :limit :where] "service_list")
           (service/list! (service! env) input))}
   "service_get"
   {:class :read :required [:collection :id] :optional [] :properties {:collection string-schema :id string-schema}
    :describe "service_get {:collection \"name\" :id \"id\"} returns one record"
    :run (fn [env input] (keys-ok! input [:collection :id] [] "service_get")
           (service/get! (service! env) input))}
   "service_update"
   {:class :effect :required [:collection :id :fields :idempotency-key] :optional []
    :properties {:collection string-schema :id string-schema :fields object-schema :idempotency-key string-schema}
    :describe "service_update {:collection \"name\" :id \"id\" :fields {:field value} :idempotency-key \"unique\"} merges fields into one record (an effect) and returns it"
    :run (fn [env input] (keys-ok! input [:collection :id :fields :idempotency-key] [] "service_update")
           (service/update! (service! env) (dissoc input :idempotency-key)))}})

;; ---- the grant: what one frozen plan authorizes ---------------------------------------------

(def ceilings {:max-ops-per-program 1024 :max-ops-per-task 20000 :max-program-ms 600000 :max-programs 256 :max-calls 20000})
(def defaults {:max-ops-per-program 256 :max-ops-per-task 2000 :max-program-ms 60000 :max-programs 64})

(defn- setting [spec k]
  (let [v (get spec k (get spec (keyword (str/replace (name k) "-" "_")) (defaults k)))]
    (u/ensure! (and (pos-int? v) (<= v (ceilings k))) (str (name k) " must be 1-" (ceilings k)) {})
    v))

(defn grant
  "The validated grant from aljure_contract.programs: {:tools {name {:class :max-calls :approval}},
  :max-ops-per-program, :max-ops-per-task, :max-program-ms, :max-programs, :direct-tools,
  :program-tool}. Unknown tools, effects without preapproval and limits over the ceilings are
  refused, so a plan cannot authorize more than this namespace enforces."
  [spec]
  (u/ensure! (map? spec) "programs must be a map" {})
  (let [listed (or (:tools spec) [])
        _ (u/ensure! (and (vector? listed) (seq listed) (apply distinct? (map :name listed))) "programs.tools must list distinct tools" {})
        entries (for [{:keys [name approval] :as t} listed
                      :let [max-calls (setting (assoc t :max-calls (get t :max-calls (get t :max_calls 1000))) :max-calls)
                            tool (get tools name)]]
                  (do (u/ensure! tool (str "Unknown tool: " name) {})
                      (u/ensure! (every? #{:name :max_calls :max-calls :approval} (keys t)) (str "Tool entry takes name, max_calls, approval: " name) {})
                      (u/ensure! (or (= :read (:class tool)) (= "preapproved" approval))
                                 (str "Effect tool needs approval \"preapproved\" in the plan: " name) {})
                      (u/ensure! (or (nil? approval) (= "preapproved" approval)) (str "Unknown approval: " approval) {})
                      [name (cond-> {:class (:class tool) :max-calls max-calls} approval (assoc :approval approval))]))
        program-tool (get spec :program-tool (get spec :program_tool true))
        direct-tools (get spec :direct-tools (get spec :direct_tools false))]
    (u/ensure! (and (boolean? program-tool) (boolean? direct-tools) (or program-tool direct-tools))
               "programs needs program_tool and/or direct_tools true" {})
    {:tools (into (sorted-map) entries)
     :max-ops-per-program (setting spec :max-ops-per-program) :max-ops-per-task (setting spec :max-ops-per-task)
     :max-program-ms (setting spec :max-program-ms) :max-programs (setting spec :max-programs)
     :program-tool program-tool :direct-tools direct-tools}))

(defn state
  "Per-task accounting, created once with the grant."
  []
  (atom {:ops 0 :programs 0 :calls {} :idempotency {}}))

(defn attach
  "The env entry for a task: {:programs {:grant :state :service}}. The service fixture is
  optional (context-only tasks)."
  [spec fixture]
  (let [g (grant spec)
        service? #(str/starts-with? % "service_")
        unavailable (when-not fixture (filterv service? (keys (:tools g))))]
    ;; A grant is a ceiling, not a promise: a task that carries no service fixture has no service,
    ;; so its service_* tools are neither advertised nor callable. The omission is recorded.
    {:grant (cond-> g (seq unavailable) (-> (update :tools #(apply dissoc % unavailable))
                                            (assoc :unavailable unavailable)))
     :state (state) :service (when fixture (service/open fixture))}))

(defn narrow
  "The task's effective [config programs]: when attach dropped tools the task cannot serve, the
  config's grant loses them too, so the model is offered exactly the tools the task enforces.
  A task left with no tools has no programs at all: no program tools are advertised."
  [config programs]
  (let [unavailable (set (get-in programs [:grant :unavailable]))
        listed (get-in config [:contract :programs :tools])
        remaining (vec (remove #(unavailable (:name %)) listed))]
    (cond (empty? unavailable) [config programs]
          (empty? remaining) [(update config :contract dissoc :programs) nil]
          :else [(assoc-in config [:contract :programs :tools] remaining) programs])))

;; ---- one operation --------------------------------------------------------------------------

(def result-bound 60000)

(defn- event! [{:keys [store run]} type payload] (c/update-run! store run #(c/event % type payload)))

(defn operate!
  "Authorizes and performs one operation for a session, recording it, and returns
  {:tool-result v} or {:tool-error message}. Used by the bridge handler (programs) and by the
  direct tools (one operation per model turn), so both paths share one authorization."
  [env session {:keys [seq name input] :as request} origin]
  (let [{:keys [grant state]} (:programs env)
        tool (get tools name) policy (get-in grant [:tools name])
        begin (System/nanoTime)
        base {:session session :origin origin :seq seq :name name :class (:class tool)
              :input-sha256 (u/hash-value input)}
        record! (fn [decision outcome]
                  (event! env :program-op (merge base {:decision decision :elapsed-ms (/ (- (System/nanoTime) begin) 1e6)} outcome)))
        deny (fn [decision message] (record! decision {:status :error :error message}) {:tool-error message})]
    (try
      (u/ensure! (and grant state) "Programs are not enabled in this task" {})
      (u/ensure! (and tool policy) (str "Tool is not authorized: " name) {})
      (u/ensure! (map? input) "Tool input must be a map" {})
      (u/ensure! (< (:ops @state) (:max-ops-per-task grant)) "Task operation budget exhausted" {})
      (u/ensure! (< (get-in @state [:calls name] 0) (:max-calls policy)) (str "Call budget exhausted for " name) {})
      (swap! state #(-> % (update :ops inc) (update-in [:calls name] (fnil inc 0))))
      (let [key (:idempotency-key input)
            effect? (= :effect (:class tool))
            earlier (when effect? (get-in @state [:idempotency key]))]
        (when effect?
          (u/ensure! (= "preapproved" (:approval policy)) (str "Effect is not preapproved: " name) {})
          (u/ensure! (and (string? key) (<= 1 (count key) 128)) "An effect needs :idempotency-key, a string of 1-128 characters" {}))
        (cond
          (= :ok (:status earlier))
          (do (record! :deduplicated {:status :ok :result-sha256 (u/hash-value (:result earlier)) :acted false})
              {:tool-result (:result earlier)})

          (= :uncertain (:status earlier))
          (deny :uncertain-not-retried (str "The outcome of key " key " is uncertain; it is not repeated. Verify with a read."))

          :else
          (let [outcome (try {:result ((:run tool) env input)}
                             (catch clojure.lang.ExceptionInfo e
                               (if (:uncertain (ex-data e)) {:uncertain (.getMessage e)} {:error (.getMessage e)}))
                             (catch Exception e {:error (.getMessage e)}))]
            (cond
              (:uncertain outcome)
              (do (swap! state assoc-in [:idempotency key] {:status :uncertain})
                  (deny :uncertain (str "Outcome uncertain: " (:uncertain outcome) ". The operation may have been applied; it is not repeated. Verify with a read.")))

              (:error outcome) (deny :allowed (str (:error outcome)))

              :else
              (let [result (:result outcome) wire (pr-str {:tool-result result})
                    bytes (count (.getBytes wire "UTF-8"))]
                (if (> bytes result-bound)
                  (deny :allowed (str "Tool result too large (" bytes " bytes; at most " result-bound "); request a smaller slice"))
                  (do (when effect? (swap! state assoc-in [:idempotency key] {:status :ok :result result}))
                      (record! :allowed {:status :ok :result-bytes bytes :result-sha256 (u/hash-value result) :acted true})
                      {:tool-result result})))))))
      (catch Exception e (deny :denied (str (.getMessage e)))))))

(defn handler
  "The bridge handler for one program: each worker request is one operation, under the
  program's time budget."
  [env session program started-ns]
  (fn [request]
    (let [elapsed (/ (- (System/nanoTime) started-ns) 1e6)]
      (if (> elapsed (get-in env [:programs :grant :max-program-ms]))
        (do (event! env :program-op {:session session :origin program :seq (:seq request) :name (:name request)
                                     :decision :denied :status :error :error "Program time budget exhausted" :elapsed-ms 0.0})
            {:tool-error "Program time budget exhausted"})
        (operate! env session request program)))))

(defn run-program!
  "Runs one program for a session through evaluate, a (fn [source bindings tools handler])
  the broker supplies with its worker already chosen; returns the program's value."
  [env session source bindings evaluate]
  (let [{:keys [grant state]} (:programs env)]
    (u/ensure! (and grant state (:program-tool grant)) "Programs are not enabled in this task" {})
    (u/ensure! (< (:programs @state) (:max-programs grant)) "Program count budget exhausted" {})
    (let [n (:programs (swap! state update :programs inc)) program (str session "/program-" n)
          remaining (- (:max-ops-per-task grant) (:ops @state))
          tools {:allow (set (keys (:tools grant))) :max-ops (max 1 (min (:max-ops-per-program grant) remaining))}
          before (:ops @state) started (System/nanoTime)
          finish! (fn [status extra]
                    (event! env :program-finished (merge {:session session :program program :status status
                                                          :ops (- (:ops @state) before)
                                                          :elapsed-ms (/ (- (System/nanoTime) started) 1e6)} extra)))]
      (event! env :program-started {:session session :program program :source-sha256 (u/sha source)
                                    :allow (vec (sort (:allow tools))) :max-ops (:max-ops tools)})
      (try (let [value (evaluate source bindings tools (handler env session program started))]
             (finish! :ok {})
             value)
           (catch Exception e (finish! :error {:error (.getMessage e)}) (throw e))))))

(defn direct!
  "A direct tool call from the model (one operation per turn, the conventional path): the
  same authorization and record as a program's operation. Returns the broker result."
  [env session name input]
  (u/ensure! (get-in env [:programs :grant :direct-tools]) "Direct tools are not enabled in this task" {})
  (let [seq (inc (get-in @(get-in env [:programs :state]) [:ops] 0))
        reply (operate! env session {:seq seq :name name :input input} "direct")]
    (if (contains? reply :tool-result) {:value (:tool-result reply)} (u/fail (:tool-error reply) {}))))

;; ---- what the model is told ------------------------------------------------------------------

(defn describe
  "The grant as text for the program_run tool description: deterministic for one plan."
  [grant]
  (str (str/join "; " (for [[name policy] (:tools grant)]
                        (str (:describe (tools name)) " [" (clojure.core/name (:class policy)) ", at most " (:max-calls policy) " calls per task]")))
       ". Limits: " (:max-ops-per-program grant) " operations per program, " (:max-ops-per-task grant)
       " per task, " (:max-program-ms grant) " ms per program, " (:max-programs grant) " programs per task."))

(defn direct-tool-names [grant] (when (:direct-tools grant) (vec (keys (:tools grant)))))
