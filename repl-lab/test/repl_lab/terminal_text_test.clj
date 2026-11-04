(ns repl-lab.terminal-text-test
  "Contract text-answer-v2: strict, deterministic acceptance of a terminal text answer, with
  provenance, and every rejection case. The runtime tests go through the production
  ExternalProvider with scripted gateway replies (transport_failure_test/run-external)."
  (:require [clojure.test :refer [deftest is testing]]
            [clojure.string :as str]
            [repl-lab.model-protocol :as wire]
            [repl-lab.external-task :as external]
            [repl-lab.transport-failure-test :as tf]
            [repl-lab.util :as u]))

(defn- text-reply [text & {:keys [stop blocks] :or {stop "end_turn"}}]
  {:text text :stop-reason stop
   :content (or blocks [{:type "thinking" :thinking "fixture" :signature "s"} {:type "text" :text text}])})

(deftest v2-accepts-exactly-one-marked-line-and-keeps-the-scorer-marker
  (is (= "Answer: 6" (wire/terminal-text-answer-v2 (text-reply "Answer: 6"))))
  (is (= "Answer: 6" (wire/terminal-text-answer-v2
                       (text-reply "Answer: 6\n\nI read the 10 reviews dated between May 05, 2023 and Jun 13, 2025 and classified each by hand.\n- May 05: negative"))))
  (is (= "Label: formal" (wire/terminal-text-answer-v2 (text-reply "I judged them myself.\n  Label: formal  \nAbout 90 were formal."))))
  (is (= "Label: formal" (wire/terminal-text-answer-v2 (text-reply "FINAL ANSWER: Label: formal"))))
  (is (= "12" (wire/terminal-text-answer-v2 (text-reply "Reasoning first.\nFINAL ANSWER:   12  "))))
  (testing "deterministic: the same reply always gives the same answer"
    (let [r (text-reply "Answer: 6\nsome notes")]
      (is (= (wire/terminal-text-answer-v2 r) (wire/terminal-text-answer-v2 r) "Answer: 6")))))

(deftest v2-rejects-everything-else
  (doseq [[why r] [["no marker" (text-reply "The answer is 6.")]
                   ["two marked lines" (text-reply "Answer: 6\nAnswer: 7")]
                   ["marker and a second mention mid-line" (text-reply "Answer: 6\nThe Answer: above is final")]
                   ["two different markers" (text-reply "Label: formal\nFINAL ANSWER: Label: formal")]
                   ["lowercase marker" (text-reply "answer: 6")]
                   ["empty answer" (text-reply "Answer:")]
                   ["empty final answer" (text-reply "FINAL ANSWER:  ")]
                   ["tool_use stop reason" (text-reply "Answer: 6" :stop "tool_use")]
                   ["max_tokens stop reason" (text-reply "Answer: 6" :stop "max_tokens")]
                   ["a tool call in the blocks" (text-reply "Answer: 6" :blocks [{:type "text" :text "Answer: 6"} {:type "tool_use" :id "t" :name "done" :input {}}])]
                   ["no text block" (text-reply "Answer: 6" :blocks [{:type "thinking" :thinking "x" :signature "s"}])]
                   ["over the size bound" (text-reply (str "Answer: 6\n" (apply str (repeat 17000 "x"))))]
                   ["answer over 4096 characters" (text-reply (str "FINAL ANSWER: " (apply str (repeat 5000 "x"))))]]]
    (is (nil? (wire/terminal-text-answer-v2 r)) why)))

(deftest contract-versions-are-explicit
  (is (nil? (wire/terminal-text-version {:contract {}})))
  (is (nil? (wire/terminal-text-version {:contract {:terminal-text-answer false}})))
  (is (= "text-answer-v1" (wire/terminal-text-version {:contract {:terminal-text-answer true}})))
  (is (= "text-answer-v2" (wire/terminal-text-version {:contract {:terminal-text-answer "text-answer-v2"}})))
  (is (thrown? clojure.lang.ExceptionInfo (wire/terminal-text-version {:contract {:terminal-text-answer "text-answer-v3"}}))))

(defn- text-message [text]
  (#'tf/reply (#'tf/message [tf/thinking {:type "text" :text text}] "end_turn")))

(deftest v2-runtime-accepts-the-first-marked-text-reply-with-provenance
  (let [{:keys [result ledger]} (tf/run-external [(text-message "Answer: 6\n\nI counted them by hand.")]
                                                 :contract {:terminal-text-answer "text-answer-v2"})
        accepted (first (filter #(= :terminal-text-accepted (:type %)) (:events ledger)))]
    (is (= "Answer: 6" (:summary result)))
    (is (= {:session "root" :answer "Answer: 6" :version "text-answer-v2" :correction-used false :lines 3}
           (select-keys (:payload accepted) [:session :answer :version :correction-used :lines])))
    (is (string? (get-in accepted [:payload :response-hash])))
    (is (= "terminal-text" (external/finalization (:events ledger))))
    (is (= {:version "text-answer-v2" :correction-used false :lines 3 :response-hash (get-in accepted [:payload :response-hash])}
           (external/finalization-provenance (:events ledger))))
    (is (nil? (some #(= :command-rejected (:type %)) (:events ledger))) "no correction was spent")))

(deftest v2-runtime-still-corrects-an-unmarked-reply-and-accepts-the-corrected-one
  (let [{:keys [result ledger]} (tf/run-external [(text-message "I think it is 6.")
                                                  (text-message "Answer: 6")]
                                                 :contract {:terminal-text-answer "text-answer-v2"})
        accepted (first (filter #(= :terminal-text-accepted (:type %)) (:events ledger)))]
    (is (= "Answer: 6" (:summary result)))
    (is (= 1 (count (filter #(= :command-rejected (:type %)) (:events ledger)))))
    (is (true? (get-in accepted [:payload :correction-used])))))

(deftest v2-runtime-rejects-a-second-unmarked-reply-exactly-as-before
  (let [{:keys [result ledger]} (tf/run-external [(text-message "I think it is 6.")
                                                  (text-message "Still 6, I believe.")]
                                                 :contract {:terminal-text-answer "text-answer-v2"})]
    (is (= :failed (:status result)))
    (is (= 2 (count (filter #(= :command-rejected (:type %)) (:events ledger)))))
    (is (nil? (some #(= :terminal-text-accepted (:type %)) (:events ledger))))))

(deftest v1-runtime-behaviour-is-unchanged-by-v2
  (testing "v1 refuses a first marked reply and accepts only the FINAL ANSWER line after the correction"
    (let [{:keys [result ledger]} (tf/run-external [(text-message "Answer: 6")
                                                    (text-message "FINAL ANSWER: 6")]
                                                   :contract {:terminal-text-answer true})
          accepted (first (filter #(= :terminal-text-accepted (:type %)) (:events ledger)))]
      (is (= "6" (:summary result)))
      (is (= 1 (count (filter #(= :command-rejected (:type %)) (:events ledger)))))
      (is (= "text-answer-v1" (get-in accepted [:payload :version])))))
  (testing "off: the pilot-1 behaviour, two text replies end the session"
    (let [{:keys [result ledger]} (tf/run-external [(text-message "Answer: 6") (text-message "Answer: 6")])]
      (is (= :failed (:status result)))
      (is (nil? (some #(= :terminal-text-accepted (:type %)) (:events ledger)))))))
