;; Capture feasibility (research/UNBLOCK_ACQUISITION.md): would the functions the model already
;; wrote during recorded tasks pass the promotion rule's candidate part on the development panel?
;; No model call. Each eligible capture candidate (repl-lab.capture) is tried with each label its own
;; task question names (a true/false test needs one; the real capture turn asks the model, so taking
;; the best named label is an upper bound). The applicability predicate is a developer stand-in: the
;; context header lists that label. One fresh isolated worker runs every entry.
;;
;;   source var/worker.env && python3 scripts/clj.py scripts/capture_feasibility.clj RUNS SUITE OUT.json
(require '[clojure.data.json :as json] '[clojure.java.io :as io] '[clojure.string :as str]
         '[repl-lab.capture :as capture] '[repl-lab.acquisition :as acq] '[repl-lab.artifact :as a]
         '[repl-lab.execution :as execution] '[repl-lab.isolation :as isolation] '[repl-lab.util :as u]
         '[repl-lab.external-task :as external])

(let [[runs suite out] *command-line-args*
      jsonl (fn [p] (map #(json/read-str % :key-fn keyword) (line-seq (io/reader p))))
      questions (into {} (map (juxt :task_id :question) (jsonl (str suite "/public/tasks.jsonl"))))
      tasks (for [results (sort (map str (filter #(= "results.jsonl" (.getName %)) (file-seq (io/file runs)))))
                  :let [dir (.getParent (io/file results))]
                  row (jsonl results)
                  :let [events (format "%s/%02d-aljure/agent/events.jsonl" dir (:position row))]
                  :when (.exists (io/file events))]
              {:task (str (.getName (io/file dir)) "/" (:position row)) :question (questions (:task_id row))
               :sources (vec (for [e (jsonl events)
                                   :when (and (= "tool-call" (:type e)) (= "root" (get-in e [:payload :session]))
                                              (= "repl/eval" (get-in e [:payload :command :op])))]
                               (get-in e [:payload :command :source])))})
      rows (vec (for [t tasks
                      :let [labels (vec (distinct (map second (re-seq #"label '([^']+)'" (or (:question t) "")))))
                            eligible (filter (comp empty? :reasons) (capture/candidates (:sources t)))]]
                  (assoc t :labels labels :eligible eligible)))
      pairs (vec (distinct (for [r rows c (:eligible r) l (:labels r)] [(:source c) l])))
      entries (vec (for [[k [source label]] (map-indexed vector pairs)
                         :let [f (a/make-artifact {:category :analysis :source (capture/adapted-source {:source source} label)
                                                   :interface {:name (str "cand-" k) :arity 1} :dependencies [] :author "feasibility"
                                                   :parent nil :provenance :controller-generated})
                               p (a/make-artifact {:category :analysis :interface {:name "applicable" :arity 1} :dependencies []
                                                   :source (str "(fn [input] (let [c (:context input)] (clojure.string/includes? "
                                                                "(subs c 0 (min (count c) 2000)) \"'" label "'\")))")
                                                   :author "feasibility" :parent nil :provenance :human-edit})]]
                     {:key k :function f :dependencies [] :predicate p}))
      panel (acq/load-panel (str suite "/controller/panel.json") (u/sha (slurp (str suite "/controller/panel.json"))))
      _ (isolation/require-tested!)
      backend (execution/backend :clojure)
      results (acq/panel-run! backend (fn [context] (fn [b w] (external/initialize-context! context true false b w)))
                              panel entries (+ (System/currentTimeMillis) (* 3600 1000)))
      passes (fn [k] (let [{:keys [items decided correct errors non-labels admitted-windows]} (acq/candidate-metrics panel results k)]
                       {:pass (and (empty? errors) (zero? non-labels) (seq admitted-windows) (pos? decided)
                                   (>= (* decided 10) items) (>= (* correct 20) (* decided 19)))
                        :items items :decided decided :correct correct}))
      by-pair (into {} (for [[k pair] (map-indexed vector pairs)] [pair (passes k)]))
      per-task (for [r rows]
                 {:task (:task r) :labels (:labels r) :eligible (count (:eligible r))
                  :passing (count (filter (fn [c] (some #(:pass (by-pair [(:source c) %])) (:labels r))) (:eligible r)))
                  :passing-single-label (when (= 1 (count (:labels r)))
                                          (count (filter #(:pass (by-pair [(:source %) (first (:labels r))])) (:eligible r))))})
      report {:model-calls 0 :tasks (count rows)
              :tasks-with-eligible (count (filter #(pos? (:eligible %)) per-task))
              :tasks-with-a-passing-candidate (count (filter #(pos? (:passing %)) per-task))
              :single-label-tasks (count (filter #(some? (:passing-single-label %)) per-task))
              :single-label-tasks-passing (count (filter #(some-> % :passing-single-label pos?) per-task))
              :pairs (count pairs) :passing-pairs (count (filter :pass (vals by-pair)))
              ;; Why the others fail: precision below 19/20, coverage below 1/10, or both (decided pairs only).
              :failing (frequencies (for [v (vals by-pair) :when (not (:pass v))]
                                      (cond (zero? (:decided v)) :decides-nothing
                                            :else (let [p (>= (* (:correct v) 20) (* (:decided v) 19)) c (>= (* (:decided v) 10) (:items v))]
                                                    (cond (and (not p) (not c)) :precision-and-coverage (not p) :precision
                                                          (not c) :coverage-only :else :errors)))))
              :coverage-only-precise (count (for [v (vals by-pair) :when (and (not (:pass v)) (pos? (:decided v))
                                                                             (>= (* (:correct v) 20) (* (:decided v) 19)))] v))
              :passing-examples (vec (take 12 (for [[[source label] v] by-pair :when (:pass v)]
                                                {:label label :decided (:decided v) :correct (:correct v) :items (:items v)
                                                 :source (subs source 0 (min 400 (count source)))})))
              :per-task (vec per-task)}]
  (spit out (json/write-str report))
  (println (json/write-str (dissoc report :per-task :passing-examples)))
  (shutdown-agents))
