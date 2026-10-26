(ns repl-lab.workloads (:require [repl-lab.util :as u]))

(defn keyed [seed key bound]
  (mod (Long/parseLong (subs (u/hash-value [seed key]) 0 12) 16) bound))

(defn generate [seed {:keys [size structure fault-count resource-mix]
                     :or {size 12 structure :layered fault-count 1 resource-mix false}}]
  (let [ids (mapv #(format "j%03d" %) (range size))]
    {:seed seed :fault-seed (u/hash-value [seed :fault])
     :profile {:size size :structure structure :fault-count fault-count :resource-mix resource-mix}
     :horizon (* 80 size)
     :workers [{:id "w0" :capacity {:cpu 4 :mem 8} :speed 1}
               {:id "w1" :capacity {:cpu 2 :mem 4} :speed 2}
               {:id "w2" :capacity {:cpu 6 :mem 8} :speed 1}]
     :jobs (mapv (fn [i]
                   (let [estimate (+ 2 (keyed seed [:estimate i] 18))]
                     {:id (ids i) :estimate estimate
                      :actual (+ 1 (quot (* estimate (+ 7 (keyed seed [:duration i] 7))) 10))
                      :delay (keyed seed [:delay i] 3)
                      :resources {:cpu (inc (keyed seed [:cpu i] (if resource-mix 4 2)))
                                  :mem (inc (keyed seed [:mem i] (if resource-mix 7 3)))}
                      :deps (case structure
                              :chain (if (zero? i) [] [(ids (dec i))])
                              :fanout (if (zero? i) [] [(ids 0)])
                              :independent []
                              :layered (if (< i 3) [] [(ids (keyed seed [:dep i] i))]))})) (range size))
     :faults (vec (mapcat (fn [i] (let [at (+ 4 (* i 25) (keyed seed [:fault i] 12))
                                        worker (str "w" (keyed seed [:worker i] 3))]
                                    [{:type :failure :at at :worker worker}
                                     {:type :recover :at (+ at 4) :worker worker}])) (range fault-count)))}))

;; Controller-only fixture panels. These are not a sealed real-model final test.
(def fixture-panels
  {:learning (mapv #(generate % {}) (range 100 103))
   :development (mapv #(generate % {}) (range 200 206))
   :heldout (vec (concat (map #(generate % {}) (range 300 306))
                        [(generate 400 {:size 24 :structure :fanout :fault-count 3 :resource-mix true})
                         (generate 401 {:size 24 :structure :chain :fault-count 3 :resource-mix true})
                         (generate 402 {:size 30 :structure :independent :fault-count 4 :resource-mix true})]))})
