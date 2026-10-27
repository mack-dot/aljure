(require '[repl-lab.gateway :as g] '[repl-lab.controller :as c] '[repl-lab.util :as u])
(let [store "var/analysis/sonnet-receipt-fix-v1/reconciled-gateway.sqlite" run "stdio-gateway"
      old (c/get-run store run) config (:config old)
      response (u/json-read (slurp "research/evidence/prime-head-to-head-v1-live-attempt1/provider-response.json"))
      id "255131fb-446c-49ef-b5a9-0f08254e5ef5"
      actual (g/receipt config response)]
  (u/ensure! (and (= 1 (count (:provider-requests old))) (= :unknown (get-in old [:provider-requests id :status]))
                  (= (:model config) (:model actual)) (= :gateway-stopped (:status old))) "Analysis input differs" {})
  (c/reconcile! store run id actual)
  (let [now (c/get-run store run)
        report {:evidence :OFFLINE-RECONCILIATION-OF-LIVE-RECEIPT :new-model-calls 0
                :original-ledger-modified false :run-status (:status now)
                :receipt actual :spent (:spent now) :reserved (:reserved now)
                :normalized-usage (g/normalized-usage {:store store :run run})}]
    (u/write-json! "var/analysis/sonnet-receipt-fix-v1/reconciliation.json" report)
    (println (u/json-str (select-keys report [:evidence :new-model-calls :run-status :spent :reserved])))))
(shutdown-agents)