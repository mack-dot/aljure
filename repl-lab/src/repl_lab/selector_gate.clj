(ns repl-lab.selector-gate
  "Controller-only development acceptance. No final/held-out outcomes are inputs."
  (:require [repl-lab.util :as u] [repl-lab.artifact :as a] [repl-lab.model-protocol :as wire]
            [repl-lab.sim :as sim] [repl-lab.executable :as executable] [repl-lab.limits :as limits]
            [repl-lab.selector-accounting :as accounting]))

(def version "selector-development-gate-v1")
(def controls #{:deterministic-reuse :descriptive-discovery :applicability-guard})
(defn infrastructure-failure? [row]
  (and (:failure-stage row)
       (not= :algorithm (:failure-stage row))
       (not (and (#{:code-loading :execution :route-generation} (:failure-stage row))
                 (#{:code-rejection :algorithm-or-contract} (:failure-kind row))))))
(defn public-input [world registry]
  ;; sim/observe omits actual durations, future faults, seeds and evaluator state.
  {:observation (sim/observe (sim/initial-state world) nil)
   :skills (mapv #(select-keys % [:name :description :interface :applicability :version-hash :limitations]) registry)})

(defn decision!
  ([value approved] (decision! value approved 1))
  ([value approved contract-version]
  (u/ensure! (map? value) "Selector must return a decision map" {})
  (u/ensure! ((cond-> #{:reuse :compute :delegate :adapt :synthesize} (= 2 contract-version) (conj :compose)) (:route value)) "Unsupported selector route" {})
  (u/ensure! (= (set (keys value)) (case (:route value) :reuse #{:route :hash} :compose #{:route :hashes} #{:route})) "Selector output schema differs" {})
  (when (= :reuse (:route value)) (u/ensure! (contains? approved (:hash value)) "Selector chose unapproved skill" {}))
  (when (= :compose (:route value))
    (u/ensure! (and (vector? (:hashes value)) (= 2 (count (:hashes value)))
                    (= 2 (count (set (:hashes value)))) (every? approved (:hashes value))) "Unapproved or invalid composition" {}))
  value))

(defn authored? [candidate ledger]
  (and (= :model-generated (:provenance candidate)) (= :live (get-in ledger [:config :mode]))
       (some #(and (= :artifact-staged (:type %)) (= (:hash candidate) (get-in % [:payload :hash]))
                   (= (:author candidate) (get-in % [:payload :session]))) (:events ledger))
       (some (fn [[_ request]]
               (let [response (:response request)]
                 (and (= :complete (:status request)) (= (:author candidate) (:session request))
                      (= :recorded-model-run (:provenance response))
                      (= "claude-sonnet-5-5" (:model response) (:requested-model response))
                      (try
                        (let [cmd (wire/parse-command (:config ledger) (:text response))]
                          (and (= :artifact/submit (:op cmd))
                               (= candidate (a/make-artifact
                                              (assoc (dissoc cmd :op) :author (:session request)
                                                     :provenance :model-generated)))))
                        (catch Exception _ false))))) (:provider-requests ledger))))

(defn cost! [ledger]
  (u/ensure! (map? ledger) "Missing independent usage ledger" {})
  (u/ensure! (every? zero? (vals (:reserved ledger))) "Unresolved usage reservations" {})
  (reduce (fn [total [_ request]]
            (let [usd (get-in request [:response :usd])]
              (u/ensure! (and (= :complete (:status request)) (number? usd)
                              (Double/isFinite (double usd)) (<= 0 usd)) "Incomplete provider usage" {})
              (+ total usd))) 0.0 (:provider-requests ledger)))

(defn verified-row!
  ([world row] (verified-row! world row 1))
  ([world row contract-version]
  (let [episode (:episode row)
        state (sim/replay world (:records episode) (:final-hash episode) (get-in episode [:metrics :status]))
        metrics (sim/metrics state)
        keys [:status :completed :makespan :score :accepted-invariant-violations]]
    (u/ensure! (= (select-keys metrics keys) (select-keys (:metrics episode) keys)) "Evaluator metrics disagree with replay" {})
    {:case (u/hash-value world) :metrics (select-keys metrics keys)
     :failure-stage (:failure-stage row) :failure-kind (:failure-kind row)
     :invocations (:invocations row)
     :usd ((if (= 2 contract-version) accounting/cost! cost!) (:ledger row))})))

(defn adjudicate-development! [{:keys [root candidate authoring-ledger mode development-worlds registry
                          control-decisions control-executors execute-route config acquisition-ledgers]}]
  (a/verify candidate)
  (u/ensure! (#{:fixture :live} mode) "Explicit evidence mode required" {})
  (u/ensure! (and (= :analysis (:category candidate))
                  (= {:name "select-route" :arity 1} (:interface candidate))
                  (empty? (:dependencies candidate))) "Invalid selector interface" {})
  (u/ensure! (= (cond-> controls (= 2 (:selector-gate-version config)) (conj :fresh-synthesis :always-compose))
                 (set (keys (or control-executors control-decisions)))) "All simpler development controls are required" {})
  (u/ensure! (seq development-worlds) "Empty development panel" {})
  (u/ensure! (= (mapv u/hash-value development-worlds) (:development-case-hashes config))
             "Development worlds differ from the controller's fixed panel" {})
  (when (= mode :live) (u/ensure! (authored? candidate authoring-ledger) "No matching real model authorship receipt" {}))
  (a/save! root candidate)
  (let [controls (cond-> controls (= 2 (:selector-gate-version config)) (conj :fresh-synthesis :always-compose))
        contract-version (get config :selector-gate-version 1)
        approved (set (map :version-hash registry))
        rows (mapv (fn [world]
                     (let [public (public-input world registry)
                           options (update (limits/fresh config) :deadline-ms min (get config :acquisition-deadline-ms Long/MAX_VALUE))
                           ;; The selector gets only public, whitelisted data in isolated SCI.
                           selected (decision! (executable/invoke! root candidate [public] (:deadline-ms options)) approved contract-version)
                           candidate-row (verified-row! world (execute-route selected world options) contract-version)
                           comparisons (into {} (for [name controls]
                                                  [name (verified-row! world
                                                          (if-let [execute (get control-executors name)]
                                                            (execute public world (limits/fresh config))
                                                            (execute-route (decision! ((get control-decisions name) public) approved contract-version)
                                                                           world (limits/fresh config))) contract-version)]))]
                       {:candidate candidate-row :controls comparisons :decision selected
                        :selector-input-hash (u/hash-value public)})) development-worlds)
        infrastructure? (some #(some (fn [row] (if (= 2 contract-version) (infrastructure-failure? row)
                                                (and (:failure-stage row) (not= :algorithm (:failure-stage row)))))
                                     (cons (:candidate %) (vals (:controls %)))) rows)
        costs (into {} (for [control controls] [control (reduce + (map #(get-in % [:controls control :usd]) rows))]))
        cost-fn (if (= 2 contract-version) accounting/cost! cost!)
        candidate-execution-usd (reduce + (map #(get-in % [:candidate :usd]) rows))
        acquisition-usd (+ (cost-fn authoring-ledger) (reduce + 0.0 (map cost-fn acquisition-ledgers))
                          ;; Validation is part of acquisition, including fixed control calls.
                          (if (= 2 contract-version) (+ candidate-execution-usd (reduce + (vals costs))) 0.0))
        horizon (if (= 2 contract-version) (:amortization-tasks config) (count rows))
        _ (u/ensure! (pos-int? horizon) "Declare a positive amortization horizon before evaluation" {})
        candidate-usd (+ (* acquisition-usd (/ (count rows) horizon)) candidate-execution-usd)
        score (fn [which] (reduce + (map #(get-in % (conj which :metrics :score)) rows)))
        safe? (every? #(zero? (get-in % [:candidate :metrics :accepted-invariant-violations])) rows)
        no-regression? (every? (fn [{:keys [candidate controls]}]
                                (every? (fn [control]
                                          (and (>= (get-in candidate [:metrics :completed]) (get-in control [:metrics :completed]))
                                               (<= (get-in candidate [:metrics :score]) (get-in control [:metrics :score])))) (vals controls))) rows)
        cheaper-than-directed? (< candidate-usd (:descriptive-discovery costs))
        beats-guard? (or (< (score [:candidate]) (score [:controls :applicability-guard]))
                        (< candidate-usd (:applicability-guard costs)))
        beats-constant? (or (= 1 contract-version) (< (score [:candidate]) (score [:controls :always-compose]))
                            (< candidate-usd (:always-compose costs)))
        accepted? (and (not infrastructure?) safe? no-regression? cheaper-than-directed? beats-guard? beats-constant?)
        receipt {:version (if (= 2 contract-version) "selector-development-gate-v2" version)
                 :candidate (:hash candidate) :evidence-category (if (= mode :fixture) :FIXTURE :LIVE-MODEL-DEVELOPMENT)
                 :status (cond infrastructure? :unverified-infrastructure
                               (= mode :fixture) (if accepted? :fixture-accepted :fixture-rejected)
                               accepted? :accepted :else :rejected)
                 :independent-authorship (boolean (authored? candidate authoring-ledger))
                 :safe safe? :no-regression no-regression? :cheaper-than-directed cheaper-than-directed?
                 :beats-applicability-guard beats-guard? :candidate-amortized-usd candidate-usd :control-usd costs
                 :beats-always-compose beats-constant?
                 :acquisition-usd acquisition-usd :amortization-tasks horizon
                 :cost-claim (if (= 2 contract-version) :PROJECTED-PAYBACK-NOT-MEASURED-TRANSFER :development-only)
                 :development rows :held-out-result :NOT-RUN :active-library-changed false}
        receipt (assoc receipt :evidence-hash (u/hash-value receipt))]
    ;; No model tool exposes this function; no active artifact changes here.
    (u/write-edn! (str root "/selector-decision.edn") receipt)
    (u/write-json! (str root "/selector-decision.json") receipt)
    receipt))

(defn adjudicate! [{:keys [root candidate mode] :as options}]
  ;; Preserve failures too. A failed worker/receipt/schema check is never improvement.
  (try (adjudicate-development! options)
       (catch Exception e
         (let [receipt {:version version :candidate (:hash candidate) :status :validation-error
                        :evidence-category (if (= :fixture mode) :FIXTURE :UNVERIFIED)
                        :error (.getMessage e) :active-library-changed false :held-out-result :NOT-RUN}]
           (u/write-edn! (str root "/selector-rejected-input.edn") candidate)
           (u/write-json! (str root "/selector-decision.json") receipt)
           receipt))))

(defn finalize-acquisition
  "Recompute projected payback after all acquisition calls, including validation
   and post-feedback authoring. Does not rerun or select hidden outcomes."
  [receipt total-acquisition-usd]
  (u/ensure! (and (= "selector-development-gate-v2" (:version receipt))
                  (accounting/finite-nonnegative? total-acquisition-usd)
                  (>= (+ total-acquisition-usd 1e-9) (:acquisition-usd receipt)))
             "Final acquisition accounting differs" {})
  (let [rows (:development receipt) costs (:control-usd receipt)
        projected (+ (* total-acquisition-usd (/ (count rows) (:amortization-tasks receipt)))
                     (reduce + (map #(get-in % [:candidate :usd]) rows)))
        quality-gain (< (reduce + (map #(get-in % [:candidate :metrics :score]) rows))
                        (reduce + (map #(get-in % [:controls :applicability-guard :metrics :score]) rows)))
        cheaper (< projected (:descriptive-discovery costs))
        beats-guard (or quality-gain (< projected (:applicability-guard costs)))
        beats-constant (or (< (reduce + (map #(get-in % [:candidate :metrics :score]) rows))
                             (reduce + (map #(get-in % [:controls :always-compose :metrics :score]) rows)))
                           (< projected (:always-compose costs)))
        pass? (and (:safe receipt) (:no-regression receipt) cheaper beats-guard beats-constant)
        result (-> receipt (dissoc :evidence-hash)
                   (assoc :acquisition-usd total-acquisition-usd :candidate-amortized-usd projected
                          :cost-claim :PROJECTED-PAYBACK-NOT-MEASURED-TRANSFER
                          :cheaper-than-directed cheaper :beats-applicability-guard beats-guard :beats-always-compose beats-constant)
                   (update :status #(case % :accepted (if pass? :accepted :rejected)
                                          :fixture-accepted (if pass? :fixture-accepted :fixture-rejected) %)))]
    (assoc result :evidence-hash (u/hash-value result))))
