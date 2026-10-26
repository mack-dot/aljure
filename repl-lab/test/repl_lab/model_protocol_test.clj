(ns repl-lab.model-protocol-test
  (:require [clojure.test :refer :all] [repl-lab.model-protocol :as wire]
            [repl-lab.artifact :as a] [repl-lab.runtime-test :refer [temp-root]]
            [repl-lab.util :as u] [repl-lab.bundle :as bundle] [repl-lab.records :as records]))

(deftest json-commands-preserve-operations-and-literal-data
  (doseq [lang [:clojure :python]]
    (let [config {:command-format :json :execution-language lang}]
      (doseq [command [{:op :repl/eval :source "literal #= text" :bindings {:op "dispatch"}}
                       {:op :context/query :handle "jobs" :query {:where {:ready true} :select [:id]}}
                       {:op :agent/call :id "child" :task "Count" :context [{:op "dispatch"}]}
                       {:op :done :summary {:op "retain-this-string"}}]]
        (is (= command (wire/parse-command config (wire/write-command config command)))))
      (is (= "context/query" (:op (u/json-read (wire/write-command config {:op :context/query})))))
      (is (thrown? Exception (wire/parse-command config "{\"op\":true}")))
      (is (thrown? Exception (wire/parse-command config "{:op :done}")))
      (is (thrown? Exception (wire/parse-command config (str "{\"op\":\"done\",\"summary\":\"" (apply str (repeat 33000 "x")) "\"}")))))))

(deftest structural-json-paths-retain-language-semantics
  (doseq [[lang path replacement] [[:clojure [2 :answer] '(+ x 1)]
                                  [:python [:fields :body 0 :fields :value] {:node "Constant" :fields {:value 3 :kind nil}}]]]
    (let [config {:command-format :json :execution-language lang}
          command {:op :artifact/patch :hash "h" :base-hash "h" :path path :expected-hash "v"
                   :replacement replacement :dependencies []}]
      (is (= command (wire/parse-command config (wire/write-command config command))))
      (let [get-subtree {:op :artifact/subtree :hash "h" :path path}]
        (is (= get-subtree (wire/parse-command config (wire/write-command config get-subtree)))))))
  (let [config {:command-format :json}
        command {:op :artifact/submit :category :workflow :source "{:strategy {:policy \"h\" :context {:select [:id]}}}"
                 :interface {:name "workflow"} :dependencies ["h"] :parent nil}]
    (is (= (u/read-edn (:source command))
           (u/read-edn (:source (wire/parse-command config (wire/write-command config command))))))))

(deftest source-and-forms-must-agree-even-with-a-recomputed-hash
  (let [artifact (a/make-artifact {:category :analysis :source "(fn [x] (+ x 1))" :interface {:name "solve" :arity 1}
                                  :dependencies [] :author "fixture" :parent nil :provenance :developer-fixture})
        corrupted (assoc artifact :forms '(fn [x] (+ x 2)))
        corrupted (assoc corrupted :hash (u/hash-value (dissoc corrupted :hash)))]
    (is (thrown? Exception (a/verify corrupted)))
    (is (= "(fn [x] (+ x 1))" (:forms-edn (wire/inspect-artifact {:command-format :json} artifact))))))

(deftest neutral-promotion-rule-rejects-regression-and-unpaired-data
  (let [rule {:objective :verified-cases :min-score-improvement 1}
        old [{:case "a" :passed true} {:case "b" :passed false}]]
    (is (:approved (a/promotion-evidence old (mapv #(assoc % :passed true) old) rule)))
    (is (not (:approved (a/promotion-evidence old old rule))))
    (is (not (:approved (a/promotion-evidence old [{:case "a" :passed false} {:case "b" :passed true}] rule))))
    (is (thrown? Exception (a/promotion-evidence old [{:case "a" :passed true}] rule)))
    (is (thrown? Exception (a/promotion-evidence old [{:case "a" :passed true} {:case "b" :passed 1}] rule)))))

(deftest bundle-rejects-narrative-fields-even-if-file-digests-match
  (let [root (temp-root) output (str root "/export")
        artifact (a/make-artifact {:category :analysis :source "(fn [x] x)" :interface {:name "solve" :arity 1}
                                  :dependencies [] :author "fixture" :parent nil :provenance :developer-fixture})]
    (a/save! root artifact)
    (let [manifest (bundle/export! root output (:hash artifact) :synthetic-fixture)
          file (first (keys (:files manifest)))
          item (assoc (u/read-file (str output "/" file)) :conversation ["private task memory"])
          body (pr-str item)]
      (u/atomic-write! (str output "/" file) body)
      (u/write-edn! (str output "/manifest.edn")
                    (assoc-in manifest [:files file] {:sha256 (u/sha body) :bytes (count (.getBytes body "UTF-8"))}))
      (is (thrown-with-msg? Exception #"Unexpected executable bundle fields" (bundle/load-bundle output))))))

(deftest dependency-closure-rejects-ambiguous-exports-and-mixed-languages
  (let [root (temp-root)
        make (fn [name source dependencies]
               (a/make-artifact {:category :analysis :source source :interface {:name name :arity 1}
                                 :dependencies dependencies :author "fixture" :parent nil :provenance :developer-fixture}))
        first-helper (make "helper" "(fn [x] x)" [])
        other-helper (make "helper" "(fn [x] (+ x 1))" [])
        good (make "solve" "(fn [x] (helper x))" [(:hash first-helper)])
        ambiguous (make "solve" "(fn [x] (helper x))" [(:hash first-helper) (:hash other-helper)])]
    (a/save! root first-helper) (a/save! root other-helper)
    (is (= [first-helper] (a/dependency-closure root good)))
    (is (thrown-with-msg? Exception #"Conflicting exported" (a/dependency-closure root ambiguous)))
    ;; Language conflict is checked before attempting to execute either source.
    (is (thrown-with-msg? Exception #"Mixed execution languages" (a/dependency-closure root (assoc good :language :python))))))

(deftest exported-traces-preserve-namespaced-operation-identities
  (let [path (str (temp-root) "/events.jsonl")]
    (records/write-events! path [{:type :tool-call :payload {:command {:op :artifact/call}}}])
    (is (= "artifact/call" (get-in (u/json-read (slurp path)) [:payload :command :op])))))
