(ns repl-lab.command-envelope-test
  "Adversarial FIXTURE controls. No provider inference or host code evaluation."
  (:require [clojure.test :refer :all] [repl-lab.model-protocol :as wire]
            [repl-lab.runtime :as runtime] [repl-lab.controller :as c]
            [repl-lab.provider :as provider] [repl-lab.util :as u]
            [repl-lab.runtime-test :refer [temp-root config]]))

(def strict-config (assoc config :response-envelope wire/envelope-version))
(defn response [text]
  {:text text :content [{:type "text" :text text}] :stop-reason "end_turn"})
(def done "{:op :done :summary \"corrected\"}")
(defn rejection [r]
  (try (wire/parse-response strict-config r runtime/schemas) nil
       (catch clojure.lang.ExceptionInfo e (ex-data e))))

(deftest envelope-accepts-only-one-complete-map-and-keeps-source-opaque
  (is (= {:op :done :summary "corrected"}
         (wire/parse-response strict-config (response (str " \n" done "\t")) runtime/schemas)))
  (let [command {:op :repl/eval :source "(do ; source comment\n (str \"<invoke>\" \"#=\"))" :bindings {:ids #{1 2}}}
        r (update (response (pr-str command)) :content #(into [{:type "thinking" :thinking "fixture" :signature "fixture"}] %))]
    (is (= command (wire/parse-response strict-config r runtime/schemas))))
  (is (= {:op :done :summary "corrected"}
         (wire/parse-response {} {:text done} runtime/schemas))))

(deftest adversarial-envelopes-never-yield-a-command
  (doseq [[text reason recoverable]
          [[(str done " extra") :trailing-content true]
           [(str "```edn\n" done "\n```") :map-envelope true]
           [(str "<invoke>" done "</invoke>") :map-envelope true]
           [(str done " " done) :multiple-commands false]
           [(str done " {:op :repl/eval :source \"(danger)\" :bindings {}}") :multiple-commands false]
           ["{:op :done :summary}" :malformed-edn true]
           ["{:op :done :summary \"unfinished" :malformed-edn true]
           ["{:op :done :op :repl/eval :summary \"x\"}" :duplicate-key false]
           ["{:op :done :summary \"x\" :source \"(danger)\"}" :command-schema false]
           ["{:op :unknown :summary \"x\"}" :command-schema false]
           ["{:op \"done\" :summary \"x\"}" :command-schema false]
           ["{:op :done :summary {:op :repl/eval}}" :command-schema false]
           ["{:op :repl/eval :source (+ 1 2) :bindings {}}" :command-schema false]
           ["{:op :repl/eval :source \"1\" :bindings []}" :command-schema false]
           [(str done " ; hidden command") :comments true]
           [(str done " #_(danger)") :reader-safety false]
           ["#=(System/exit 0)" :reader-safety false]
           ["{:op :done :summary #inst \"2020\"}" :reader-safety false]
           [(apply str (repeat 33000 "x")) :size false]
           [(str "{:op :done :summary " (apply str (repeat 100 "["))) :reader-safety false]]]
    (is (= {:command-envelope-error true :reason reason :recoverable recoverable}
           (rejection (response text))) (str reason)))
  (doseq [r [(assoc (response done) :stop-reason "max_tokens")
             (assoc (response done) :stop-reason "tool_use")
             (dissoc (response done) :stop-reason)
             (assoc (response done) :content [{:type "text" :text done} {:type "text" :text done}])
             (assoc (response done) :content [{:type "text" :text done} {:type "tool_use" :input {:source "danger"}}])
             (assoc (response done) :text "{:op :repl/eval :source \"danger\" :bindings {}}")
             (assoc (response done) :content [])]]
    (is (false? (:recoverable (rejection r)))))
  ;; Split text blocks must not be concatenated into an executable envelope.
  (is (= :content-blocks (:reason (rejection (assoc (response done) :content
                                             [{:type "text" :text "{:op :done"}
                                              {:type "text" :text " :summary \"x\"}"}]))))))

(defrecord AccountedScript [queues observed after-call]
  provider/Provider
  (invoke! [_ store run session messages]
    (let [id (str (java.util.UUID/randomUUID)) answer (first (get @queues session))]
      (u/ensure! answer "No scripted response" {})
      (c/reserve! store run id session 100 0.01)
      (swap! observed conj {:session session :messages messages})
      (swap! queues update session #(vec (rest %)))
      (let [reply (merge answer {:tokens 20 :usd 0.002 :model "fixture" :request-id id
                                 :provider-id id :provenance :synthetic-fixture})]
        (c/reconcile! store run id reply)
        (when after-call (after-call store run session))
        reply))))

(defn execute-script
  ([queues overrides after-call] (execute-script queues overrides after-call strict-config))
  ([queues overrides after-call base]
  (let [root (temp-root) store (str root "/controller.sqlite") observed (atom [])
        cfg (update base :limits merge {:usd 1} overrides)
        env {:store store :run "run" :workers (atom {}) :base-instructions "Fixture envelope test"
             :provider (->AccountedScript (atom queues) observed after-call)}]
    (c/create-run! store "run" cfg nil) (c/session! store "run" "root" nil)
    (let [result (runtime/run-session! env "root" {:task "Fixture only"})]
      {:env env :result result :observed @observed :ledger (c/get-run store "run")}))))

(deftest exact-v3-failure-gets-one-accounted-fresh-response-with-no-fragment-execution
  (let [bad (u/json-read (slurp "test/fixtures/v3-command-response.json"))
        _ (is (= (:text_sha256 bad) (u/sha (:text bad))))
        {:keys [result observed ledger]} (execute-script {"root" [bad (response done)]} {} nil)
        rejected (filter #(= :command-rejected (:type %)) (:events ledger))
        tools (filter #(= :tool-call (:type %)) (:events ledger))]
    (is (= {:summary "corrected"} result))
    (is (= 2 (count observed) (get-in ledger [:spent :calls])))
    (is (= 40 (get-in ledger [:spent :tokens])))
    (is (= 0.004 (get-in ledger [:spent :usd])))
    (is (= {:calls 0 :tokens 0 :usd 0.0} (:reserved ledger)))
    (is (= [:done] (mapv #(get-in % [:payload :command :op]) tools)))
    (is (= 1 (count rejected) (:command-corrections-issued ledger)))
    (is (false? (get-in (first rejected) [:payload :executed])))
    (is (every? #(not= (:text bad) (:content %)) (:messages (second observed))))
    (is (some #(re-find #"command-rejected" (:content %)) (:messages (second observed))))))

(deftest correction-budget-is-task-wide-and-not-reset-by-a-valid-command
  (let [bad (response "<invoke>invalid</invoke>")
        {:keys [ledger observed]} (execute-script
                                   {"root" [bad (response "{:op :agent/call :id \"child\" :task \"test\" :context {}}")
                                            (response done)]
                                    "child" [bad (response done)]} {} nil)
        rejected (filter #(= :command-rejected (:type %)) (:events ledger))]
    (is (= ["root" "root" "child" "root"] (mapv :session observed)))
    (is (= 4 (get-in ledger [:spent :calls])))
    (is (= [true false] (mapv #(get-in % [:payload :correction-requested]) rejected)))
    (is (= :failed (get-in ledger [:sessions "child" :status])))
    (is (= 1 (:command-corrections-issued ledger)))))

(deftest budget-or-deadline-denial-does-not-dispatch-a-correction
  (doseq [[limits after-call] [[{:calls 1} nil] [{:usd 0.01} nil] [{:tokens 100} nil]
                               [{} (fn [store run _] (c/update-run! store run #(assoc % :started-ms 0)))]]]
    (let [{:keys [result ledger observed]} (execute-script
                                          {"root" [(response "malformed") (response done)]} limits after-call)]
      (is (:error result))
      (is (= 1 (count observed) (get-in ledger [:spent :calls])))
      (is (empty? (filter #(= :tool-call (:type %)) (:events ledger)))))))

(deftest resumed-child-cannot-renew-the-correction-allowance
  (let [call (response "{:op :agent/call :id \"child\" :task \"test\" :context {}}")
        {:keys [env ledger observed]} (execute-script
                                       {"root" [call call (response done)]
                                        "child" [(response "bad") (response done) (response "bad again")]} {} nil)]
    (is (= ["root" "child" "child" "root" "child" "root"] (mapv :session observed)))
    (is (= :failed (get-in ledger [:sessions "child" :status])))
    (is (= 1 (:command-corrections-issued ledger)))
    ;; A new read of the durable store retains the same allowance state.
    (is (= 1 (:command-corrections-issued (c/get-run (:store env) (:run env)))))))

(deftest unknown-provider-outcome-is-not-a-formatting-retry
  (let [root (temp-root) store (str root "/controller.sqlite") calls (atom 0)
        p (reify provider/Provider
            (invoke! [_ store run session _]
              (swap! calls inc)
              (c/reserve! store run "unknown-fixture" session 100 0.01)
              (c/recover! store run)
              (throw (ex-info "Fixture provider interruption" {}))))]
    (c/create-run! store "run" (assoc-in strict-config [:limits :usd] 1) nil)
    (c/session! store "run" "root" nil)
    (is (:error (runtime/run-session! {:store store :run "run" :workers (atom {}) :provider p} "root" {})))
    (let [r (c/get-run store "run")]
      (is (= 1 @calls))
      (is (= :unknown (get-in r [:provider-requests "unknown-fixture" :status])))
      (is (= 0.01 (get-in r [:reserved :usd])))
      (is (not-any? #(#{:command-rejected :tool-call} (:type %)) (:events r))))))

(deftest ambiguous-and-repeated-invalid-output-cannot-execute
  (doseq [answers [[(response (str done " " done)) (response done)]
                  [(response "bad") (response "still bad") (response done)]
                  [(assoc (response done) :stop-reason "max_tokens") (response done)]]]
    (let [{:keys [result ledger]} (execute-script {"root" answers} {} nil)]
      (is (:error result))
      (is (<= (get-in ledger [:spent :calls]) 2))
      (is (empty? (filter #(= :tool-call (:type %)) (:events ledger)))))))

;; edn-map-source-block-v1: the V6 live failure was valid Clojure that could not
;; survive EDN string escaping. The block form carries it verbatim.
(def block-config (assoc config :response-envelope wire/block-envelope-version))
(defn block-rejection [r]
  (try (wire/parse-response block-config r runtime/schemas) nil
       (catch clojure.lang.ExceptionInfo e (ex-data e))))
(def v6-code "(do (def qs (filter (fn [l] (re-find #\"User: \" l)) lines)) (doseq [l qs] (println (clojure.string/replace l #\"^Date: [^|]*\\|\\| \" \"\"))) nil)")
(defn block [m code] (str (pr-str m) "\n<<<SOURCE\n" code "\nSOURCE>>>\n"))

(deftest block-envelope-carries-code-verbatim
  (doseq [code [v6-code
                "(let [s \"a;b\"] ; comment\n  #_(ignored) (str s \"\\\"\" #'inc))"
                "(+ 1\n\n   2)"]]
    (is (= {:op :repl/eval :source code :bindings {}}
           (wire/parse-response block-config (response (block {:op :repl/eval :source :block :bindings {}} code))
                                runtime/schemas))))
  (is (= {:op :repl/eval :source "(+ 1 2)" :bindings {}}
         (wire/parse-response block-config
                              (response "{:op :repl/eval :source :block :bindings {}}\r\n<<<SOURCE\r\n(+ 1 2)\r\nSOURCE>>>\r\n")
                              runtime/schemas)))
  ;; The string form and plain maps keep working under the new envelope.
  (is (= {:op :repl/eval :source "(+ 1 2)" :bindings {}}
         (wire/parse-response block-config (response "{:op :repl/eval :source \"(+ 1 2)\" :bindings {}}") runtime/schemas)))
  (is (= {:op :done :summary "corrected"} (wire/parse-response block-config (response done) runtime/schemas))))

(deftest malformed-blocks-never-yield-a-command
  (let [m "{:op :repl/eval :source :block :bindings {}}"]
    (doseq [[text reason recoverable]
            [[m :source-block true]
             [(str "{:op :repl/eval :source \"(+ 1 2)\" :bindings {}}\n<<<SOURCE\n(danger)\nSOURCE>>>") :source-block true]
             [(str done "\n<<<SOURCE\n(danger)\nSOURCE>>>") :source-block true]
             [(str m "\n<<<SOURCE\n(a)\nSOURCE>>>\n<<<SOURCE\n(b)\nSOURCE>>>") :source-block true]
             [(str m "\n<<<SOURCE\n(a)\n<<<SOURCE\n(b)\nSOURCE>>>") :source-block true]
             [(str m "\n<<<SOURCE\n(danger)") :source-block true]
             [(str m "\n<<<SOURCE\n(a)\nSOURCE>>>\nexplanation") :source-block true]
             [(str m "\n<<<SOURCE\n(a) SOURCE>>>") :source-block true]
             [(str m "\n<<<SOURCE\n  \nSOURCE>>>") :source-block true]
             [(str "Here is the command:\n" m "\n<<<SOURCE\n(a)\nSOURCE>>>") :map-envelope true]
             [(str "{:op :repl/eval :source :block :bindings {}} ; note\n<<<SOURCE\n(a)\nSOURCE>>>") :comments true]
             [(str "{:op :repl/eval :source :block :bindings #=(danger)}\n<<<SOURCE\n(a)\nSOURCE>>>") :reader-safety false]
             [(str done " " m "\n<<<SOURCE\n(a)\nSOURCE>>>") :multiple-commands false]
             [(str m "\n<<<SOURCE\n" (apply str (repeat 33000 "x")) "\nSOURCE>>>") :size false]]]
      (is (= {:command-envelope-error true :reason reason :recoverable recoverable}
             (block-rejection (response text))) (str reason " " (subs text 0 (min 60 (count text))))))))

(deftest v1-envelope-is-unchanged-by-the-block-format
  (is (some? (rejection (response (block {:op :repl/eval :source :block :bindings {}} "(+ 1 2)")))))
  (is (= :command-schema (:reason (rejection (response "{:op :repl/eval :source :block :bindings {}}")))))
  (is (= "Return a new complete single EDN command map. No markup, comments or extra text. No rejected fragment was executed. This is the task's only formatting correction; normal budgets still apply."
         (wire/correction-instruction strict-config)))
  (is (re-find #"<<<SOURCE" (wire/correction-instruction block-config))))

;; native-tool-v1: V3, V6 and V7 failed when the model wrote tool-call markup
;; instead of a text command. Commands now arrive as provider-native tool calls.
(def tool-config (-> config (assoc :response-envelope wire/tool-envelope-version)
                     (assoc-in [:limits :history-records] Integer/MAX_VALUE)))
(defn tool-response [tool input & {:keys [text stop] :or {stop "tool_use"}}]
  {:text (or text "") :stop-reason stop
   :content (cond-> [{:type "thinking" :thinking "fixture" :signature "fixture-signature"}]
              text (conj {:type "text" :text text})
              tool (conj {:type "tool_use" :id (str (gensym "toolu_")) :name tool :input input}))})
(defn call-id [r] (:id (last (:content r))))
(defn tool-rejection [r]
  (try (wire/parse-response tool-config r runtime/schemas) nil
       (catch clojure.lang.ExceptionInfo e (ex-data e))))
(def quoted-code "(count (filter (fn [l] (re-find (re-pattern \"User: \") l)) lines))")

(deftest tool-calls-map-onto-the-same-command-schemas
  (doseq [[tool input command]
          [["repl_eval" {:source quoted-code} {:op :repl/eval :source quoted-code :bindings {}}]
           ["repl_eval" {:source v6-code} {:op :repl/eval :source v6-code :bindings {}}]
           ["context_metadata" {:handle "context"} {:op :context/metadata :handle "context"}]
           ["context_query" {:handle "context" :offset 0 :limit 5 :select ["text"]}
            {:op :context/query :handle "context" :query {:offset 0 :limit 5 :select [:text]}}]
           ["context_query" {:handle "context"} {:op :context/query :handle "context" :query {}}]
           ["agent_call" {:id "c" :task "t"} {:op :agent/call :id "c" :task "t" :context []}]
           ["agent_call" {:id "c" :task "t" :context ["e"]} {:op :agent/call :id "c" :task "t" :context ["e"]}]
           ["done" {:summary "6"} {:op :done :summary "6"}]]]
    (is (= command (wire/parse-response tool-config (tool-response tool input) runtime/schemas))))
  ;; Text beside the call is never parsed, even when it looks like a command.
  (is (= {:op :repl/eval :source "(+ 1 2)" :bindings {}}
         (wire/parse-response tool-config (tool-response "repl_eval" {:source "(+ 1 2)"} :text done) runtime/schemas)))
  (is (= #{"context_metadata" "context_query" "repl_eval" "agent_call" "done"}
         (set (map :name (wire/tool-definitions)))))
  (is (every? #(and (string? (:description %)) (= false (get-in % [:input_schema :additionalProperties])))
              (wire/tool-definitions))))

(deftest malformed-tool-responses-never-yield-a-command
  (doseq [[r reason recoverable]
          [[(tool-response nil nil :text done :stop "end_turn") :no-tool-call true]
           ;; The exact V7 final response: empty invoke tags, no command.
           [(tool-response nil nil :text "<invoke name=\"eval\">\n</invoke>\n\n<invoke name=\"eval\">\n</invoke>" :stop "end_turn") :no-tool-call true]
           [(tool-response "shell" {:cmd "ls"}) :tool-name true]
           [(tool-response "repl_eval" {:source "(+ 1 2)" :bindings {:x 1}}) :tool-input true]
           [(tool-response "repl_eval" {}) :tool-input true]
           [(tool-response "repl_eval" {:source 42}) :tool-input true]
           [(tool-response "repl_eval" "(+ 1 2)") :tool-input true]
           [(tool-response "context_query" {:offset 0}) :tool-input true]
           [(tool-response "done" {:summary ["x"]}) :tool-input true]
           [(update (tool-response "done" {:summary "a"}) :content conj {:type "tool_use" :id "t2" :name "done" :input {:summary "b"}})
            :multiple-commands false]
           [(tool-response "done" {:summary "a"} :stop "max_tokens") :incomplete-turn false]
           [(tool-response "done" {:summary "a"} :stop "end_turn") :incomplete-turn false]
           [(tool-response nil nil :stop "tool_use") :incomplete-turn false]
           [(tool-response nil nil :text "x" :stop "refusal") :incomplete-turn false]
           [(update (tool-response "done" {:summary "a"}) :content conj {:type "image"}) :content-blocks false]
           [(update (tool-response "done" {:summary "a"}) :content seq) :content-blocks false]]]
    (is (= {:reason reason :recoverable recoverable}
           (select-keys (tool-rejection r) [:reason :recoverable]))
        (pr-str r))))

(deftest tool-turns-append-provider-blocks-unchanged-and-answer-each-call
  (let [bad (tool-response nil nil :text "The answer is 6." :stop "end_turn")
        size (tool-response "context_metadata" {:handle "context"} :text "Checking the size.")
        invalid-child (tool-response "agent_call" {:id "root" :task "self"})
        child-call (tool-response "agent_call" {:id "child" :task "count" :context ["evidence"]})
        finish (tool-response "done" {:summary "6"})
        {:keys [result observed ledger]}
        (execute-script {"root" [bad size invalid-child child-call finish]
                         "child" [(tool-response "done" {:summary "child-6"})]} {:calls 12} nil tool-config)
        roots (filterv #(= "root" (:session %)) observed)
        answered (fn [request] (take-last 2 (:messages request)))]
    (is (= {:summary "6"} result))
    (is (= ["root" "root" "root" "root" "child" "root"] (mapv :session observed)))
    ;; Append-only: each root request extends the previous one unchanged.
    (doseq [[a b] (partition 2 1 roots)]
      (is (= (:messages a) (subvec (vec (:messages b)) 0 (count (:messages a))))))
    ;; The rejected text response never enters history; one correction is spent.
    (is (not-any? #(= (:content bad) (:content %)) (mapcat :messages observed)))
    (is (re-find #"command-rejected" (:content (last (:messages (second roots))))))
    (is (= 1 (:command-corrections-issued ledger)))
    ;; Each executed call is answered by ID, after the provider's unchanged blocks.
    ;; Broker errors (this fixture binds no context handle) return as error results.
    (doseq [[request r error] [[(nth roots 2) size true] [(nth roots 3) invalid-child true] [(nth roots 4) child-call false]]]
      (let [[assistant user] (answered request) block (first (:content user))]
        (is (= {:role "assistant" :content (:content r)} assistant))
        (is (= ["tool_result" (call-id r)] [(:type block) (:tool_use_id block)]))
        (is (string? (:content block)))
        (is (= error (boolean (:is_error block))))))
    (is (re-find #"child-6" (:content (first (:content (last (:messages (nth roots 4))))))))
    (is (= [:context/metadata :agent/call :agent/call :done]
           (mapv #(get-in % [:payload :command :op])
                 (filter #(and (= :tool-call (:type %)) (= "root" (get-in % [:payload :session]))) (:events ledger)))))))

(deftest text-envelopes-are-unchanged-by-native-tools
  ;; A text-envelope run never executes a native tool call.
  (is (= :incomplete-turn (:reason (rejection (tool-response "done" {:summary "a"} :text done)))))
  (is (= :content-blocks (:reason (rejection (tool-response "done" {:summary "a"} :text done :stop "end_turn")))))
  (is (re-find #"exactly one of the provided tools" (wire/correction-instruction tool-config)))
  (is (= [{:role "assistant" :content done} {:role "user" :content "{:summary \"x\"}"}]
         (wire/result-messages strict-config (response done) {:summary "x"}))))
