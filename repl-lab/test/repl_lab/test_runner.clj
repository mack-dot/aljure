(ns repl-lab.test-runner (:require [clojure.test :as t] [repl-lab.sim-test] [repl-lab.terminal-text-test] [repl-lab.runtime-test] [repl-lab.experiment-test]
                                  [repl-lab.provider-test] [repl-lab.smoke-test] [repl-lab.subscription-test]
                                  [repl-lab.language-benchmark-test] [repl-lab.model-protocol-test] [repl-lab.command-envelope-test] [repl-lab.gateway-test]
                                  [repl-lab.skills-test] [repl-lab.skill-discovery-test] [repl-lab.selector-gate-test]
                                  [repl-lab.selector-acquisition-test] [repl-lab.verification-test] [repl-lab.controller-state-test]
                                  [repl-lab.transport-failure-test] [repl-lab.elastic-test]
                                  [repl-lab.artifact-identity-test] [repl-lab.artifact-library-test]
                                  [repl-lab.acquisition-test] [repl-lab.capture-test] [repl-lab.programs-test] [repl-lab.program-library-test]
                                  [repl-lab.skill-interface-test]))
(defn -main [& _]
  (let [r (t/run-tests 'repl-lab.sim-test 'repl-lab.runtime-test 'repl-lab.experiment-test 'repl-lab.provider-test 'repl-lab.smoke-test 'repl-lab.subscription-test 'repl-lab.language-benchmark-test 'repl-lab.model-protocol-test 'repl-lab.command-envelope-test 'repl-lab.gateway-test 'repl-lab.skills-test 'repl-lab.skill-discovery-test 'repl-lab.selector-gate-test 'repl-lab.selector-acquisition-test 'repl-lab.verification-test 'repl-lab.controller-state-test 'repl-lab.transport-failure-test 'repl-lab.elastic-test 'repl-lab.artifact-identity-test 'repl-lab.artifact-library-test 'repl-lab.acquisition-test 'repl-lab.capture-test 'repl-lab.programs-test 'repl-lab.program-library-test 'repl-lab.terminal-text-test)]
    (let [extra (t/run-tests 'repl-lab.skill-interface-test)]
      (when (pos? (+ (:fail extra) (:error extra))) (System/exit 1)))
    (shutdown-agents)
    (System/exit (if (zero? (+ (:fail r) (:error r))) 0 1))))
