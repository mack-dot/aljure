(ns repl-lab.replay
  "Counterfactual replay of a recorded Aljure arm, with no model calls. Re-runs
  the model's own recorded commands in order (every repl_eval, then the first
  done) through the current broker and a fresh real worker over the same
  context, and stops there. That is where the episode would have ended had the
  answer been delivered. The caller scores the answer with the official scorer.
  Replays that model's code under today's delivery; it does not predict new
  model behaviour."
  (:require [clojure.java.io :as io] [repl-lab.util :as u] [repl-lab.isolation :as isolation]
            [repl-lab.execution :as execution] [repl-lab.model-protocol :as wire]
            [repl-lab.external-task :as external] [repl-lab.controller :as c] [repl-lab.runtime :as runtime]))

(defn- commands
  "Recorded tool calls, in order. An arm killed at its deadline writes no
  events.jsonl, but its controller ledger keeps every call."
  [arm]
  (let [events (io/file arm "agent/events.jsonl")]
    (if (.exists events)
      (->> (line-seq (io/reader events)) (map u/json-read)
           (filter #(= "tool-call" (:type %))) (map #(get-in % [:payload :command])))
      (->> (:events (c/get-run (str arm "/agent/controller.sqlite") "external-task"))
           (filter #(= :tool-call (:type %))) (map #(get-in % [:payload :command]))))))

(defn- command [recorded]
  (let [op (keyword (subs (str (:op recorded)) (if (keyword? (:op recorded)) 1 0)))]
    (case op
      :repl/eval {:op op :source (:source recorded) :bindings {}}
      :done/eval {:op op :source (:source recorded)}
      :done {:op op :summary (:summary recorded)}
      nil)))

(defn replay-arm [arm]
  (let [context (:context (u/json-read (slurp (str arm "/public-input.json"))))
        root (str (System/getProperty "java.io.tmpdir") "/replay-" (System/nanoTime))
        store (str root "/controller.sqlite") workers (atom {})
        env {:store store :run "replay" :workers workers :registry root :allow-learning false
             :initialize-worker (partial external/initialize-context! context true)}]
    (c/create-run! store "replay" (merge (u/read-file "config/experiment.edn")
                                         {:response-envelope wire/tool-envelope-version
                                          :sci-surface :assisted :sci-results :bounded}) nil)
    (c/session! store "replay" "root" nil)
    (try
      (loop [[cmd & more] (keep command (commands arm)) evals 0 errors 0]
        (cond
          (nil? cmd) {:arm arm :answer nil :evals evals :errors errors :note "no done command recorded"}
          (#{:done :done/eval} (:op cmd))
          (let [result (try (runtime/broker! env "root" cmd) (catch Exception e {:error (.getMessage e)}))]
            {:arm arm :answer (:summary result) :evals evals :errors errors :done (name (:op cmd))
             :error (:error result) :workers (count @workers)})
          :else
          (let [ok (try (runtime/broker! env "root" cmd) true (catch Exception _ false))]
            (recur more (inc evals) (if ok errors (inc errors))))))
      (finally (doseq [[_ w] @workers] (execution/close! (execution/backend :clojure) w))))))

(defn -main [& arms]
  (isolation/require-tested!)
  (doseq [arm arms]
    (let [{:keys [answer] :as r} (try (replay-arm arm) (catch Exception e {:arm arm :error (.getMessage e)}))]
      (when (string? answer) (spit (str "var/replay-" (.getName (io/file arm)) ".txt") answer))
      (println (u/json-str (-> r (dissoc :answer) (assoc :answer_chars (when (string? answer) (count answer))))))))
  (shutdown-agents)
  (System/exit 0))
