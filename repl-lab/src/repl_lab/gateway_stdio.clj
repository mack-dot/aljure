(ns repl-lab.gateway-stdio
  "Trusted host-only bridge. The transport must wait for provider-request before
   dispatch. Current protocol explicitly accepts FIXTURE experiments only."
  (:require [clojure.java.io :as io] [repl-lab.gateway :as g] [repl-lab.controller :as c]
            [repl-lab.records :as records] [repl-lab.util :as u]))

(defn emit! [value] (println (u/json-str value)) (flush))
(defn receive! []
  (when-let [line (read-line)]
    (u/ensure! (<= (alength (.getBytes line "UTF-8")) 5242880) "Bridge frame too large" {})
    (u/json-read line)))
(defn export! [{:keys [store run] :as gateway} out]
  (let [ledger (c/get-run store run)]
    (records/write-events! (str out "/events.jsonl") (:events ledger))
    (records/write-events! (str out "/usage.jsonl") (g/normalized-usage gateway))
    (let [report {:evidence "FIXTURE" :model_calls 0 :live_ready false
                  :status (:status ledger) :spent (:spent ledger) :reserved (:reserved ledger)}]
      (u/write-json! (str out "/report.json") report)
      report)))

(defn serve! [out]
  (let [{:keys [evidence config]} (receive!)]
    (u/ensure! (= "FIXTURE" evidence) "Only explicit offline fixture bridging is implemented" {})
    (u/ensure! (not (.exists (io/file out))) "Use a new gateway directory" {})
    (let [gateway (g/create! (str out "/controller.sqlite") "stdio-gateway" config)]
      (u/write-json! (str out "/manifest.json") {:evidence evidence :config config :model_calls 0 :live_ready false})
      (try
        (emit! {:type "gateway_ready"})
        (loop []
          (when-let [command (receive!)]
            (if (= "close" (:op command))
              (emit! {:type "gateway_closed" :report (export! gateway out)})
              (do
                (try
                  (u/ensure! (= "invoke" (:op command)) "Unknown bridge operation" {})
                  (let [result (g/dispatch! gateway (:route command) (:body command)
                                 (fn [body]
                                   ;; This frame is emitted only AFTER durable reservation.
                                   (emit! {:type "provider_request" :body body})
                                   (let [reply (receive!)]
                                     (u/ensure! (= "provider_response" (:type reply)) "Missing transport response" {})
                                     (:response reply))))]
                    (emit! {:type "gateway_result" :response result}))
                  (catch Exception _ (emit! {:type "gateway_error" :message "Dispatch rejected or outcome uncertain; inspect ledger"})))
                (recur)))))
        (finally (export! gateway out))))))

(defn -main [& [out action]]
  (try
    (u/ensure! (seq out) "Output directory required" {})
    (if (= action "recover")
      (let [gateway {:store (str out "/controller.sqlite") :run "stdio-gateway"}]
        (u/ensure! (c/get-run (:store gateway) (:run gateway)) "Gateway ledger is missing" {})
        (g/recover! gateway)
        (emit! {:type "gateway_recovered" :report (export! gateway out)}))
      (serve! out))
    (catch Exception _ (binding [*out* *err*] (println "Gateway bridge failed; inspect its durable ledger")) (System/exit 2))
    (finally (shutdown-agents))))
