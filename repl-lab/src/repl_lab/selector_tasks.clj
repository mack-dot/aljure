(ns repl-lab.selector-tasks
  "New controller-owned selector tasks and reviewed capability definitions."
  (:require [repl-lab.util :as u] [repl-lab.artifact :as a] [repl-lab.fixtures :as f]
            [repl-lab.workloads :as workloads] [repl-lab.sim :as sim]))

(def version "selector-acquisition-v1")
(def retained-hash "834a4e02cd945ad6f889947c2ad4223e04a0bb175e4d7ba266329f2193a0e4d3")

;; These are initial tools, not learned candidates. They are available in every
;; condition. No task labels or branch recommendations appear in model prompts.
(f/fixture-function rank-jobs
  (fn [observation]
    (let [jobs (:jobs observation) by-id (into {} (map (juxt :id identity) jobs))
          children (fn [id] (filter (fn [j] (some (fn [d] (= d id)) (:deps j))) jobs))
          rank (fn rank [id] (+ (:estimate (get by-id id))
                               (reduce max 0 (map (fn [j] (rank (:id j))) (children id)))))]
      (vec (sort-by (fn [j] [(- (rank (:id j))) (:id j)]) (filter :ready jobs))))))
(f/fixture-function pack-ranked
  (fn [jobs workers memory]
    (let [[actions _]
          (reduce (fn [[actions workers] job]
                    (if-let [worker (first (sort-by (fn [w] [(- (:speed w)) (:id w)])
                                            (filter (fn [w] (and (:up w)
                                              (every? (fn [[r n]] (<= n (get (:available w) r 0)))
                                                      (:resources job)))) workers)))]
                      [(conj actions {:op :dispatch :job (:id job) :worker (:id worker)})
                       (mapv (fn [w] (if (= (:id w) (:id worker))
                                       (update w :available (fn [r] (merge-with - r (:resources job)))) w)) workers)]
                      [actions workers])) [[] workers] jobs)]
      {:actions (if (seq actions) actions [{:op :wait :ticks 1}]) :memory memory})))

(defn tool [category name arity source]
  (a/make-artifact {:category category :interface {:name name :arity arity} :source source
                   :dependencies [] :parent nil :author "reviewed-initial-selector-library"
                   :provenance :human-edit}))

(defn library []
  (let [original (a/verify (u/read-file (str "research/evidence/first-live-20261027/candidates/" retained-hash ".edn")))
        retained (tool :policy "retained-schedule" 2 (:source original))
        generic (tool :policy "general-schedule" 2 (:source f/packed-policy))
        rank (tool :analysis "rank-jobs" 1 (pr-str rank-jobs-form))
        pack (tool :analysis "pack-ranked" 3 (pr-str pack-ranked-form))
        artifacts [retained generic rank pack]
        descriptions [{:name "retained critical-path schedule"
                       :description "Rank ready jobs by estimated downstream work; pack onto fast CPU/memory workers."
                       :applicability {:required-job-resources [:cpu :mem] :supported-resources [:cpu :mem]}
                       :limitations ["Other resource keys are ignored; CPU and memory amounts must both be present."
                                     "The export name changed; source is byte-identical to the historical retained policy."]
                       :source-origin retained-hash}
                      {:name "general resource schedule"
                       :description "Order ready jobs by individual estimate and pack using every resource key."
                       :applicability {:resource-keys :arbitrary-positive-integers}
                       :limitations ["Does not rank downstream dependency work; not an optimal scheduler."]}
                      {:name "dependency rank"
                       :description "Return ready jobs ordered by estimated longest downstream dependency path."
                       :applicability {:graph :acyclic :estimates :positive}
                       :limitations ["Recursive ranking repeats shared subgraphs; large graphs can be costly."]}
                      {:name "resource packer"
                       :description "Dispatch ordered jobs onto available fast workers while checking all resource keys."
                       :applicability {:jobs :ordered :resources :positive-integers}
                       :limitations ["Uses the supplied job order; greedy packing is not guaranteed optimal."]}]
        registry (mapv (fn [artifact descriptor]
                         (merge descriptor {:version-hash (:hash artifact) :interface (:interface artifact)
                                            :category (:category artifact)
                                            :provenance (select-keys artifact [:author :provenance])
                                            :metadata-validation {:method :controller-source-review :version version}
                                            :validation-evidence :requires-current-isolated-library-control})) artifacts descriptions)
        workflow (a/make-artifact
                   {:category :workflow :interface {:name "selector-tools" :version 1}
                    :source (pr-str {:strategy {:policy (:hash generic) :context {:limit 64}}})
                    :dependencies (mapv :hash artifacts) :parent nil :author "controller"
                    :provenance :human-edit})]
    {:artifacts artifacts :registry registry :workflow workflow
     :retained (:hash retained) :compute (:hash generic) :rank (:hash rank) :pack (:hash pack)
     :hash (u/hash-value (mapv #(select-keys % [:hash :interface]) artifacts))}))

(defn cpu-memory-contract? [observation]
  (and (every? (fn [j] (and (= #{:cpu :mem} (set (keys (:resources j))))
                            (every? pos-int? (vals (:resources j))))) (:jobs observation))
       (every? #(every? (fn [key] (number? (get (:available %) key))) [:cpu :mem]) (:workers observation))))

(defn guard [library {:keys [observation]}]
  ;; Strong semantic control: checks required fields as well as unknown resources.
  ;; It combines the general packer with dependency ranking when reuse is unsafe.
  (if (cpu-memory-contract? observation) {:route :reuse :hash (:retained library)}
    {:route :compose :hashes [(:rank library) (:pack library)]}))

(defn composed [library hashes]
  (u/ensure! (= hashes [(:rank library) (:pack library)]) "Only the reviewed rank/pack composition is supported" {})
  (a/make-artifact {:category :policy :interface {:name "decide" :arity 2}
                   :source "(fn [observation memory] (pack-ranked (rank-jobs observation) (:workers observation) memory))"
                   :dependencies hashes :parent nil :author "controller-composition-template" :provenance :human-edit}))

;; The live panel uses independently drawn controller seeds and is frozen before
;; calls. These profiles declare mechanisms, not desired selector decisions.
(def profiles
  {:learning [{:structure :independent :size 6 :resource-mix true}
              {:structure :chain :size 7 :resource-mix true :resource :license}
              {:structure :fanout :size 8 :resource-mix false :omit-memory true}]
   :development [{:structure :layered :size 9 :resource-mix true :fault-count 1}
                 {:structure :independent :size 8 :resource-mix true :resource :bandwidth}
                 {:structure :chain :size 9 :resource-mix false :omit-memory true}]
   :heldout [{:structure :independent :size 9 :resource-mix true :fault-count 1}
             {:structure :fanout :size 11 :resource-mix true :resource :license :fault-count 1}
             {:structure :layered :size 12 :resource-mix true :omit-memory true :fault-count 1}
             {:structure :independent :size 10 :resource-mix true :resource :bandwidth :fault-count 1}]
   :coldboot [{:structure :chain :size 10 :resource-mix true :fault-count 1}
              {:structure :layered :size 13 :resource-mix true :resource :license :omit-memory true :fault-count 1}
              {:structure :chain :size 12 :resource-mix true :resource :bandwidth :fault-count 1}
              {:structure :fanout :size 14 :resource-mix true :resource :storage :fault-count 1}]})

(defn world [seed profile]
  (let [base (workloads/generate seed (merge {:fault-count 0} profile))
        extra (:resource profile)
        value (cond-> base
                (:omit-memory profile) (update :jobs #(mapv (fn [j] (update j :resources dissoc :mem)) %))
                extra (update :jobs #(mapv (fn [j] (assoc-in j [:resources extra] 1)) %))
                extra (update :workers #(mapv (fn [w] (if (= "w1" (:id w)) w
                                                        (assoc-in w [:capacity extra] 2))) %)))]
    (u/ensure! (and (empty? (sim/workload-errors value)) (sim/feasible? value)) "Invalid selector task" {}) value))

(defn generate-splits [seeds]
  (u/ensure! (= (count seeds) (reduce + (map count (vals profiles)))) "One independent seed per case required" {})
  (u/ensure! (= (count seeds) (count (set seeds))) "Selector splits must not share seeds" {})
  (loop [phases [:learning :development :heldout :coldboot] seeds seeds result {}]
    (if-let [phase (first phases)]
      (let [specs (profiles phase) [part rest] (split-at (count specs) seeds)]
        (recur (next phases) rest (assoc result phase (mapv world part specs)))) result)))
