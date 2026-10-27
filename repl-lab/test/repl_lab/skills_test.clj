(ns repl-lab.skills-test
  (:require [clojure.test :refer :all] [repl-lab.skills :as skills]
            [repl-lab.util :as u] [repl-lab.artifact :as a] [repl-lab.fixtures :as f]
            [repl-lab.runtime-test :as rt] [repl-lab.runtime :as runtime]
            [repl-lab.controller :as c]))

(deftest registry-is-derived-and-progressively-disclosed
  (let [root (rt/temp-root)]
    (doseq [artifact [f/initial-policy f/initial-workflow f/packed-policy]] (a/save! root artifact))
    (let [items (skills/inventory root (:hash f/initial-workflow)) item (first items)]
      (is (= 1 (count items)))
      (is (= "serial-resource-fit" (:name item)))
      (is (= (:interface f/initial-policy) (:interface item)))
      (is (= 11 (get-in item [:validation-evidence :completed])))
      (is (= (:hash f/initial-policy) (:version-hash item)))
      (is (not-any? #(contains? item %) [:source :forms]))
      (is (= f/initial-policy (skills/select-policy root (:hash f/initial-workflow) (:hash f/initial-policy))))
      (is (thrown? Exception (skills/select-policy root (:hash f/initial-workflow) (:hash f/packed-policy))))
      (is (thrown? Exception (skills/describe root (:hash f/initial-workflow) (:hash f/packed-policy))))
      (is (= (u/hash-value (dissoc item :metadata-hash)) (:metadata-hash item)))))
  ;; Model claims are not metadata: unreviewed hashes receive interface-only text.
  (let [candidate (assoc f/packed-policy :description "Guaranteed optimal" :approved true)]
    (is (thrown? Exception (skills/entry candidate (skills/reviewed-catalog)))))
  (let [item (skills/entry f/packed-policy (skills/reviewed-catalog))]
    (is (= :derived-interface-only (get-in item [:metadata-validation :method])))
    (is (= :unreviewed (get-in item [:applicability :status]))))
  (with-redefs [u/sha (constantly "changed")]
    (is (thrown-with-msg? Exception #"evidence changed" (skills/reviewed-catalog)))))

(deftest selection-is-scoped-and-last-successful-choice-wins
  (let [root (rt/temp-root) store (str root "/test.sqlite") run "selection"
        env {:registry root :store store :run run :workers (atom {})}]
    (doseq [item [f/initial-policy f/initial-workflow f/packed-policy]] (a/save! root item))
    (c/create-run! store run rt/config (:hash f/initial-workflow)) (c/session! store run "root" nil)
    (runtime/broker! env "root" {:op :policy/use :source (:source f/packed-policy)})
    (runtime/broker! env "root" {:op :policy/select :hash (:hash f/initial-policy)})
    (is (= f/initial-policy (runtime/selected-policy root (c/get-run store run) "root" nil)))
    (is (thrown? Exception (runtime/broker! env "root" {:op :policy/select :hash (:hash f/packed-policy)})))
    (is (= f/initial-policy (runtime/selected-policy root (c/get-run store run) "root" nil)))
    (runtime/broker! env "root" {:op :policy/use :source (:source f/packed-policy)})
    (is (= (:forms f/packed-policy) (:forms (runtime/selected-policy root (c/get-run store run) "root" nil))))
    (is (thrown? Exception (runtime/broker! env "root" {:op :skills/register :approved true})))
    (is (= 1 (count (:skills (runtime/broker! env "root" {:op :skills/list})))))))
