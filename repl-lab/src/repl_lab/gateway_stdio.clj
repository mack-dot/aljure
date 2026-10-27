(ns repl-lab.gateway-stdio
  "Trusted host-only bridge. The transport must wait for provider-request before
   dispatch. The caller must authorize any live transport; this bridge never opens a network."
  (:require [clojure.java.io :as io] [repl-lab.gateway :as g] [repl-lab.controller :as c]
            [repl-lab.records :as records] [repl-lab.util :as u]))

(defn emit! [value] (println (u/json-str value)) (flush))
(defn receive! []
  (when-let [line (read-line)]
    (u/ensure! (<= (alength (.getBytes line "UTF-8")) 5242880) "Bridge frame too large" {})
    (u/json-read line)))
(defn export! [{:keys [store run] :as gateway} out]
  (let [ledger (c/get-run store run)
        manifest (u/json-read (slurp (str out "/manifest.json")))
        evidence (:evidence manifest)
        _ (u/ensure! (#{"FIXTURE" "LIVE MODEL RUN"} evidence) "Missing persisted gateway evidence category" {})]
    (records/write-events! (str out "/events.jsonl") (:events ledger))
    (records/write-events! (str out "/usage.jsonl") (g/normalized-usage gateway))
    (let [report {:evidence evidence :bridge_protocol (get manifest :bridge_protocol 1)
                  :model_calls (if (= "FIXTURE" evidence) 0 (count (:provider-requests ledger)))
                  :completed_requests (get-in ledger [:spent :calls])
                  :uncertain_requests (get-in ledger [:reserved :calls]) :live_ready false
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

(defn serve-v2! [out]
  ;; Admission and completion are separate so concurrent native children keep
  ;; independent reservations while the host transport performs bounded I/O.
  (let [{:keys [evidence config]} (receive!)
        _ (u/ensure! (#{"FIXTURE" "LIVE MODEL RUN"} evidence) "Explicit bridge evidence required" {})
        _ (u/ensure! (not (.exists (io/file out))) "Use a new gateway directory" {})
        gateway (g/create! (str out "/controller.sqlite") "stdio-gateway" config)
        pending (atom {}) seen (atom #{})
        save! (fn [] (export! gateway out))]
    (u/write-json! (str out "/manifest.json") {:evidence evidence :config config :bridge_protocol 2})
    (try
      (emit! {:type "gateway_ready" :bridge_protocol 2})
      (loop []
        (when-let [command (receive!)]
          (if (= "close" (:op command))
            (do (doseq [[_ admission] @pending] (g/stop-uncertain! gateway (:id admission)))
                (reset! pending {}) (emit! {:type "gateway_closed" :report (save!)}))
            (do
              (try
                (let [id (:transport_id command)]
                  (u/ensure! (and (string? id) (<= 1 (count id) 128)) "Invalid transport ID" {})
                  (case (:op command)
                    "invoke"
                    (do (u/ensure! (not (@seen id)) "Duplicate transport ID" {})
                        (swap! seen conj id)
                        (let [admission (g/admit! gateway (:route command) (:body command))]
                          (swap! pending assoc id admission)
                          (emit! {:type "provider_request" :transport_id id :request_id (:id admission)
                                  :body (:body command)})))
                    "provider_response"
                    (let [admission (get @pending id)]
                      (u/ensure! admission "Missing request admission" {})
                      (swap! pending dissoc id)
                      (if (:transport_error command)
                        (do (g/stop-uncertain! gateway (:id admission))
                            (emit! {:type "gateway_error" :transport_id id :message "Provider outcome uncertain"}))
                        (let [result (g/finish! gateway admission (:response command))]
                          (if (:cleanup_failure command)
                            (do (g/stop-uncertain! gateway (:id admission))
                                (emit! {:type "gateway_error" :transport_id id :message "Transport cleanup failed after receipt"}))
                            (emit! {:type "gateway_result" :transport_id id :response result})))))
                    (u/fail "Unknown bridge operation" {})))
                (catch Exception _ (emit! {:type "gateway_error" :transport_id (:transport_id command)
                                          :message "Dispatch rejected or outcome uncertain; inspect ledger"})))
              (recur)))))
      (finally
        (doseq [[_ admission] @pending] (g/stop-uncertain! gateway (:id admission)))
        (save!)))))

(defn -main [& [out action]]
  (try
    (u/ensure! (seq out) "Output directory required" {})
    (if (= action "recover")
      (let [gateway {:store (str out "/controller.sqlite") :run "stdio-gateway"}]
        (u/ensure! (c/get-run (:store gateway) (:run gateway)) "Gateway ledger is missing" {})
        (g/recover! gateway)
        (emit! {:type "gateway_recovered" :report (export! gateway out)}))
      (if (= action "v2") (serve-v2! out) (serve! out)))
    (catch Exception _ (binding [*out* *err*] (println "Gateway bridge failed; inspect its durable ledger")) (System/exit 2))
    (finally (shutdown-agents))))
