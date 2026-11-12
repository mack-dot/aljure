(ns repl-lab.verification-test
  "Switchable verification contract: helpers, prompt text, evidence gate and
  finalization provenance. Fixture workers only; no container or inference."
  (:require [clojure.test :refer :all] [clojure.string :as str] [repl-lab.runtime :as runtime]
            [repl-lab.isolation :as isolation] [repl-lab.external-task :as external]
            [repl-lab.command-envelope-test :refer [execute-script tool-response tool-config]] [repl-lab.util]))

(def gate-config (assoc tool-config :contract {:structured-labels true :uncertainty-audit true :targeted-review true}))

(defn audit-worker
  "Answers the controller's audit query with the given report; anything else is 7."
  [audit queries]
  (fn [_ source _]
    (if (str/includes? source "(deref aljure-audit)") (do (swap! queries conj source) audit) 7)))

(defn- run-with [audit cfg steps]
  (let [queries (atom [])]
    (with-redefs [runtime/open-worker! (fn [& _] ::worker)
                  isolation/close-session! (fn [_] nil)
                  isolation/evaluate! (audit-worker audit queries)]
      (assoc (execute-script {"root" steps} {} nil cfg) :queries @queries))))

(defn- events [ledger kind] (filter #(= kind (:type %)) (:events ledger)))

(def open-audit {:open 3 :missing-count 0 :unresolved-count 2 :conflict-count 1 :count-range {:c [120 123]}})

(deftest the-evidence-gate-answers-one-done-with-the-models-own-open-audit
  (let [steps [(tool-response "repl_eval" {:source "(audit-labels ids labels)"})
               (tool-response "done" {:summary "Answer: 120"})
               (tool-response "done" {:summary "Answer: 122"})]
        on (run-with open-audit gate-config steps)
        [_ _ third] (:observed on)
        notice (first (:content (last (:messages third))))]
    ;; The first done is answered by the notice, not run; the next done is accepted.
    (is (= {:summary "Answer: 122"} (:result on)))
    (is (= 3 (get-in on [:ledger :spent :calls])))
    (is (= 1 (:evidence-gates-issued (:ledger on))))
    (is (= [open-audit] (map #(get-in % [:payload :audit]) (events (:ledger on) :evidence-gate))))
    (is (= "tool_result" (:type notice)))
    (is (re-find #"Not submitted\. Your last audit-labels left 3 items open \(0 missing, 2 unknown, 1 conflicting\)" (:content notice)))
    (is (= ["done"] (map #(name (get-in % [:payload :command :op])) (filter #(= :done (get-in % [:payload :command :op]))
                                                                             (events (:ledger on) :tool-call)))))
    ;; Separate from the format correction and the transport retry.
    (is (nil? (:command-corrections-issued (:ledger on))))
    (is (nil? (:transport-retries-issued (:ledger on))))))

(deftest the-evidence-gate-costs-nothing-unless-enabled-and-an-audit-is-open
  (let [steps [(tool-response "repl_eval" {:source "1"}) (tool-response "done" {:summary "Answer: 120"})]
        off (run-with open-audit tool-config steps)
        helpers-only (run-with open-audit (assoc tool-config :contract {:structured-labels true :uncertainty-audit true}) steps)
        complete (run-with (assoc open-audit :open 0) gate-config steps)
        never-audited (run-with nil gate-config steps)
        no-worker (run-with open-audit gate-config [(tool-response "done" {:summary "Answer: 1"})])]
    (doseq [r [off helpers-only complete never-audited]]
      (is (= {:summary "Answer: 120"} (:result r)))
      (is (= 2 (get-in r [:ledger :spent :calls])))
      (is (empty? (events (:ledger r) :evidence-gate))))
    ;; Off, the controller never even asks the worker.
    (is (empty? (:queries off)))
    (is (empty? (:queries helpers-only)))
    (is (= {:summary "Answer: 1"} (:result no-worker)))
    (is (empty? (:queries no-worker)))))

(deftest prompt-text-appears-only-with-its-switch
  (let [assisted (assoc tool-config :sci-surface :assisted :sci-results :bounded)
        base (external/instructions assisted)
        labels (external/instructions (assoc assisted :contract {:structured-labels true}))
        audit (external/instructions (assoc assisted :contract {:structured-labels true :uncertainty-audit true}))
        review (external/instructions (assoc assisted :contract {:structured-labels true :uncertainty-audit true :targeted-review true}))]
    (is (= base (external/instructions (assoc assisted :contract {:truncated-turn-retries 1 :terminal-text-answer true}))))
    (is (not (str/includes? base "audit-labels")))
    (is (= labels (str base "\n" (slurp "resources/structured-labels.txt"))))
    (is (= audit (str labels (slurp "resources/uncertainty-audit.txt"))))
    (is (= review (str audit (slurp "resources/targeted-review.txt"))))
    ;; Each level adds only its own text: labels never mention the audit, the audit never asks for review.
    (is (not (str/includes? labels "audit-labels")))
    (is (not (str/includes? audit "reread")))
    (is (str/includes? audit "not whether a label is right"))))

(deftest the-answer-records-how-it-was-delivered
  (is (= "done" (external/finalization [{:type :tool-call :payload {:session "root"}}])))
  (is (= "terminal-text" (external/finalization [{:type :terminal-text-accepted :payload {:session "root" :answer "6"}}])))
  (is (= "done" (external/finalization [{:type :terminal-text-accepted :payload {:session "c1" :answer "6"}}]))))

(deftest a-preflight-the-controller-times-out-still-leaves-a-refusal
  ;; A supervisor that hangs past the wait is killed; the refusal must still be on disk
  ;; for the paired runner's stop rule, and the doctor must report not ready.
  (let [dir (str (System/getProperty "java.io.tmpdir") "/doctor-" (System/nanoTime))
        hang (java.io.File/createTempFile "hang" ".py")]
    (spit hang "import time\ntime.sleep(30)\n")
    (with-redefs [isolation/script (fn [_] (.getPath hang))
                  isolation/audit-dir (fn [] dir)]
      (binding [isolation/*doctor-wait-s* 1]
        (is (= {:ready false :reason "Isolation preflight timeout"} (isolation/doctor)))))
    (let [records (.listFiles (clojure.java.io/file dir "preflight"))]
      (is (= 1 (count records)))
      (is (= {:ready false :reason "Isolation preflight timeout" :doctor-wait-s 1}
             (repl-lab.util/json-read (slurp (first records))))))))

(def format-config (assoc tool-config :contract {:answer-format {:max_lines 1 :max_chars 64}}))

(deftest the-answer-format-notice-fires-once-and-never-rewrites
  (let [verbose "Answer: 285\n\nThis is an estimate from my own reading of 602 sentences."
        notice (fn [r] (first (:content (last (:messages (nth (:observed r) 1))))))
        ;; A verbose answer, then a conforming one: one notice, the second answer is run as given.
        fixed (run-with nil format-config [(tool-response "done" {:summary verbose}) (tool-response "done" {:summary "Answer: 285"})])
        ;; Verbose twice: the second is accepted exactly as written and recorded.
        stubborn (run-with nil format-config [(tool-response "done" {:summary verbose}) (tool-response "done" {:summary verbose})])
        conforming (run-with nil format-config [(tool-response "done" {:summary "Answer: 285"})])
        off (run-with nil tool-config [(tool-response "done" {:summary verbose})])]
    (is (= {:summary "Answer: 285"} (:result fixed)))
    (is (= 2 (get-in fixed [:ledger :spent :calls])))
    (is (= [{:session "root" :lines 3 :chars (count verbose) :max-lines 1 :max-chars 64 :executed false}]
           (map :payload (events (:ledger fixed) :answer-format-notice))))
    (is (re-find #"^Not submitted: the final answer must be only the answer" (:content (notice fixed))))
    (is (= {:summary verbose} (:result stubborn)))
    (is (= 1 (count (events (:ledger stubborn) :answer-format-notice))))
    (is (= 1 (count (events (:ledger stubborn) :answer-format-accepted-nonconforming))))
    (doseq [r [conforming off]]
      (is (= 1 (get-in r [:ledger :spent :calls])))
      (is (empty? (events (:ledger r) :answer-format-notice))))
    (is (= {:summary verbose} (:result off)))
    ;; Separate from the format correction and the transport retry.
    (is (nil? (:command-corrections-issued (:ledger fixed))))))
