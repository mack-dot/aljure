(ns repl-lab.baselines (:require [repl-lab.sim :as sim]))

(defn- schedule [observation memory job-key worker-key]
  (let [[actions _]
        (reduce (fn [[actions workers] j]
                  (if-let [w (first (sort-by #(worker-key j %) (filter #(and (:up %) (sim/fits? (:resources j) (:available %))) workers)))]
                    [(conj actions {:op :dispatch :job (:id j) :worker (:id w)})
                     (mapv #(if (= (:id w) (:id %)) (update % :available (fn [r] (merge-with - r (:resources j)))) %) workers)]
                    [actions workers]))
                [[] (:workers observation)] (sort-by job-key (filter :ready (:jobs observation))))]
    {:actions (if (seq actions) actions [{:op :wait :ticks 1}]) :memory memory}))

(defn fifo [obs memory] (schedule obs memory :id (fn [_ w] (:id w))))
(defn estimate-aware [obs memory]
  (let [jobs (into {} (map (juxt :id identity) (:jobs obs)))
        children (reduce (fn [m j] (reduce #(update %1 %2 (fnil conj []) (:id j)) m (:deps j))) {} (:jobs obs))
        rank (fn rank [id] (+ (:estimate (jobs id)) (reduce max 0 (map rank (children id)))))]
    (schedule obs memory (fn [j] [(- (rank (:id j))) (:id j)])
              (fn [j w] [(/ (:estimate j) (:speed w)) (:id w)]))))

;; Reviewed developer fixture. This is deliberately simple, and is not a baseline.
(defn serial-fixture [obs memory]
  (if (some #(= :running (:status %)) (:jobs obs))
    {:actions [{:op :wait :ticks 1}] :memory memory}
    (let [j (first (filter :ready (:jobs obs)))
          w (first (filter #(and (:up %) (sim/fits? (:resources j) (:available %))) (:workers obs)))]
      {:actions (if (and j w) [{:op :dispatch :job (:id j) :worker (:id w)}] [{:op :wait :ticks 1}]) :memory memory})))
