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

(defn execute-script [queues overrides after-call]
  (let [root (temp-root) store (str root "/controller.sqlite") observed (atom [])
        cfg (update strict-config :limits merge {:usd 1} overrides)
        env {:store store :run "run" :workers (atom {}) :base-instructions "Fixture envelope test"
             :provider (->AccountedScript (atom queues) observed after-call)}]
    (c/create-run! store "run" cfg nil) (c/session! store "run" "root" nil)
    (let [result (runtime/run-session! env "root" {:task "Fixture only"})]
      {:env env :result result :observed @observed :ledger (c/get-run store "run")})))

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
