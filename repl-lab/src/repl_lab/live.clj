(ns repl-lab.live
  (:require [clojure.java.io :as io] [clojure.string :as str] [repl-lab.util :as u]
            [repl-lab.isolation :as iso] [repl-lab.controller :as c] [repl-lab.artifact :as a]
            [repl-lab.fixtures :as f] [repl-lab.workloads :as w] [repl-lab.sim :as sim]
            [repl-lab.runtime :as runtime] [repl-lab.provider :as provider]
            [repl-lab.bundle :as bundle] [repl-lab.experiment :as experiment]))

(defn positive-number [value label]
  (let [n (try (Double/parseDouble (or value "")) (catch Exception _ 0.0))]
    (u/ensure! (and (Double/isFinite n) (pos? n)) (str "Positive " label " is required") {}) n))
(defn options [env]
  (u/ensure! (= "1" (get env "LIVE")) "Paid calls are disabled. Set LIVE=1 with an explicit model and cap." {})
  (let [model (get env "MODEL") cap (positive-number (get env "MAX_USD") "MAX_USD")]
    (u/ensure! (and (seq model) (not (str/ends-with? model "latest"))) "Set a pinned MODEL identifier" {})
    {:model model :cap cap
     :input-rate (positive-number (get env "INPUT_USD_PER_M") "INPUT_USD_PER_M")
     :output-rate (positive-number (get env "OUTPUT_USD_PER_M") "OUTPUT_USD_PER_M")
     :api-key (get env "ANTHROPIC_API_KEY")}))

(defn dependency-closure [registry artifact]
  (letfn [(visit [item stack]
            (u/ensure! (not (contains? stack (:hash item))) "Dependency cycle" {})
            (vec (mapcat (fn [hash] (let [dep (a/load! registry hash)]
                                     (conj (visit dep (conj stack (:hash item))) dep))) (:dependencies item))))]
    (vec (distinct (visit artifact #{})))))

(defn run-policy!
  ([artifact world] (run-policy! artifact world []))
  ([artifact world dependencies]
  (let [worker (iso/open-session!) begin (System/nanoTime)]
    (try
      (a/verify artifact)
      (u/ensure! (= :policy (:category artifact)) "Expected policy" {})
      (doseq [dependency dependencies]
        (a/verify dependency)
        (u/ensure! (#{:analysis :policy} (:category dependency)) "Function dependency required" {})
        (iso/evaluate! worker (str "(do (def " (get-in dependency [:interface :name]) " " (:source dependency) ") nil)") {}))
      (iso/evaluate! worker (str "(do (def policy " (:source artifact) ") nil)") {})
      (let [result (sim/run-episode world
                     (fn [obs memory] (iso/evaluate! worker "(policy observation memory)" {:observation obs :memory memory}))
                     {:event-budget 10000})]
        (assoc result :wall-ms (/ (- (System/nanoTime) begin) 1000000.0)))
      (finally (iso/close-session! worker))))))

(defn development-panel! [store id registry policy-hash worlds]
  (c/consume! store id :evaluation-episodes (count worlds))
  (let [artifact (a/load! registry policy-hash) dependencies (dependency-closure registry artifact)]
    (mapv (fn [world]
            ;; Every failure remains a scored case, including isolation timeout.
            (try (let [run (run-policy! artifact world dependencies)
                       handle (str "trace-" policy-hash "-" (u/hash-value world))
                       records (mapv #(select-keys % [:type :action :accepted :error :observation :response]) (:records run))]
                   (c/put-context! store id handle records)
                   (c/update-run! store id #(update-in % [:contexts "trace-index"] (fnil conj [])
                                                       {:handle handle :artifact policy-hash :records (count records)}))
                   (c/update-run! store id #(c/event % :development-episode
                                                   {:artifact policy-hash :case (u/hash-value world)
                                                    :metrics (:metrics run) :wall-ms (:wall-ms run)}))
                   (assoc (:metrics run) :case (u/hash-value world)))
                 (catch Exception e
                   (let [failure {:case (u/hash-value world) :completed 0 :makespan nil :status :execution-failure
                                  :accepted-invariant-violations 0 :score (* (:horizon world) (inc (count (:jobs world))))
                                  :error (.getMessage e)}]
                     (c/update-run! store id #(c/event % :development-failure {:artifact policy-hash :result failure}))
                     failure)))) worlds)))

(defn evolve! [env]
  (let [{:keys [model cap input-rate output-rate api-key] :as options} (options env)
        isolation (iso/doctor)]
    (u/ensure! (:ready isolation) "Live evolution requires verified isolated SCI execution" isolation)
    (u/ensure! (seq api-key) "ANTHROPIC_API_KEY is required" {})
    (u/ensure! (.exists (io/file "var/isolation-proof.json")) "Run make isolation-test successfully before live execution" {})
    (let [proof (u/json-read (slurp "var/isolation-proof.json"))]
      (u/ensure! (and (= "TESTED" (:status proof)) (= (:image isolation) (:image proof))) "Isolation proof does not match worker image" {}))
    (let [id (str "model-" (System/currentTimeMillis)) root (str "var/runs/" id) store (str root "/controller.sqlite")
          seed (.nextInt (java.security.SecureRandom.) 1000000000)
          learning (mapv #(w/generate (+ seed %) {}) (range 3))
          development (mapv #(w/generate (+ seed %) {}) (range 100 106))
          final (vec (concat (map #(w/generate (+ seed %) {}) (range 200 206))
                             [(w/generate (+ seed 300) {:size 24 :structure :fanout :fault-count 3 :resource-mix true})
                              (w/generate (+ seed 301) {:size 24 :structure :chain :fault-count 3 :resource-mix true})]))
          coldboot (vec (concat (map #(w/generate (+ seed %) {}) (range 400 406))
                                [(w/generate (+ seed 500) {:size 30 :structure :independent :fault-count 4 :resource-mix true})
                                 (w/generate (+ seed 501) {:size 30 :structure :fanout :fault-count 4 :resource-mix true})]))
          config (-> (u/read-file "config/experiment.edn")
                     (assoc :mode :live :provenance :recorded-model-run :split-version (u/hash-value [learning development final coldboot]))
                     (assoc-in [:limits :usd] cap))
          p (provider/->AnthropicProvider model api-key input-rate output-rate 2048)]
      (doseq [artifact [f/initial-policy f/initial-workflow]] (a/save! root artifact))
      (c/create-run! store id config (:hash f/initial-workflow))
      (u/write-edn! (str root "/manifest.edn") (assoc (experiment/manifest config)
                                                    :model {:requested model :provider :anthropic :input-usd-per-m input-rate :output-usd-per-m output-rate}
                                                    :isolation isolation))
      ;; Controller-only file; never sent through the capability broker or mounted.
      (u/write-edn! (str root "/sealed-splits.edn") {:learning learning :development development :final final :coldboot coldboot})
      (try
        (doseq [[i world] (map-indexed vector learning)]
          (experiment/assert-frozen-source! (u/read-file (str root "/manifest.edn")))
          (let [r (c/get-run store id) active (a/load! root (:active r))
                policy-hash (get-in active [:forms :strategy :policy])
                before (development-panel! store id root policy-hash development)
                session (str "root-" i)]
            (c/put-context! store id "jobs" (:jobs (sim/observe (sim/initial-state world) nil)))
            (c/put-context! store id "workers" (:workers (sim/observe (sim/initial-state world) nil)))
            (c/put-context! store id "artifacts" [active (a/load! root policy-hash)])
            (c/put-context! store id "development" before)
            (c/session! store id session nil)
            (let [runtime-env {:store store :run id :registry root :provider p :workers (atom {}) :allow-learning true
                               :development-evaluator (fn [hash] {:cases (development-panel! store id root hash development)})}
                  selected (runtime/workflow! store id active "jobs"
                             (fn [task context]
                               (runtime/broker! runtime-env session {:op :agent/call :id (str session "-workflow-child")
                                                                    :task task :context context})))]
              (runtime/run-session! runtime-env session
                {:task "Investigate the bottleneck. Use code-selected evidence and a child call. Propose a reusable policy and a workflow that uses it."
                 :workflow-result selected :active-workflow (:hash active) :context-handles ["jobs" "workers" "artifacts" "development" "trace-index"]}))
            (doseq [event (:events (c/get-run store id))
                    :when (and (= :artifact-staged (:type event)) (= session (get-in event [:payload :session])))
                    :let [candidate (a/load! root (get-in event [:payload :hash]))]
                    :when (and (= :workflow (:category candidate)) (= (:hash active) (:parent candidate)))]
              (let [after (development-panel! store id root (get-in candidate [:forms :strategy :policy]) development)
                    evidence (a/promotion-evidence before after (:promotion config))]
                (a/promote! store id root candidate evidence)))))
        (catch Exception e
          (c/update-run! store id #(-> % (assoc :status :checkpointed) (c/event :run-stopped {:reason (.getMessage e)})))))
      (let [r (c/get-run store id) export-path (str root "/export")
            returned (set (keep #(get-in % [:response :model]) (vals (:provider-requests r))))]
        (experiment/assert-frozen-source! (u/read-file (str root "/manifest.edn")))
        (u/write-edn! (str root "/manifest.edn")
                      (assoc-in (u/read-file (str root "/manifest.edn")) [:model :returned-identifiers] returned))
        (bundle/export! root export-path (:active r) :recorded-model-run)
        (u/atomic-write! (str root "/events.jsonl") (str (str/join "\n" (map u/json-str (:events r))) "\n"))
        (u/write-edn! (str root "/checkpoint.edn") (select-keys r [:id :status :active :spent :reserved]))
        {:run-id id :path root :export export-path :status (:status r)
         :promotions (count (:promotions r)) :spent (:spent r) :reserved (:reserved r)}))))
