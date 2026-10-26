(ns repl-lab.provider-crash-probe
  "Trusted, test-only provider transport. Never contacts an inference service."
  (:require [repl-lab.controller :as c] [repl-lab.provider :as p]
            [repl-lab.artifact :as a] [repl-lab.fixtures :as f]
            [repl-lab.live :as live] [repl-lab.experiment :as experiment]
            [repl-lab.workloads :as workloads] [repl-lab.util :as u]))

(def request [{:role "user" :content "Synthetic provider crash fixture"}])
(def response
  {:model "fixture-model-id" :id "synthetic-response"
   :usage {:input_tokens 12 :output_tokens 3}
   :content [{:type "text" :text "{:op :done :summary \"synthetic response\"}"}]})
(def adapter (p/->AnthropicProvider "fixture-model-id" "offline-test-not-a-credential" 1.0 2.0 32))
(def config (-> (u/read-file "config/experiment.edn")
                (assoc :mode :live :provenance :synthetic-fixture)
                (assoc-in [:limits :calls] 1) (assoc-in [:limits :usd] 1.0)))
(def world (workloads/generate 993 {:size 3}))
(def run-id "provider-crash-evolving-0")
(defn task-root [root] (str root "/tasks/evolving-0"))
(defn store-path [root] (str (task-root root) "/controller.sqlite"))
(defn boundary! [root chosen stage]
  (when (= chosen stage)
    (u/atomic-write! (str root "/ready-to-kill") stage)
    ;; The parent test must kill this process group; a normal exit fails the test.
    (Thread/sleep 60000)
    (u/fail "Parent did not kill the provider fixture" {:stage stage})))

(defn invoke-probe! [root point caller]
  (let [store (store-path root) original-reconcile c/reconcile!]
    (doseq [artifact [f/initial-policy f/initial-workflow]] (a/save! (task-root root) artifact))
    (c/create-run! store run-id config (:hash f/initial-workflow))
    (c/session! store run-id "root" nil)
    (when (= caller "child") (c/session! store run-id "child" "root"))
    (with-redefs
      [p/http-post!
       (fn [path _body _key]
         (when (= path "messages/count_tokens") (boundary! root point "after-reservation"))
         (spit (str root "/transport.jsonl") (str (u/json-str {:path path :provenance :synthetic-fixture}) "\n") :append true)
         (case path
           "messages/count_tokens" {:input_tokens 12}
           "messages" (do (boundary! root point "request-dispatched") response)))
       c/reconcile!
       (fn [store run id answer]
         (boundary! root point "before-response-commit")
         (let [result (original-reconcile store run id answer)]
           (boundary! root point "after-response-commit")
           result))]
      (p/invoke! adapter store run-id caller request))))

(defn summary [ledger]
  {:spent (:spent ledger) :reserved (:reserved ledger)
   :requests (:provider-requests ledger)
   :sessions (into {} (map (fn [[id s]] [id (select-keys s [:parent :status])]) (:sessions ledger)))
   :unknown-events (count (filter #(= :provider-outcome-unknown (:type %)) (:events ledger)))})

(defn recover-probe! [root]
  (let [store (store-path root) before (c/get-run store run-id)
        forbidden (fn [& _] (u/fail "Recovery attempted execution or inference" {}))
        env {:root root :id "provider-crash" :config config :provenance :synthetic-fixture
             :execute forbidden :provider (reify p/Provider (invoke! [_ _ _ _ _] (forbidden)))}
        result (live/recorded-or-new-task! env :evolving 0 world [] f/initial-workflow)
        after (c/get-run store run-id)
        repeated (live/recorded-or-new-task! env :evolving 0 world [] f/initial-workflow)
        playback (try {:entries (count (p/playback-entries after))}
                      (catch Exception _ {:unknown-outcome true}))]
    {:provenance :synthetic-fixture :before (summary before) :after (summary after)
     :checkpoint-status (:status result) :episode-status (get-in result [:episode :metrics :status])
     :idempotent (and (= result repeated) (= after (c/get-run store run-id)))
     :playback playback :replayed (:replayed (experiment/replay! root))}))

(defn -main [& [op root point caller]]
  (case op
    "invoke" (invoke-probe! root point caller)
    "recover" (println (u/json-str (recover-probe! root))))
  (shutdown-agents))
