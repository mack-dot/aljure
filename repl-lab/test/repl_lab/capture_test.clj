(ns repl-lab.capture-test
  "Controller-assisted capture and the acquisition modes (research/UNBLOCK_ACQUISITION.md).
  Model code is read, never evaluated; no Docker and no model call."
  (:require [clojure.test :refer :all] [clojure.string :as str]
            [repl-lab.capture :as capture] [repl-lab.acquisition :as acq] [repl-lab.model-protocol :as wire]))

(defn- by-name [candidates] (into {} (map (juxt :name identity) candidates)))

(deftest captures-named-let-bound-and-anonymous-text-tests-verbatim
  (let [sources ["(defn loc? [q] (re-find #\"^Where \" q))"
                 "(def num-re #\"^How many \")"
                 "(let [qs (map #(second (re-find #\"Instance: (.*)\" %)) context-lines) hum #\"^Who \" desc? (fn [q] (re-find #\"^Why \" q))] [(count (filter #(re-find hum %) qs)) (count (filter desc? qs)) (count (filter #(re-find num-re %) qs))])"]
        cs (capture/candidates sources)
        named (by-name cs)]
    (is (every? (comp empty? :reasons) (vals (dissoc named "anonymous"))))
    (is (= "(fn [q] (re-find (re-pattern \"^Where \") q))" (:source (named "loc?"))))
    ;; A named pattern becomes the test the model ran with it; the wrapper is recorded as an adapter.
    (is (= ["regex-detector-v1" :regex] ((juxt :adapter :kind) (named "num-re"))))
    (is (= ["regex-detector-v1" :regex] ((juxt :adapter :kind) (named "hum"))))
    ;; A let-bound fn and anonymous predicates keep their forms; earlier bindings and session defs they call are inlined.
    (is (= "(fn [q] (re-find (re-pattern \"^Why \") q))" (:source (named "desc?"))))
    (let [anonymous (filter #(= "anonymous" (:name %)) cs)
          sources (set (map :source anonymous))]
      (is (some #(and (str/includes? % "(let [hum (re-pattern \"^Who \")]") (empty? (:reasons (first (filter (fn [c] (= % (:source c))) anonymous))))) sources))
      (is (some #(str/includes? % "(let [num-re (re-pattern \"^How many \")]") sources)))
    (is (= (count cs) (count (set (map :source cs)))) "one candidate per distinct portable form")
    (is (= (mapv #(str "c" %) (range 1 (inc (count cs)))) (mapv :id cs)))
    (is (every? #(re-matches #"[0-9a-f]{64}" (:source-sha256 %)) cs))))

(deftest session-data-index-sets-unresolved-names-and-helpers-are-not-captured
  (let [sources ["(def rows (vec context-lines))"
                 "(def ent #{1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22})"
                 "(defn seen? [q] (re-find (re-pattern (first rows)) q))"
                 "(defn listed? [i] (and (ent i) (re-find #\"x\" (str i))))"
                 "(defn other? [q] (re-find mystery q))"
                 "(defn helper [r] (:f r))"]
        named (by-name (capture/candidates sources))]
    (is (= [[:session-data "context-lines"]] (:reasons (named "seen?"))))
    (is (= [[:literal-data-set "ent"]] (:reasons (named "listed?"))))
    (is (= [[:unresolved "mystery"]] (:reasons (named "other?"))))
    (is (= [[:not-a-text-test]] (:reasons (named "helper"))))))

(deftest a-true-false-test-is-wrapped-for-its-named-label
  (let [c (first (capture/candidates ["(defn loc? [q] (re-find #\"^Where \" q))"]))]
    (is (= "(fn [text] (when ((fn [q] (re-find (re-pattern \"^Where \") q)) text) \"location\"))"
           (capture/adapted-source c "location")))
    (is (= (:source c) (capture/adapted-source c nil)))
    ;; The adapted source is one readable fn form, as every proposal must be.
    (is (= 1 (count (wire/read-forms (capture/adapted-source c "location")))))))

(deftest structured-and-capture-turns-state-their-terms-and-require-a-decline-reason
  (let [structured (acq/proposal-tools "E" "structured" nil)
        cs (capture/candidates ["(defn loc? [q] (re-find #\"^Where \" q))"])
        captured (acq/proposal-tools "E" "capture" cs)]
    (is (= ["propose_artifact" "skip_proposal"] (mapv :name structured)))
    (is (= ["reason"] (get-in (second structured) [:input_schema :required])))
    (is (= ["capture_artifact" "skip_proposal"] (mapv :name captured)))
    (is (= ["c1"] (get-in (first captured) [:input_schema :properties :candidate :enum])))
    (is (= ["reason"] (get-in (second captured) [:input_schema :required])))
    ;; The optional mode is the thesis pilot's turn, byte for byte.
    (is (= (acq/proposal-tools "E") (acq/proposal-tools "E" "optional" nil)))
    (is (= (acq/instruction "E") (acq/instruction "E" "optional" nil)))
    (is (str/includes? (acq/instruction "E" "structured" nil) "give your reason in one sentence"))
    (is (str/includes? (acq/instruction "E" "capture" cs) "[c1] loc?: (fn [q] (re-find (re-pattern \"^Where \") q))"))
    (is (thrown? Exception (acq/proposal-tools "C" "capture" cs)))))

(deftest anonymous-fn-parameters-become-plain-symbols-the-artifact-store-reads
  ;; #(...) reads as (fn* [p1__N#] ...); the trailing # is refused by the artifact store's EDN reader.
  (let [c (first (filter #(= "anonymous" (:name %)) (capture/candidates ["(let [qs [] hum #\"^Who \"] (count (filter #(re-find hum %) qs)))"])))]
    (is (= "(fn [arg__1] (let [hum (re-pattern \"^Who \")] (re-find hum arg__1)))" (:source c)))
    (is (= '(fn [arg__1] (re-find (re-pattern "x") arg__1)) (repl-lab.util/read-edn (capture/printed (capture/plain-gensyms (first (wire/read-forms "#(re-find #\"x\" %)"))))))))
  (is (= '(fn [q] q) (capture/plain-gensyms '(fn [q] q)))))

(deftest rule-v2-keeps-a-precision-floor-and-abstains-per-label
  (let [v1 {:schema "aljure-promotion-rule-v1" :min_precision [19 20] :min_coverage [1 10] :min_panel_gain 1}
        v2 (assoc v1 :schema "aljure-promotion-rule-v2" :label_abstention true)
        candidate {:items 100 :decided 50 :correct 50 :errors [] :non-labels 0 :admitted-windows ["w"]}
        evidence {:no-regression true :score-gain 122}]
    ;; The seed's case: a 99.2%-precise second entry after a 99.25% first one.
    (is (= [:library-precision-regression]
           (:reasons (acq/decide v1 candidate {:decided 133 :correct 132} {:decided 256 :correct 254} evidence))))
    (is (:approved (acq/decide v2 candidate {:decided 133 :correct 132} {:decided 256 :correct 254} evidence)))
    (is (= [:library-precision-below-floor]
           (:reasons (acq/decide v2 candidate {:decided 0 :correct 0} {:decided 100 :correct 90} {:no-regression true :score-gain 90}))))
    (is (= ["description and abstract concept"]
           (acq/abstained-labels v2 {"abbreviation" [132 133] "description and abstract concept" [88 125]})))
    (is (= v2 (acq/check-rule! v2)))
    (is (thrown? Exception (acq/check-rule! (dissoc v2 :label_abstention))))))
