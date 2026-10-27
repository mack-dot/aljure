(ns repl-lab.selector-gate
  "Controller-only development acceptance. No final/held-out outcomes are inputs."
  (:require [repl-lab.util :as u] [repl-lab.artifact :as a] [repl-lab.model-protocol :as wire]
            [repl-lab.sim :as sim] [repl-lab.executable :as executable] [repl-lab.limits :as limits]))

(def version "selector-development-gate-v1")
(def controls #{:deterministic-reuse :descriptive-discovery :applicability-guard})
(defn public-input [world registry]
  ;; sim/observe omits actual durations, future faults, seeds and evaluator state.
  {:observation (sim/observe (sim/initial-state world) nil)
   :skills (mapv #(select-keys % [:name :description :interface :applicability :version-hash :limitations]) registry)})

(defn decision! [value approved]
  (u/ensure! (map? value) "Selector must return a decision map" {})
  (u/ensure! (#{:reuse :compute :delegate :adapt :synthesize} (:route value)) "Unsupported selector route" {})
  (u/ensure! (= (set (keys value)) (if (= :reuse (:route value)) #{:route :hash} #{:route})) "Selector output schema differs" {})
  (when (= :reuse (:route value)) (u/ensure! (contains? approved (:hash value)) "Selector chose unapproved skill" {}))
  value)

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

(defn verified-row! [world row]
  (let [episode (:episode row)
        state (sim/replay world (:records episode) (:final-hash episode) (get-in episode [:metrics :status]))
        metrics (sim/metrics state)
        keys [:status :completed :makespan :score :accepted-invariant-violations]]
    (u/ensure! (= (select-keys metrics keys) (select-keys (:metrics episode) keys)) "Evaluator metrics disagree with replay" {})
    {:case (u/hash-value world) :metrics (select-keys metrics keys)
     :failure-stage (:failure-stage row) :usd (cost! (:ledger row))}))

(defn adjudicate-development! [{:keys [root candidate authoring-ledger mode development-worlds registry
                          control-decisions execute-route config]}]
  (a/verify candidate)
  (u/ensure! (#{:fixture :live} mode) "Explicit evidence mode required" {})
  (u/ensure! (and (= :analysis (:category candidate))
                  (= {:name "select-route" :arity 1} (:interface candidate))
                  (empty? (:dependencies candidate))) "Invalid selector interface" {})
  (u/ensure! (= controls (set (keys control-decisions))) "All simpler development controls are required" {})
  (u/ensure! (seq development-worlds) "Empty development panel" {})
  (u/ensure! (= (mapv u/hash-value development-worlds) (:development-case-hashes config))
             "Development worlds differ from the controller's fixed panel" {})
  (when (= mode :live) (u/ensure! (authored? candidate authoring-ledger) "No matching real model authorship receipt" {}))
  (a/save! root candidate)
  (let [approved (set (map :version-hash registry))
        rows (mapv (fn [world]
                     (let [public (public-input world registry)
                           options (limits/fresh config)
                           ;; The selector gets only public, whitelisted data in isolated SCI.
                           selected (decision! (executable/invoke! root candidate [public] (:deadline-ms options)) approved)
                           candidate-row (verified-row! world (execute-route selected world options))
                           comparisons (into {} (for [[name choose] control-decisions]
                                                  [name (verified-row! world
                                                          (execute-route (decision! (choose public) approved) world (limits/fresh config)))]))]
                       {:candidate candidate-row :controls comparisons :decision selected
                        :selector-input-hash (u/hash-value public)})) development-worlds)
        infrastructure? (some #(some (fn [row] (and (:failure-stage row) (not= :algorithm (:failure-stage row))))
                                     (cons (:candidate %) (vals (:controls %)))) rows)
        candidate-usd (+ (cost! authoring-ledger) (reduce + (map #(get-in % [:candidate :usd]) rows)))
        costs (into {} (for [control controls] [control (reduce + (map #(get-in % [:controls control :usd]) rows))]))
        score (fn [which] (reduce + (map #(get-in % (conj which :metrics :score)) rows)))
        safe? (every? #(zero? (get-in % [:candidate :metrics :accepted-invariant-violations])) rows)
        no-regression? (every? (fn [{:keys [candidate controls]}]
                                (every? (fn [control]
                                          (and (>= (get-in candidate [:metrics :completed]) (get-in control [:metrics :completed]))
                                               (<= (get-in candidate [:metrics :score]) (get-in control [:metrics :score])))) (vals controls))) rows)
        cheaper-than-directed? (< candidate-usd (:descriptive-discovery costs))
        beats-guard? (or (< (score [:candidate]) (score [:controls :applicability-guard]))
                        (< candidate-usd (:applicability-guard costs)))
        accepted? (and (not infrastructure?) safe? no-regression? cheaper-than-directed? beats-guard?)
        receipt {:version version :candidate (:hash candidate) :evidence-category (if (= mode :fixture) :FIXTURE :LIVE-MODEL-DEVELOPMENT)
                 :status (cond infrastructure? :unverified-infrastructure
                               (= mode :fixture) (if accepted? :fixture-accepted :fixture-rejected)
                               accepted? :accepted :else :rejected)
                 :independent-authorship (boolean (authored? candidate authoring-ledger))
                 :safe safe? :no-regression no-regression? :cheaper-than-directed cheaper-than-directed?
                 :beats-applicability-guard beats-guard? :candidate-amortized-usd candidate-usd :control-usd costs
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
