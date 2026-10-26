(ns repl-lab.gateway-fixture
  (:require [clojure.java.io :as io] [repl-lab.gateway :as g] [repl-lab.controller :as c]
            [repl-lab.records :as records] [repl-lab.util :as u]))

(def config {:model "fixture-gateway-v1" :context-window 1000 :max-output 100
             :pinned-settings {:temperature 0} :routes ["aljure/task" "prime/task"]
             :rates {:input 2 :output 10 :cache-read 0.2 :cache-write-5m 2.5 :cache-write-1h 4}
             :limits {:calls 5 :tokens 10000 :usd 0.015 :wall-ms 120000 :concurrent-subagents 2}})
(def pricing {:input_tokens 2 :output_tokens 10 :cache_read_input_tokens 0.2
              :cache_creation_5m_input_tokens 2.5 :cache_creation_1h_input_tokens 4})
(def source-paths ["src/repl_lab/gateway.clj" "src/repl_lab/gateway_fixture.clj" "src/repl_lab/controller.clj"
                   "src/repl_lab/store.clj" "src/repl_lab/records.clj" "src/repl_lab/util.clj" "scripts/store.py"])
(defn snapshot [] (into {} (for [path source-paths] [path (u/sha (slurp path))])))
(defn scripted-response [id stream?]
  (let [message {:type "message" :id id :model (:model config) :role "assistant"
                 :content [{:type "text" :text "Developer-authored fixture"}] :stop_reason "end_turn"
                 :usage {:input_tokens 12 :output_tokens 3 :cache_read_input_tokens 5 :cache_creation_input_tokens 10
                         :cache_creation {:ephemeral_5m_input_tokens 6 :ephemeral_1h_input_tokens 4}}}]
    {:status 200 :content-type (if stream? "text/event-stream" "application/json")
     :body (if-not stream? (u/json-str message)
               (apply str (map #(str "data: " (u/json-str %) "\n\n")
                               [{:type "message_start" :message (assoc-in message [:usage :output_tokens] 1)}
                                {:type "message_delta" :usage {:output_tokens 2}}
                                {:type "message_delta" :usage {:output_tokens 3}}
                                {:type "message_stop"}])))}))

(defn run! [out]
  (u/ensure! (and (seq out) (not (.exists (io/file out)))) "Use a new output directory" {})
  (.mkdirs (io/file out))
  (let [sources (snapshot) gateway (g/create! (str out "/controller.sqlite") "gateway-fixture" config)
        request {:model (:model config) :messages [{:role "user" :content "Offline accounting fixture"}]
                 :temperature 0 :max_tokens 100 :stream false}
        calls (atom 0)
        manifest {:evidence "FIXTURE" :config config :pricing_usd_per_m pricing :source_files sources
                  :model_calls 0 :provider_billing_usd nil :live_ready false}]
    (u/write-json! (str out "/manifest.json") manifest)
    (try
      (doseq [[route stream?] [["aljure/task" false] ["prime/task" true]]]
        (g/dispatch! gateway route (assoc request :stream stream?)
                     (fn [_] (scripted-response (str "fixture-" (swap! calls inc)) stream?))))
      (let [uncertain? (try (g/dispatch! gateway "prime/task" request
                             (fn [_] (swap! calls inc) (throw (ex-info "Scripted interrupted response" {})))) false
                           (catch Exception _ true))
            _ (g/recover! gateway)
            retry-blocked? (try (g/dispatch! gateway "prime/task" request
                                 (fn [_] (swap! calls inc) (scripted-response "unexpected-retry" false))) false
                               (catch Exception _ true))
            ledger (c/get-run (:store gateway) (:run gateway))
            passed (and uncertain? retry-blocked? (= 3 @calls) (= 2 (get-in ledger [:spent :calls]))
                        (= 1 (get-in ledger [:reserved :calls])) (= :gateway-stopped (:status ledger))
                        (= sources (snapshot)))
            report {:evidence "FIXTURE" :passed passed :model_calls 0 :scripted_transport_calls @calls
                    :spent (:spent ledger) :reserved (:reserved ledger) :status (:status ledger)
                    :unknown_preserved uncertain? :retry_blocked_after_reopen retry-blocked?
                    :live_ready false :provider_billing_usd nil
                    :limitations ["Injected transport only; no HTTP, native provider routing or network-isolation proof"
                                  "Declared model context ceiling needs verification before live use"
                                  "Gateway request identities are not verified native agent ancestry"]}]
        (u/write-json! (str out "/report.json") report)
        (u/ensure! passed "Gateway fixture failed; inspect preserved ledger" {})
        report)
      (finally
        (records/write-events! (str out "/events.jsonl") (:events (c/get-run (:store gateway) (:run gateway))))
        (records/write-events! (str out "/usage.jsonl") (g/normalized-usage gateway))))))

(defn -main [& [out]]
  (try (println (u/json-str (run! out)))
       (catch Exception e (binding [*out* *err*] (println (.getMessage e))) (System/exit 2))
       (finally (shutdown-agents))))
