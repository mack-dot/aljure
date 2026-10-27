(require '[repl-lab.experiment :as experiment]
         '[repl-lab.util :as u]
         '[repl-lab.artifact :as a]
         '[repl-lab.bundle :as bundle])
(doseq [path ["var/runs/model-1793062055972"
              "var/evaluations/evaluation-1793062969450"
              "var/evaluations/evaluation-1793064236328"]]
  (println path (pr-str (experiment/replay! path))))
(let [original (a/load! "var/runs/model-1793062055972/tasks/evolving-0"
                       "834a4e02cd945ad6f889947c2ad4223e04a0bb175e4d7ba266329f2193a0e4d3")
      cold (a/load! "var/evaluations/evaluation-1793064236328"
                    "eb336176819f34a4a955fd21b8f735bbdad1dd1a66ea9d15b3dab5d1248d760e")]
  (assert (= (:forms original) (:forms cold)))
  (println "Restored policy forms match model-authored policy exactly."))
(bundle/load-bundle "var/runs/model-1793062055972/export")
(println "Export envelope and payload hashes verified.")
(shutdown-agents)
