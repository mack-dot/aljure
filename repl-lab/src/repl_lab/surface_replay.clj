(ns repl-lab.surface-replay
  "Offline ergonomics measurement (research/Q_SUBSTRATE_BRIEF.md Phase 3): every
  recorded model-written SCI program under var/ whose arm kept its public input,
  re-run in its recorded order through the current broker and a fresh real worker
  over its own recorded context. Each call's recorded outcome is compared with
  today's, by error class. Replays the model's own code under today's surface; it
  predicts no new model behaviour. No model calls."
  (:require [clojure.java.io :as io] [clojure.string :as str] [repl-lab.util :as u]
            [repl-lab.isolation :as isolation] [repl-lab.execution :as execution]
            [repl-lab.model-protocol :as wire] [repl-lab.external-task :as external]
            [repl-lab.controller :as c] [repl-lab.runtime :as runtime] [repl-lab.replay :as replay]))

(def classes
  [[:range #"out of bounds for length|String index out of range|begin \d+, end \d+, length"]
   [:reader #"EOF while reading|No dispatch macro|Unmatched closing|not readable|Unmatched delimiter"]
   [:one-form #"One form per request"]
   [:context-function #"Could not resolve symbol: (context_query|context-query|external-context-fake|context_metadata)"]
   [:parse #"Could not resolve symbol: (parse-long|Long/parseLong)"]
   [:char-cast #"java.lang.Character cannot be cast"]
   [:denied #"is not allowed!|denied in this sandbox|Could not resolve symbol: (slurp|println|pr-str|print|prn|read-string|eval)$"]
   [:source-function #"Could not resolve symbol: (clojure.repl/)?source"]
   [:unresolved #"Could not resolve symbol"]
   [:infrastructure #"execution disabled|response timeout|terminated without result|The worker stopped|Worker input too large"]])

(defn classify [error]
  (when error
    (or (some (fn [[k re]] (when (re-find re error) k)) classes) :other)))

(defn arms
  "Arm directories with a recorded public context and an event log."
  [root]
  (->> (file-seq (io/file root))
       (filter #(and (= "public-input.json" (.getName %)) (not (str/includes? (str %) "quarantine"))))
       (map #(.getParentFile %))
       (filter #(.exists (io/file % "agent/events.jsonl")))
       (filter #(string? (:context (try (u/json-read (slurp (io/file % "public-input.json"))) (catch Exception _ nil)))))
       (map str) sort vec))

(defn recorded
  "The root session's SCI calls in order, each with its recorded outcome."
  [arm]
  (let [events (->> (line-seq (io/reader (io/file arm "agent/events.jsonl"))) (map u/json-read)
                    (filter #(= "root" (get-in % [:payload :session]))))
        calls (filter #(and (= "tool-call" (:type %)) (#{"repl/eval" "done/eval"} (get-in % [:payload :command :op]))) events)
        results (filter #(and (= "tool-result" (:type %)) (#{"repl/eval" "done/eval"} (get-in % [:payload :op]))) events)]
    (mapv (fn [call result]
            {:op (get-in call [:payload :command :op]) :source (get-in call [:payload :command :source])
             :recorded-status (get-in result [:payload :status]) :recorded-error (get-in result [:payload :error])
             :recorded-ms (get-in result [:payload :elapsed-ms])})
          calls results)))

(defn replay-arm
  "Runs the arm's recorded calls through the current broker on a fresh worker."
  [arm]
  (let [context (:context (u/json-read (slurp (str arm "/public-input.json"))))
        root (str (System/getProperty "java.io.tmpdir") "/surface-replay-" (System/nanoTime))
        store (str root "/controller.sqlite") workers (atom {})
        env {:store store :run "replay" :workers workers :registry root :allow-learning false
             :initialize-worker (partial external/initialize-context! context true)}]
    (c/create-run! store "replay" (merge (u/read-file "config/experiment.edn")
                                         {:response-envelope wire/tool-envelope-version
                                          :sci-surface :assisted :sci-results :bounded
                                          :limits {:calls 1000 :tokens 1000000 :recursion-depth 2 :concurrent-subagents 2
                                                   :candidates 4 :evaluation-episodes 100 :messages 100 :wall-ms 600000
                                                   :history-records 1000 :message-bytes 8192 :context-bytes 16384 :event-budget 100000}}) nil)
    (c/session! store "replay" "root" nil)
    (try
      (vec (for [call (recorded arm)]
             (let [command (replay/command {:op (:op call) :source (:source call)})
                   started (System/nanoTime)
                   outcome (try (runtime/broker! env "root" command) {:status "ok"}
                                (catch Exception e {:status "error" :error (.getMessage e)}))]
               (merge call outcome {:replayed-ms (/ (- (System/nanoTime) started) 1e6)
                                    :recorded-class (classify (:recorded-error call)) :replayed-class (classify (:error outcome))}))))
      (finally (doseq [[_ w] @workers] (execution/close! (execution/backend :clojure) w))))))

(defn transition [{:keys [recorded-status status]}]
  (cond (and (= "error" recorded-status) (= "ok" status)) :fixed
        (and (= "ok" recorded-status) (= "error" status)) :regressed
        (= "error" status) :remaining
        :else :ok))

(defn summarize [rows]
  {:calls (count rows)
   :recorded-errors (count (filter #(= "error" (:recorded-status %)) rows))
   :replayed-errors (count (filter #(= "error" (:status %)) rows))
   :transitions (frequencies (map transition rows))
   :recorded-by-class (frequencies (keep :recorded-class rows))
   :replayed-by-class (frequencies (keep :replayed-class rows))
   :regressions (vec (for [r rows :when (= :regressed (transition r))] (select-keys r [:arm :op :error :source])))
   :remaining (vec (for [r rows :when (= :remaining (transition r))] (select-keys r [:arm :op :error :replayed-class])))})

(defn -main [& [label root]]
  (let [check (isolation/require-tested!)
        label (or label "baseline") root (or root "var")
        arms (arms root)
        rows (vec (mapcat (fn [arm]
                            (try (map #(assoc % :arm arm) (replay-arm arm))
                                 (catch Exception e [{:arm arm :status "error" :error (str "Arm replay failed: " (.getMessage e))
                                                      :recorded-status "unknown" :replayed-class :infrastructure}])))
                          arms))
        summary (summarize rows)
        out (str "var/surface-replay-" label ".json")]
    (u/write-json! out {:evidence "OFFLINE REPLAY; real isolated worker; no model" :label label :image (:image check)
                        :output-bytes (isolation/output-bound) :arms (count arms)
                        :sources {:prelude-sha256 (u/sha (slurp "resources/sci-prelude.edn")) :contract-sha256 (u/sha (slurp "resources/sci-contract.json"))
                                  :model-protocol-sha256 (u/sha (slurp "src/repl_lab/model_protocol.clj"))}
                        :summary summary :rows (mapv #(dissoc % :source) rows)})
    (println (u/json-str (dissoc summary :regressions :remaining)))
    (println "wrote" out)
    (shutdown-agents)
    (System/exit 0)))
