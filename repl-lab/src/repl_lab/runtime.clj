(ns repl-lab.runtime
  (:require [clojure.string :as str] [repl-lab.util :as u] [repl-lab.controller :as c] [repl-lab.provider :as p]
            [repl-lab.artifact :as a] [repl-lab.isolation :as isolation]))

(def schemas
  {:context/query #{:op :handle :query} :context/metadata #{:op :handle}
   :repl/eval #{:op :source :bindings} :agent/call #{:op :id :task :context}
   :message/send #{:op :recipient :correlation-id :payload} :message/receive #{:op}
   :agent/await #{:op :id} :agent/cancel #{:op :id}
   :artifact/submit #{:op :category :source :interface :dependencies :parent}
   :development/evaluate #{:op :hash} :policy/use #{:op :source} :done #{:op :summary}})
(declare run-session!)
(defn broker! [{:keys [store run registry provider workers development-evaluator allow-learning] :as env} session command]
  (let [r (c/get-run store run) op (:op command) s (get-in r [:sessions session])]
    (c/within-time! r)
    (u/ensure! (and s (= :ready (:status s))) "Session cannot use broker" {})
    (u/ensure! (= (get schemas op) (set (keys command))) "Unknown capability or invalid schema" {:op op})
    (u/ensure! (<= (count (.getBytes (pr-str command) "UTF-8")) 32768) "Tool request too large" {})
    (c/update-run! store run #(c/event % :tool-call {:session session :command command :artifact (:artifact s)}))
    (case op
      :context/query (c/context store run (:handle command) (:query command))
      :context/metadata (dissoc (c/context store run (:handle command) {:limit 1 :select []}) :records)
      :repl/eval (let [worker (or (get @workers session)
                                  (let [new (isolation/open-session!)] (swap! workers assoc session new) new))]
                   {:value (isolation/evaluate! worker (:source command) (:bindings command))})
      :agent/call
      (let [id (:id command) _ (u/ensure! (and (string? id) (<= 1 (count id) 128) (not= id session)) "Invalid child ID" {})
            prior (get-in r [:sessions id])]
        (if prior
          (do (u/ensure! (= session (:parent prior)) "Only parent can resume child" {}) (c/resume-session! store run id))
          (c/session! store run id session))
        (c/send! store run {:message-id (str (java.util.UUID/randomUUID)) :run-id run :sender session :recipient id
                           :correlation-id id :schema-version 1 :payload (select-keys command [:task :context])})
        (let [result (run-session! env id (select-keys command [:task :context]))]
          (c/update-run! store run #(c/event % :child-result-consumed {:parent session :child id :result result}))
          result))
      :message/send (do (c/send! store run {:message-id (str (java.util.UUID/randomUUID)) :run-id run :sender session
                                           :recipient (:recipient command) :correlation-id (:correlation-id command)
                                           :schema-version 1 :payload (:payload command)}) {:sent true})
      :message/receive (let [messages (c/deliver! store run session)]
                         (doseq [m messages] (c/acknowledge! store run session (:message-id m) {:received (:payload m)}))
                         {:messages messages})
      :agent/await (do (u/ensure! (= session (get-in r [:sessions (:id command) :parent])) "Only parent can await child" {})
                      (c/await-status store run (:id command)))
      :agent/cancel (do (u/ensure! (= session (get-in r [:sessions (:id command) :parent])) "Only parent may cancel child" {})
                       (c/cancel! store run (:id command)) {:cancelled true})
      :artifact/submit (do
                         (u/ensure! allow-learning "Library is frozen" {})
                         (c/consume! store run :candidates 1)
                         (let [artifact (a/make-artifact (-> command (dissoc :op) (assoc :author session :provenance (if (= :synthetic-fixture (:provenance env)) :developer-fixture :model-generated))))]
                           (doseq [dep (:dependencies artifact)] (a/load! registry dep))
                           (a/save! registry artifact)
                           (c/update-run! store run #(c/event % :artifact-staged {:hash (:hash artifact) :session session}))
                           {:hash (:hash artifact) :status :staged}))
      :development/evaluate (do (u/ensure! (and allow-learning development-evaluator) "Development evaluation is unavailable" {})
                                (development-evaluator (:hash command)))
      :policy/use (let [artifact (a/make-artifact {:category :policy :source (:source command)
                                                   :interface {:name "decide" :arity 2} :dependencies []
                                                   :author session :parent nil :provenance (if (= :synthetic-fixture (:provenance env)) :developer-fixture :model-generated)})]
                    (c/update-run! store run #(assoc-in % [:sessions session :temporary-policy] artifact))
                    {:hash (:hash artifact) :scope :current-task-only})
      :done {:summary (:summary command)})))

(defn run-session! [{:keys [store run provider workers] :as env} session task]
  (try
    (loop [messages (let [r (c/get-run store run) base (slurp "resources/base-instructions.txt")
                          history (->> (get-in r [:sessions session :history]) (filter :role)
                                       (remove #(str/starts-with? (:content %) base))
                                       (take-last (get-in r [:config :limits :history-records])))]
                      (vec (concat [{:role "user" :content base}] history [{:role "user" :content (pr-str task)}]))) n 0]
      (u/ensure! (< n 64) "Session tool-step limit" {})
      (let [response (p/invoke! provider store run session messages)
            command (u/read-edn (:text response))]
        (if (= :done (:op command))
          (let [result (broker! env session command)]
            (c/finish-session! store run session :complete result) result)
          (let [result (try (broker! env session command)
                            (catch Exception e {:error (.getMessage e)}))
                r (c/get-run store run) cap (get-in r [:config :limits :history-records])
                next (into [(first messages)]
                           (take-last cap (concat (rest messages)
                                                  [{:role "assistant" :content (:text response)}
                                                   {:role "user" :content (pr-str result)}])))]
            (c/update-run! store run #(assoc-in % [:sessions session :history] next))
            (recur next (inc n))))))
    (catch Exception e
      (c/finish-session! store run session :failed {:error (.getMessage e)})
      {:error (.getMessage e) :status :failed})
    (finally
      (when-let [worker (get @workers session)]
        (isolation/close-session! worker) (swap! workers dissoc session)))))

(defn workflow! [store run workflow context-handle child-call]
  (let [strategy (get-in workflow [:forms :strategy])
        _ (u/ensure! (and (map? strategy) (map? (:context strategy)) (string? (:policy strategy))) "Invalid workflow" {})
        selected (c/context store run context-handle (:context strategy))
        result (when-let [delegation (:delegate strategy)] (child-call (:task delegation) (:records selected)))]
    (c/update-run! store run #(c/event % :workflow-invoked
                                     {:artifact (:hash workflow) :input-handle context-handle
                                      :selected (:records selected) :child-result result :policy (:policy strategy)}))
    {:policy (:policy strategy) :evidence selected :child-result result}))
