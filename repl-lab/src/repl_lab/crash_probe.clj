(ns repl-lab.crash-probe
  "Trusted fixture process for actual kill/restart tests. Not an agent capability."
  (:require [repl-lab.controller :as c] [repl-lab.artifact :as a]
            [repl-lab.fixtures :as f] [repl-lab.util :as u]))
(defn -main [& [op root point]]
  (let [store (str root "/controller.sqlite") id "crash-fixture"]
    (case op
      "prepare" (do (doseq [item [f/initial-policy f/packed-policy f/initial-workflow f/improved-workflow]] (a/save! root item))
                    (c/create-run! store id (u/read-file "config/experiment.edn") (:hash f/initial-workflow)))
      "promote" (let [old [{:case "test-fixture" :completed 1 :makespan 10 :score 10 :accepted-invariant-violations 0}]
                      new [(assoc (first old) :makespan 8 :score 8)]
                      evidence (a/promotion-evidence old new (:promotion (u/read-file "config/experiment.edn")))]
                  (binding [a/*crash-hook* (fn [stage]
                                           (when (= stage (keyword point))
                                             (u/atomic-write! (str root "/ready-to-kill") (name stage))
                                             (Thread/sleep 60000)))]
                    (a/promote! store id root f/improved-workflow evidence)))
      "recover" (let [r (a/recover-registry! store id root)]
                  (println (u/json-str {:active (:active r) :promotions (count (:promotions r))
                                       :initial (:hash f/initial-workflow) :candidate (:hash f/improved-workflow)})))
      "rollback" (a/rollback! store id root (:hash f/initial-workflow)))
    (shutdown-agents)))
