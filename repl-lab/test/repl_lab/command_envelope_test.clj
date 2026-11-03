(ns repl-lab.command-envelope-test
  "Adversarial FIXTURE controls. No provider inference or host code evaluation."
  (:require [clojure.test :refer :all] [clojure.string :as str] [repl-lab.model-protocol :as wire]
            [repl-lab.runtime :as runtime] [repl-lab.controller :as c]
            [repl-lab.provider :as provider] [repl-lab.util :as u]
            [repl-lab.isolation :as isolation]
            [repl-lab.external-task :as external]
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
           ["done" {:summary "6"} {:op :done :summary "6"}]
           ["done" {:source "(str 6)"} {:op :done/eval :source "(str 6)"}]]]
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
           [(tool-response "done" {}) :tool-input true]
           [(tool-response "done" {:summary "6" :source "(str 6)"}) :tool-input true]
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

(defn answer-worker
  "Fixture worker for done with source: keeps aljure-answer and serves pages,
  as the real worker does for the controller's wrapper."
  [sources answers]
  (let [kept (atom nil)]
    (fn [_ source _]
      (swap! sources conj source)
      (if-let [[_ n to from] (re-find #"\(min (\d+) (\d+)\).*\(subs aljure-answer (\d+) e\)" source)]
        (let [end (min (Long/parseLong n) (Long/parseLong to))] [end (subs @kept (Long/parseLong from) end)])
        (let [[_ answer] (first (filter #(str/includes? source (first %)) answers))]
          (cond (nil? answer) (u/fail "Worker rejected expression: boom" {})
                (string? answer) (do (reset! kept answer) [(count answer) (hash answer)])
                (number? answer) [answer 0]
                :else :aljure/not-a-string))))))

(deftest done-can-take-its-answer-from-the-session-worker
  ;; Fixture worker only: no container. A failed or non-string answer expression
  ;; is an ordinary tool error and the session continues.
  (let [sources (atom []) big (apply str (map #(char (+ 97 (mod % 26))) (range 20000)))]
    (with-redefs [runtime/open-worker! (fn [& _] ::worker)
                  isolation/close-session! (fn [_] nil)
                  isolation/evaluate! (answer-worker sources [["(+ 1 2)" :number] ["(big)" big] ["(huge)" 9000000]])]
      (let [steps (mapv #(tool-response "done" {:source %}) ["(+ 1 2)" "(boom)" "(huge)" "(big)"])
            {:keys [result observed ledger]} (execute-script {"root" steps} {} nil tool-config)
            errors (mapv #(first (:content (last (:messages %)))) (rest observed))
            pages (keep #(second (re-find #"\(min \d+ (\d+)\)" %)) @sources)]
        ;; An answer larger than one worker reply arrives whole, in pages below the bound.
        (is (= {:summary big} result))
        (is (= ["8192" "16384" "24576"] pages))
        (is (= 4 (count observed)))
        (is (every? :is_error errors))
        (is (re-find #"must evaluate to a string" (:content (first errors))))
        (is (re-find #"8 MiB" (:content (nth errors 2))))
        (is (= :complete (get-in ledger [:sessions "root" :status])))
        (is (zero? (get ledger :command-corrections-issued 0)))))))

(deftest only-the-outgoing-request-carries-cache-breakpoints
  (let [messages [{:role "user" :content "base"} {:role "user" :content "task"}]
        tools (wire/tool-definitions)
        body (external/cache-breakpoints {:messages messages :tools tools})
        called (conj messages (first (wire/result-messages tool-config (tool-response "done" {:summary "x"}) {:summary "x"})))
        answered (conj called {:role "user" :content [{:type "tool_result" :tool_use_id "t" :content "{}"}]})
        marked (fn [b] (filter :cache_control (concat (:tools b) (mapcat #(when (vector? (:content %)) (:content %)) (:messages b)))))]
    (is (= [{:type "text" :text "task" :cache_control {:type "ephemeral"}}] (:content (last (:messages body)))))
    (is (= {:type "ephemeral"} (:cache_control (last (:tools body)))))
    (is (= 2 (count (marked body))))
    (is (= "base" (:content (first (:messages body)))))
    (is (= {:type "ephemeral"} (:cache_control (first (:content (last (:messages (external/cache-breakpoints {:messages answered :tools tools}))))))))
    ;; Inputs are values: stored history and tool definitions stay unmarked.
    (is (empty? (marked {:messages answered :tools tools})))))

(deftest string-values-read-as-plain-text-like-native-output
  (let [content (fn [result] (-> (wire/result-messages tool-config (tool-response "repl_eval" {:source "x"}) result)
                                 second :content first))]
    (is (= "a\nb" (:content (content {:value "a\nb"}))))
    (is (= "42" (:content (content {:value 42}))))
    (is (= "[\"a\" 1]" (:content (content {:value ["a" 1]}))))
    (is (= "nil" (:content (content {:value nil}))))
    (is (= "{:handle \"c\", :total 1}" (:content (content {:handle "c" :total 1}))))
    (is (= {:content "{:error \"boom\"}" :is_error true} (select-keys (content {:error "boom"}) [:content :is_error])))
    (is (not (contains? (content {:value "x"}) :is_error)))
    ;; Text envelopes keep their exact EDN results.
    (is (= "{:value \"a\\nb\"}" (:content (second (wire/result-messages strict-config (response done) {:value "a\nb"})))))))

(deftest ledger-sized-edn-parses-without-reflection
  ;; The controller re-reads the whole run ledger several times per step. A
  ;; reflective per-character scan made a 284 KB ledger take 514 ms to parse and
  ;; added 3-5 s to every Aljure step. Checked by compiler warnings, not timing:
  ;; a timing bound failed spuriously at load average 36.
  (let [ledger (pr-str {:events (vec (repeat 2000 {:type :provider-input :input [{:role "user" :content (apply str (repeat 400 "x\"; #{"))}]}))})
        warnings (java.io.StringWriter.)]
    (is (< 1000000 (count ledger)))
    (is (map? (u/read-edn ledger)))
    (binding [*warn-on-reflection* true *err* (java.io.PrintWriter. warnings)]
      (load "repl_lab/util"))
    (is (not (re-find #"charAt" (str warnings))) (str warnings))))

(deftest a-stopped-worker-is-retired-and-replaced
  ;; 32K case 1: an oversized result stopped the worker, every later eval said
  ;; "Stream closed", and the session spent its calls on a dead worker.
  (let [opened (atom 0) closed (atom []) failures (atom #{"(big)"})]
    (with-redefs [runtime/open-worker! (fn [& _] (keyword (str "worker-" (swap! opened inc))))
                  isolation/close-session! (fn [w] (swap! closed conj w))
                  isolation/evaluate! (fn [worker source _]
                                        (cond
                                          (@failures source) (do (swap! failures disj source) (u/fail "Worker terminated without result" {}))
                                          (= source "(bad)") (u/fail "Worker rejected expression: boom" {})
                                          :else (str (name worker) " " source)))]
      (let [steps (mapv #(tool-response "repl_eval" {:source %}) ["(ok)" "(bad)" "(big)" "(again)"])
            {:keys [result observed]} (execute-script {"root" (conj steps (tool-response "done" {:summary "6"}))} {} nil tool-config)
            results (mapv #(:content (first (:content (last (:messages %))))) (rest observed))]
        (is (= {:summary "6"} result))
        (is (= "worker-1 (ok)" (nth results 0)))
        ;; An expression error keeps the worker.
        (is (re-find #"Worker rejected expression" (nth results 1)))
        (is (re-find #"Worker terminated without result\. The worker stopped; the next repl_eval starts a fresh worker" (nth results 2)))
        (is (= "worker-2 (again)" (nth results 3)))
        (is (= 2 @opened))
        ;; Final cleanup still closes the retired worker as well as the new one.
        (is (= #{:worker-1 :worker-2} (set @closed)))))))

(deftest closing-a-stopped-worker-still-confirms-its-exit
  (letfn [(session [exit] {:writer (proxy [java.io.Writer] [] (write [& _]) (flush [])
                                     (close [] (throw (java.io.IOException. "Stream closed"))))
                           :process (proxy [Process] [] (waitFor ([] exit) ([_ _] true)) (exitValue [] exit)
                                      (getInputStream [] nil) (getOutputStream [] nil) (getErrorStream [] nil) (destroy []))
                           :errors nil})]
    (is (nil? (isolation/close-session! (session 2))))
    (is (thrown-with-msg? clojure.lang.ExceptionInfo #"Worker cleanup unconfirmed" (isolation/close-session! (session 3))))))

;; Assisted SCI surface (resources/sci-contract.json, resources/sci-prelude.edn).
;; The real-worker contract check is repl-lab.sci-contract; these cover the
;; controller logic without a container.
(def assisted-config (assoc tool-config :sci-surface :assisted :sci-results :raw))
(def bounded-config (assoc tool-config :sci-surface :assisted :sci-results :bounded))

(deftest assisted-source-reads-every-form-and-explains-unreadable-code
  (is (= '[(def a 1) (+ a 1)] (wire/read-forms "(def a 1) (+ a 1)")))
  (is (= ["x" 2] (wire/read-forms " \"x\"\n2 ")))
  ;; Clojure reader syntax becomes EDN-safe data; regex literals become re-pattern calls.
  (is (= '[(re-find (re-pattern "\\d+") s)] (wire/read-forms "(re-find #\"\\d+\" s)")))
  (is (= '[(quote x) (clojure.core/deref a) (var v)] (wire/read-forms "'x @a #'v")))
  (is (= 'fn* (first (second (first (wire/read-forms "(map #(inc %) xs)"))))))
  ;; The reader cannot evaluate, construct objects or recurse without bound.
  (doseq [[source text] [["#=(java.lang.System/exit 0)" "read-eval"] ["#java.io.File[\"/\"]" "Record construction"]
                         ["#inst \"2020-01-01\"" "Date literal"] ["#uuid \"00000000-0000-0000-0000-000000000000\"" "UUID literal"]
                         ["#foo 1" "No reader function"] ["#?(:clj 1)" "Conditional read"]
                         [(apply str (repeat 200 "(")) "nesting is too deep"]
                         ["(str \"abc)" "not readable"] ["(+ 1 2" "not readable"] ["   " "empty"]]]
    (is (re-find (re-pattern text) (try (wire/read-forms source) "no error" (catch Exception e (.getMessage e)))) source))
  (let [wrapped (wire/read-forms (wire/assisted-source bounded-config :repl/eval "(def a 1) (+ a 1)"))]
    (is (= 1 (count wrapped)))
    (is (re-find #"\(do \(def a 1\) \(\+ a 1\)\)" (pr-str wrapped)))
    (is (re-find #"aljure-show aljure-v 60000 24000" (pr-str wrapped)))
    (is (re-find #"def full-result" (pr-str wrapped))))
  (is (re-find #"aljure-show aljure-v 1000000000000000 24000" (wire/assisted-source assisted-config :repl/eval "1")))
  ;; done keeps its value exact: no display wrapper, no truncation.
  (is (= "(do (def s \"6\") s)" (wire/assisted-source bounded-config :done/eval "(def s \"6\") s"))))

(deftest assisted-results-explain-errors-and-truncation
  (let [text (fn [config result] (-> (wire/result-messages config (tool-response "repl_eval" {:source "x"}) result)
                                     second :content first :content))
        truncated {:value {:aljure/truncated true :total-chars 100000 :shown-chars 24000 :items nil :kind "string" :preview "xxx"}}]
    (is (= "xxx\n[... truncated: showing the first 24,000 of 100,000 characters. The full value is bound to full-result; read more with (page full-result 24000 24000).]"
           (text bounded-config truncated)))
    (is (re-find #"a sequence of 20,000 items" (text bounded-config (update truncated :value assoc :items 20000 :kind "sequence"))))
    (is (re-find #"denied in this sandbox" (text assisted-config {:error "Worker rejected expression: Could not resolve symbol: slurp"})))
    (is (re-find #"Long/parseLong\. That class is unavailable" (text assisted-config {:error "Worker rejected expression: Could not resolve symbol: Long/parseLong"})))
    (is (re-find #"not defined in this worker" (text assisted-config {:error "Worker rejected expression: Could not resolve symbol: helper"})))
    ;; A fixed-size slice of a shorter text (run-3 of the reuse interface A/B: subs 0 3000 on 1545 characters).
    (is (re-find #"\(page v offset n\)" (text assisted-config {:error "Worker rejected expression: Range [0, 3000) out of bounds for length 1545"})))
    (is (re-find #"\(min end \(count s\)\)" (text assisted-config {:error "Worker rejected expression: begin 0, end 3000, length 1545"})))
    (is (not (re-find #"page v offset" (text assisted-config {:error "Worker rejected expression: Could not resolve symbol: subs-all"}))))
    ;; The raw surface (the benchmark control) shows errors unchanged.
    (is (= "{:error \"Worker rejected expression: Could not resolve symbol: slurp\"}"
           (text tool-config {:error "Worker rejected expression: Could not resolve symbol: slurp"})))))

(deftest assisted-tool-descriptions-come-from-the-contract
  (let [describe (fn [config] (:description (first (filter #(= "repl_eval" (:name %)) (wire/tool-definitions config)))))]
    (is (= (wire/tool-definitions) (wire/tool-definitions tool-config)))
    (is (every? #(str/includes? (describe bounded-config) %) (wire/sci-rules bounded-config)))
    (is (str/includes? (describe bounded-config) "full-result"))
    (is (not (str/includes? (describe assisted-config) "full-result")))
    (is (str/includes? (describe assisted-config) "stops the worker"))))

(deftest unreadable-assisted-source-never-reaches-or-retires-a-worker
  (let [opened (atom 0)]
    (with-redefs [runtime/open-worker! (fn [& _] (swap! opened inc) ::worker)
                  isolation/close-session! (fn [_] nil)
                  isolation/evaluate! (fn [_ source _] (if (str/includes? source "aljure-show") 7 "6"))]
      (let [{:keys [result observed]} (execute-script {"root" [(tool-response "repl_eval" {:source "(str \"abc)"})
                                                               (tool-response "repl_eval" {:source "(+ 3 4)"})
                                                               (tool-response "done" {:summary "6"})]} {} nil assisted-config)
            results (mapv #(:content (first (:content (last (:messages %))))) (rest observed))]
        (is (= {:summary "6"} result))
        (is (re-find #"not readable" (first results)))
        (is (= "7" (second results)))
        (is (= 1 @opened))))))

(deftest sci-settings-are-explicit-and-bounded-needs-assisted
  (is (= [:raw :raw] ((juxt :sci-surface :sci-results) (external/sci-settings {}))))
  (is (= [:assisted :bounded] ((juxt :sci-surface :sci-results) (external/sci-settings {:sci {:surface "assisted" :results "bounded"}}))))
  (doseq [bad [{:surface "raw" :results "bounded"} {:surface "magic"} {:results "huge"}]]
    (is (thrown? clojure.lang.ExceptionInfo (external/sci-settings {:sci bad})))))

(deftest the-ledger-records-only-what-each-request-appends
  (let [m1 [{:role "user" :content "a"} {:role "user" :content "b"}]
        m2 (conj m1 {:role "assistant" :content "c"} {:role "user" :content "d"})
        first-record (external/provider-input-record [] "r1" "root" m1)
        events [{:type :provider-input :payload first-record}]
        second-record (external/provider-input-record events "r2" "root" m2)]
    (is (= m1 (:appended first-record)))
    (is (= (subvec m2 2) (:appended second-record)))
    (is (= [4 (u/hash-value m2)] ((juxt :message-count :input-hash) second-record)))
    (is (= m1 (:appended (external/provider-input-record events "r3" "child" m1))))
    (is (thrown? clojure.lang.ExceptionInfo (external/provider-input-record events "r4" "root" (subvec m1 0 1))))))

;; Finalization and transport recovery (plan-level switches, default off).
;; The fixture holds the exact Opus 5.5 provider responses from plan d6e9b40d.
(def opus-fixture (u/json-read (slurp "test/fixtures/opus-finalization-responses.json")))
(def opus-identity
  {:imdb-truncated ["tool_use" ["thinking" "thinking"] "interrupted before it finished"]
   :formality-text-1 ["end_turn" ["thinking" "text"] "Label: formal"]
   :formality-text-2 ["end_turn" ["thinking" "text"] "Label: formal"]})
(defn opus-response [k]
  (let [{:keys [content stop_reason]} (get-in opus-fixture [:responses k])
        [stop types excerpt] (opus-identity k)]
    ;; The fixture's sha256 is over the recorded transport body; here, its identity.
    (is (= [stop types] [stop_reason (mapv :type content)]) (str "fixture changed: " k))
    (is (str/includes? (pr-str content) excerpt) (str "fixture changed: " k))
    {:content content :stop-reason stop_reason
     :text (apply str (map :text (filter #(= "text" (:type %)) content)))}))
(def contract-config (assoc tool-config :contract {:truncated-turn-retries 1 :terminal-text-answer true}))
(defn text-reply [text & {:keys [stop] :or {stop "end_turn"}}]
  {:text text :stop-reason stop
   :content [{:type "thinking" :thinking "fixture" :signature "s"} {:type "text" :text text}]})

(deftest truncated-turns-are-only-the-self-contradicting-ones
  (is (wire/truncated-tool-turn? (opus-response :imdb-truncated)))
  (is (wire/truncated-tool-turn? (tool-response nil nil :stop "tool_use")))
  (doseq [r [(tool-response "done" {:summary "a"})
             (tool-response nil nil :text "x" :stop "end_turn")
             (tool-response nil nil :text "x" :stop "max_tokens")
             (tool-response nil nil :text "x" :stop "refusal")
             (tool-response "done" {:summary "a"} :stop "end_turn")
             (update (tool-response nil nil :stop "tool_use") :content conj {:type "image"})
             (update (tool-response nil nil :stop "tool_use") :content seq)]]
    (is (not (wire/truncated-tool-turn? r)) (pr-str r))))

(deftest only-an-exact-final-answer-line-is-a-terminal-answer
  (is (= "Label: formal" (wire/terminal-text-answer (text-reply "FINAL ANSWER: Label: formal"))))
  (is (= "Label: formal" (wire/terminal-text-answer (text-reply "  FINAL ANSWER:   Label: formal  "))))
  ;; The exact Opus replies: right answer, but commentary around it. Refused.
  (is (nil? (wire/terminal-text-answer (opus-response :formality-text-1))))
  (is (nil? (wire/terminal-text-answer (opus-response :formality-text-2))))
  (doseq [r [(text-reply "Label: formal")
             (text-reply "FINAL ANSWER: Label: formal\nI judged about 90 formal.")
             (text-reply "I judged them myself.\nFINAL ANSWER: Label: formal")
             (text-reply "FINAL ANSWER: ")
             (text-reply "FINAL ANSWER: a FINAL ANSWER: b")
             (text-reply "final answer: Label: formal")
             (text-reply "```FINAL ANSWER: x```")
             (text-reply "FINAL ANSWER: Label: formal" :stop "max_tokens")
             (text-reply "FINAL ANSWER: Label: formal" :stop "tool_use")
             (tool-response "done" {:summary "x"} :text "FINAL ANSWER: x" :stop "end_turn")
             {:text "FINAL ANSWER: x" :stop-reason "end_turn" :content [{:type "thinking" :thinking "FINAL ANSWER: x"}]}
             (text-reply (str "FINAL ANSWER: " (apply str (repeat 4097 "x"))))]]
    (is (nil? (wire/terminal-text-answer r)) (pr-str (:text r)))))

(defn- events [ledger kind] (filter #(= kind (:type %)) (:events ledger)))

(deftest a-truncated-turn-is-retried-once-accounted-and-never-in-history
  (let [finish (tool-response "done" {:summary "6"})
        ;; Original contract: the exact Opus turn fails the task, as in plan d6e9b40d.
        off (execute-script {"root" [(opus-response :imdb-truncated) finish]} {} nil tool-config)
        on (execute-script {"root" [(opus-response :imdb-truncated) finish]} {} nil contract-config)
        twice (execute-script {"root" [(opus-response :imdb-truncated) (opus-response :imdb-truncated) finish]}
                              {} nil contract-config)
        [first-call second-call] (:observed on)]
    (is (= :failed (:status (:result off))))
    (is (= {:summary "6"} (:result on)))
    ;; The same request again: the truncated turn never entered history.
    (is (= (:messages first-call) (:messages second-call)))
    (is (= 2 (get-in on [:ledger :spent :calls])))
    (is (= 1 (:transport-retries-issued (:ledger on))))
    (is (nil? (:command-corrections-issued (:ledger on))))
    (is (= [{:reason :truncated-tool-turn :attempt 1 :retried true :executed false}]
           (map #(select-keys (:payload %) [:reason :attempt :retried :executed]) (events (:ledger on) :provider-turn-retried))))
    (is (empty? (events (:ledger on) :command-rejected)))
    ;; Bounded: a second truncation with one retry allowed fails, charged and recorded.
    (is (= "Provider turn truncated; transport retry budget exhausted" (get-in twice [:result :error])))
    (is (= 2 (get-in twice [:ledger :spent :calls])))
    (is (= [true false] (map #(get-in % [:payload :retried]) (events (:ledger twice) :provider-turn-retried))))))

(deftest transport-retries-and-format-corrections-are-separate-allowances
  (let [r (execute-script {"root" [(opus-response :imdb-truncated)
                                   (tool-response "repl_eval" {})
                                   (tool-response "done" {:summary "6"})]} {} nil contract-config)]
    (is (= {:summary "6"} (:result r)))
    (is (= 1 (:transport-retries-issued (:ledger r))))
    (is (= 1 (:command-corrections-issued (:ledger r))))))

(deftest a-final-answer-line-is-accepted-only-after-the-terminal-instruction
  (let [opus [(opus-response :formality-text-1) (opus-response :formality-text-2)]
        compliant [(opus-response :formality-text-1) (text-reply "FINAL ANSWER: Label: formal")]
        ;; The exact Opus trajectory fails under both contracts: the second reply has no marker.
        off (execute-script {"root" opus} {} nil tool-config)
        on (execute-script {"root" opus} {} nil contract-config)
        ok (execute-script {"root" compliant} {} nil contract-config)
        legacy (execute-script {"root" compliant} {} nil tool-config)
        [_ second-request] (:observed ok)]
    (is (= :failed (:status (:result off))))
    (is (= "Command response rejected; no correction permitted" (get-in on [:result :error])))
    (is (= {:summary "Label: formal"} (:result ok)))
    (is (re-find #"FINAL ANSWER: <the exact final answer>" (:content (last (:messages second-request)))))
    (is (= ["Label: formal"] (map #(get-in % [:payload :answer]) (events (:ledger ok) :terminal-text-accepted))))
    (is (= 2 (get-in ok [:ledger :spent :calls])))
    ;; Without the switch the same compliant reply is never an answer.
    (is (= :failed (:status (:result legacy))))
    (is (empty? (events (:ledger legacy) :terminal-text-accepted)))))

(deftest terminal-answers-are-refused-outside-their-one-narrow-path
  (let [marker (text-reply "FINAL ANSWER: 6")
        ;; Not asked for yet: the first reply with a marker only earns the correction.
        unasked (execute-script {"root" [marker (tool-response "done" {:summary "7"})]} {} nil contract-config)
        ;; The correction was spent on a different error: no instruction, no acceptance.
        spent (execute-script {"root" [(tool-response "repl_eval" {}) (text-reply "I am done.") marker]} {} nil contract-config)
        ;; A child session never answers the task in text.
        child (execute-script {"root" [(tool-response "agent_call" {:id "c" :task "t"}) (tool-response "done" {:summary "root"})]
                               "c" [(text-reply "I am done.") marker]} {:calls 12} nil contract-config)
        ;; Commentary in reply to the instruction is refused.
        chatty (execute-script {"root" [(text-reply "Done.") (text-reply "Here it is.\nFINAL ANSWER: 6")]} {} nil contract-config)]
    (is (= {:summary "7"} (:result unasked)))
    (is (empty? (events (:ledger unasked) :terminal-text-accepted)))
    (is (= :failed (:status (:result spent))))
    (is (empty? (events (:ledger spent) :terminal-text-accepted)))
    (is (empty? (events (:ledger child) :terminal-text-accepted)))
    (is (= "Command response rejected; no correction permitted" (get-in chatty [:result :error])))))

;; The matched Python surface (research/Q_SUBSTRATE_BRIEF.md, Phase 2): the same tool envelope,
;; prompt structure, previews, paging and answer delivery over the Python worker, and no change
;; to any Clojure text. Worker behaviour itself is proved by repl-lab.python-contract.
(def python-config (assoc bounded-config :execution-language :python))

(deftest python-surface-shares-the-tool-envelope-and-changes-no-clojure-text
  (let [clojure-tools (wire/tool-definitions bounded-config) python-tools (wire/tool-definitions python-config)
        by-name (fn [tools] (into {} (map (juxt :name identity) tools)))
        changed (set (for [[n t] (by-name python-tools) :when (not= t (get (by-name clojure-tools) n))] n))]
    (is (= (map :name clojure-tools) (map :name python-tools)))
    (is (= (map :input_schema clojure-tools) (map :input_schema python-tools)))
    (is (= #{"repl_eval" "done" "agent_call"} changed))
    (doseq [t python-tools] (is (not (re-find #"Clojure|SCI|EDN" (:description t))) (:name t)))
    (doseq [t clojure-tools :when (changed (:name t))] (is (not (re-find #"Python" (:description t))) (:name t)))
    (is (every? #(str/includes? (:description (get (by-name python-tools) "repl_eval")) %) (wire/sci-rules python-config)))
    (is (str/includes? (:description (get (by-name python-tools) "repl_eval")) "full_result"))
    (is (= (wire/tool-definitions bounded-config) (wire/tool-definitions (assoc bounded-config :execution-language :clojure))))))

(deftest python-instructions-differ-from-clojure-only-in-language-terms
  (let [clojure-text (slurp "resources/external-tools-assisted.txt")
        terms [["experimental Clojure RLM" "experimental Python RLM"] ["and SCI." "and an isolated Python interpreter."]
               ["build it in SCI" "build it in the interpreter"] ["repl_eval runs Clojure in SCI:" "repl_eval runs Python in the isolated interpreter:"]]]
    (is (= (slurp "resources/external-tools-python.txt") (reduce (fn [t [a b]] (str/replace t a b)) clojure-text terms)))
    (is (str/includes? (external/instructions python-config) "- Send one or more statements"))
    (is (not (str/includes? (external/instructions python-config) "{{SCI_RULES}}")))
    (is (str/includes? (external/instructions bounded-config) "- Send one or more forms"))
    (is (= {:context "external_context" :worker "interpreter worker" :compute "in the interpreter"} (external/worker-text python-config)))
    (is (= {:context "external-context" :worker "SCI worker" :compute "in SCI"} (external/worker-text bounded-config)))))

(deftest python-source-wrappers-are-worker-requests-not-clojure-forms
  (is (= {:source "x = 1\nx" :display {:limit 60000 :preview 24000}} (wire/assisted-source python-config :repl/eval "x = 1\nx")))
  (is (= {:source "'a'" :answer true} (wire/answer-source python-config "'a'")))
  (is (thrown-with-msg? Exception #"Source is empty" (wire/assisted-source python-config :repl/eval " ")))
  ;; Python source is never read as Clojure; the worker's own parser judges it.
  (is (map? (wire/assisted-source python-config :repl/eval "x = (")))
  (is (string? (wire/assisted-source bounded-config :repl/eval "(+ 1 2)")))
  (is (string? (wire/answer-source bounded-config "\"a\""))))

(deftest python-results-and-errors-are-explained-in-python-terms
  (let [text (fn [config result]
               (:content (first (:content (second (wire/result-messages config {:content [{:type "tool_use" :id "t" :name "repl_eval" :input {}}]} result))))))
        truncated {:aljure/truncated true :total-chars 100002 :shown-chars 24000 :items nil :kind "string" :preview "'xx"}]
    (is (= "hi\n4" (text python-config {:value "hi\n4"})))
    (is (str/includes? (text python-config {:value truncated}) "The full text is bound to full_result; read more with page(full_result, 24000, 24000)."))
    (is (str/includes? (text bounded-config {:value truncated}) "(page full-result 24000 24000)"))
    (is (re-find #"It is not defined in this worker" (text python-config {:error "Worker rejected expression: NameError: name 'foo' is not defined"})))
    (is (re-find #"Imports are limited" (text python-config {:error "Worker rejected expression: ImportError: Module is outside the computation capability set"})))
    (is (re-find #"keeps running" (text python-config {:error "Worker rejected expression: ValueError: Printed output limit (1 MiB)"})))
    ;; Each language's hints apply to its own errors only.
    (is (not (re-find #"parse-long" (text python-config {:error "Worker rejected expression: Could not resolve symbol: Long/parseLong"}))))
    (is (not (re-find #"Imports are limited" (text bounded-config {:error "Worker rejected expression: ImportError: Module is outside the computation capability set"}))))))

(deftest python-settings-need-the-matched-surface
  (is (= :python (:execution-language (external/sci-settings {:sci {:surface "assisted" :results "bounded"} :execution-language "python"}))))
  (is (= :clojure (:execution-language (external/sci-settings {}))))
  (is (thrown? Exception (external/sci-settings {:execution-language "python"})))
  (is (thrown? Exception (external/sci-settings {:sci {:surface "assisted" :results "raw"} :execution-language "python"})))
  (is (thrown? Exception (external/sci-settings {:sci {:surface "assisted" :results "bounded"} :execution-language "python" :contract {:structured-labels true}})))
  (is (thrown? Exception (external/sci-settings {:sci {:surface "assisted" :results "bounded"} :execution-language "python" :contract {:artifacts {}}})))
  (is (thrown? Exception (external/sci-settings {:sci {:surface "assisted" :results "bounded"} :execution-language "ruby"}))))

(defn- code-point-checksum
  "An independent copy of the Python worker's checksum (python_worker.py) for the fake worker."
  [^String s]
  (let [h (reduce (fn [h cp] (mod (+ (* 31 h) cp) 4294967296)) 0 (iterator-seq (.iterator (.codePoints s))))]
    (if (>= h 2147483648) (- h 4294967296) h)))

(defn- fake-python-worker
  "Answers the controller's answer and page requests for one fixed answer string, as the Python
  worker would: lengths and slices in code points, the 31-polynomial checksum."
  [answer]
  (fn [_ source _]
    (if (map? source)
      (do (is (= {:source "ANSWER" :answer true} source)) [(.codePointCount answer 0 (count answer)) (code-point-checksum answer)])
      (let [[_ n limit start] (re-find #"^\[min\((\d+), (\d+)\), aljure_answer\[(\d+):min\(\d+, \d+\)\]\]$" source)
            start (parse-long start) end (min (parse-long n) (parse-long limit))
            from (.offsetByCodePoints answer 0 start) to (.offsetByCodePoints answer 0 end)]
        [end (subs answer from to)]))))

(deftest python-answers-are-paged-by-code-points-and-checked
  ;; 96354 and 131519 are the values the real worker returns (test_python/test_python_worker.py).
  (is (= 96354 (code-point-checksum "abc")))
  (is (= 131519 (code-point-checksum "a😀")))
  (doseq [[answer pages] [[(apply str (repeat 10000 "y")) 3] [(apply str (repeat 5000 "a😀")) 3] ["abc" 1]]]
    (with-redefs [runtime/open-worker! (fn [& _] ::worker)
                  isolation/close-session! (fn [_] nil)
                  isolation/evaluate! (fake-python-worker answer)]
      (let [{:keys [result ledger]} (execute-script {"root" [(tool-response "done" {:source "ANSWER"})]} {} nil python-config)
            delivered (first (filter #(= :answer-delivered (:type %)) (:events ledger)))]
        (is (= {:summary answer} result))
        (is (= pages (get-in delivered [:payload :pages])))
        ;; Recorded in the worker's own unit, code points.
        (is (= (.codePointCount answer 0 (count answer)) (get-in delivered [:payload :chars])))))))
