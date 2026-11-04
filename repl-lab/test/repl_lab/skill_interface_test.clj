(ns repl-lab.skill-interface-test
  (:require [clojure.test :refer :all] [clojure.string :as str]
            [repl-lab.skill-interface :as view] [repl-lab.model-protocol :as wire]
            [repl-lab.executable :as executable] [repl-lab.runtime :as runtime]
            [repl-lab.artifact :as a] [repl-lab.skills :as skills]
            [repl-lab.controller :as c] [repl-lab.runtime-test :refer [config temp-root]]))

(def on {:response-envelope :native-tool-v1 :sci-surface :assisted :contract {:skill-interface "inspect-v1"}})
(def off (dissoc on :contract))
(defn artifact [name source]
  (a/make-artifact {:category :analysis :source source :interface {:name name :arity 1}
                   :dependencies [] :author "fixture" :parent nil :provenance :developer-fixture}))
(defn fixture []
  (let [f (artifact "generic-helper" "(fn [x] (str x))") p (artifact "applicable" "(fn [x] true)")
        entry {:artifact (:hash f) :function f :code-hash (a/code-hash f) :predicate p
               :dependencies [] :applicability (:hash p) :applicability-code-hash (a/code-hash p)
               :summary "A fixture, not a routing task." :receipt {:candidate-panel {:correct 1 :items 1}}
               :check {:decision :preload :reason :applicable}}
        plan (executable/preload-plan [entry])]
    {:f f :entry entry :plan plan
     :catalog (view/snapshot (:functions plan) [entry] (:decisions plan) "pin")}))
(defn inspect [catalog h & [extra]] (view/inspect catalog (merge {:hash h :section "function" :offset 0 :limit 4096} extra)))
(defn response [tool input] {:stop-reason "tool_use" :content [{:type "tool_use" :id "fixture" :name tool :input input}]})

(deftest baseline-is-unchanged-and-tool-grant-is-explicit
  (is (= (wire/tool-definitions off) (wire/tool-definitions (assoc off :contract {}))))
  (is (= ["context_metadata" "context_query" "repl_eval" "agent_call" "done"] (mapv :name (wire/tool-definitions off))))
  (is (= ["artifact_inspect" "artifact_call"] (mapv :name (drop 5 (wire/tool-definitions on)))))
  (is (thrown? Exception (wire/parse-response off (response "artifact_inspect" {:hash "h"}) runtime/schemas)))
  (is (= {:op :skill/inspect :hash "h" :section "function" :offset 0 :limit 4096}
         (wire/parse-response on (response "artifact_inspect" {:hash "h"}) runtime/schemas)))
  (is (thrown? Exception (wire/parse-response on (response "artifact_inspect" {:hash "h" :path "/etc/passwd"}) runtime/schemas)))
  (is (str/includes? (wire/explain-error on "Worker rejected expression: Could not resolve symbol: source") "artifact_inspect"))
  (is (not (str/includes? (wire/explain-error off "Worker rejected expression: Could not resolve symbol: source") "artifact_inspect"))))

(deftest approved-source-is-data-and-pages-are-bounded
  (let [{:keys [f catalog]} (fixture) h (:hash f) page (inspect catalog h)]
    (is (= (:forms f) (read-string (:source page))))
    (is (= (a/code-hash f) (:code-hash page)))
    (is (= "(generic-helper arg1)" (:call page)))
    (is (= {:candidate-panel {:correct 1 :items 1}} (:validation page)))
    (is (:invocation-allowed page))
    (is (= "(fn [x] true)" (:source (inspect catalog h {:section "applicability"}))))
    (let [long-source (apply str (repeat 9000 "x")) catalog (assoc-in catalog [h :source] long-source)]
      (is (= 4096 (count (:source (inspect catalog h)))))
      (is (= 4096 (:next-offset (inspect catalog h))))
      (is (= (subs long-source 4096) (str (:source (inspect catalog h {:offset 4096}))
                                                       (:source (inspect catalog h {:offset 8192}))))))
    ;; Inspection never evaluates even source that requests a host effect.
    (is (= "(spit \"/tmp/do-not-create\" \"bad\")"
           (:source (inspect (assoc-in catalog [h :source] "(spit \"/tmp/do-not-create\" \"bad\")") h))))
    (doseq [bad ["../../etc/passwd" "/etc/passwd" (apply str (repeat 64 "0")) nil {} 42]]
      (is (thrown? Exception (inspect catalog bad))))
    (doseq [bad [{:offset -1} {:offset 999999} {:offset 0.5} {:limit 0} {:limit 4097}
                 {:limit "5"} {:section "filesystem"} {:offset nil}]]
      (is (thrown? Exception (inspect catalog h bad))))))

(deftest approved-but-inapplicable-is-inspectable-without-execution-authority
  (let [{:keys [entry]} (fixture) entry (assoc entry :check {:decision :refuse :reason :inapplicable})
        plan (executable/preload-plan [entry]) catalog (view/snapshot (:functions plan) [entry] (:decisions plan) "pin")]
    (is (false? (:invocation-allowed (inspect catalog (:artifact entry)))))
    (is (= {:decision :refuse :reason :inapplicable} (:admission (inspect catalog (:artifact entry)))))
    (is (empty? (:functions plan)))
    (is (= 1 (count (:functions (view/inventory catalog)))))))

(deftest external-invocation-uses-approved-immutable-target-and-existing-isolation
  (let [{:keys [f catalog]} (fixture) root (temp-root) store (str root "/state.sqlite") run "test"
        run-config (merge config on) _ (c/create-run! store run run-config nil) _ (c/session! store run "root" nil)
        initialize (fn [_ _] :initialized)
        called (atom []) env {:store store :run run :workers (atom {}) :registry "wrong-registry"
                             :skill-catalog catalog :external-artifact-library "pinned-library"
                             :external-artifact-initialize initialize
                             :external-artifact-targets {(:hash f) f}}]
    (with-redefs [executable/invoke! (fn [library target args deadline & [init]]
                                     (swap! called conj [library target args deadline init]) "ok")]
      (is (= {:value "ok" :artifact (:hash f)} (runtime/broker! env "root" {:op :artifact/call :hash (:hash f) :arguments ["literal"]})))
      (is (= ["pinned-library" f ["literal"]] (take 3 (first @called))))
      ;; The isolated call worker is initialized like the session's workers (context + assisted helpers).
      (is (identical? initialize (nth (first @called) 4)))
      (is (thrown? Exception (runtime/broker! (assoc env :external-artifact-targets {}) "root"
                                            {:op :artifact/call :hash (:hash f) :arguments ["literal"]})))
      (is (thrown? Exception (runtime/broker! env "root" {:op :artifact/call :hash "../../etc/passwd" :arguments []})))
      (runtime/broker! env "root" {:op :skill/inspect :hash (:hash f) :section "function" :offset 0 :limit 4096})
      (is (= 1 (count @called)))
      (let [events (:events (c/get-run store run)) invoked (filter #(= :artifact-invoked (:type %)) events)]
        (is (= 1 (count invoked)))
        (is (= (a/code-hash f) (get-in (first invoked) [:payload :code-hash])))))))

(deftest invocation-log-counts-nil-returns-apart-and-rejects-impossible-counts
  ;; A probe that returns nil is executed but decides nothing (run-3 baseline task 1).
  (is (str/includes? (first (executable/preload-sources [])) ":nils 0"))
  (is (str/includes? (first (executable/preload-sources [])) "(if (nil? v) (update r :nils inc) r)"))
  (let [drain (fn [log] (with-redefs [repl-lab.execution/evaluate! (fn [& _] log)] (executable/drain! nil nil #{"h"})))]
    (is (= {:invocations [{:calls 2 :returns 2 :values ["retry"] :nils 1 :code-hash "h"}]}
           (drain {"h" {:calls 2 :returns 2 :nils 1 :values ["retry"]}})))
    ;; Earlier logs without the field read as zero nil returns.
    (is (= {:invocations [{:calls 1 :returns 1 :values [] :nils 0 :code-hash "h"}]} (drain {"h" {:calls 1 :returns 1 :values []}})))
    (is (= {:error "Malformed invocation log"} (drain {"h" {:calls 1 :returns 1 :nils 2 :values []}})))
    (is (= {:error "Malformed invocation log"} (drain {"h" {:calls 1 :returns 1 :nils -1 :values []}})))))

(deftest names-only-variant-withholds-summaries-and-changes-nothing-else
  (let [names (assoc-in on [:contract :skill-interface] "inspect-v1-names")
        {:keys [f entry]} (fixture) h (:hash f) plan (executable/preload-plan [entry])
        shown (view/snapshot (:functions plan) [entry] (:decisions plan) "pin")
        withheld (view/snapshot (:functions plan) [entry] (:decisions plan) "pin" {:withhold-summaries true})]
    (is (view/enabled? names))
    (is (view/summaries-withheld? names))
    (is (not (view/summaries-withheld? on)))
    (is (not (view/enabled? (assoc-in on [:contract :skill-interface] "inspect-v2"))))
    ;; Same tools, same schemas, same error help.
    (is (= (wire/tool-definitions on) (wire/tool-definitions names)))
    (is (str/includes? (wire/explain-error names "Worker rejected expression: Could not resolve symbol: source") "artifact_inspect"))
    ;; The default snapshot keeps the summary; the withheld one carries no summary anywhere.
    (is (= "A fixture, not a routing task." (:summary (first (:functions (view/inventory shown))))))
    (is (= "A fixture, not a routing task." (:summary (inspect shown h))))
    (is (str/starts-with? (:limits (view/inventory shown)) "Summaries are model-authored."))
    (let [entry' (first (:functions (view/inventory withheld))) page (inspect withheld h)]
      (is (nil? (:summary entry')))
      (is (true? (:summary-withheld entry')))
      (is (nil? (:summary page)))
      (is (true? (:summary-withheld page)))
      (is (str/starts-with? (:limits (view/inventory withheld)) "Summaries are withheld on this task."))
      (is (not (str/includes? (pr-str (view/inventory withheld)) "fixture, not a routing")))
      (is (not (str/includes? (pr-str page) "fixture, not a routing")))
      ;; Source, call syntax, admission and authority are unchanged.
      (is (= (:source (inspect shown h)) (:source page)))
      (is (= (:call (inspect shown h)) (:call page)))
      (is (= (:invocation-allowed (inspect shown h)) (:invocation-allowed page)))
      (is (= (dissoc (inspect shown h) :summary) (dissoc page :summary-withheld))))))
