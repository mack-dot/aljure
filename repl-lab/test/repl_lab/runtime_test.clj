(ns repl-lab.runtime-test
  (:require [clojure.test :refer :all] [clojure.string :as str] [repl-lab.util :as u] [repl-lab.store :as db]
            [repl-lab.controller :as c] [repl-lab.artifact :as a] [repl-lab.isolation :as isolation]
            [repl-lab.execution :as execution] [repl-lab.provider :as provider] [repl-lab.runtime :as runtime]))

(defn temp-root [] (str (java.nio.file.Files/createTempDirectory "repl-lab-test-" (make-array java.nio.file.attribute.FileAttribute 0))))
(def config (u/read-file "config/experiment.edn"))
(defn fixture []
  (let [root (temp-root) store (str root "/controller.sqlite")]
    (c/create-run! store "run" config "initial")
    (c/session! store "run" "root" nil)
    [root store]))
(defn envelope [id recipient] {:message-id id :run-id "run" :sender "root" :recipient recipient
                             :correlation-id "task" :schema-version 1 :payload {:evidence [1 2]}})

(deftest durable-mailboxes-and-effects
  (let [[_ store] (fixture) msg (envelope "m1" "child")]
    (c/session! store "run" "child" "root")
    (c/send! store "run" msg)
    (c/send! store "run" msg)
    (is (= 1 (count (:mailbox (c/get-run store "run")))))
    (is (= 1 (:deliveries (first (c/deliver! store "run" "child")))))
    ;; New storage subprocesses on every call simulate transport/controller reopen.
    (is (= 2 (:deliveries (first (c/deliver! store "run" "child")))))
    (c/acknowledge! store "run" "child" "m1" {:result :consumed})
    (c/acknowledge! store "run" "child" "m1" {:result :must-not-overwrite})
    (is (= [] (c/deliver! store "run" "child")))
    (is (= {:result :consumed} (get-in (c/get-run store "run") [:sessions "child" :effects "m1"])))
    (is (thrown? Exception (c/send! store "run" (assoc msg :payload {:changed true}))))
    (is (thrown? Exception (c/send! store "run" (envelope "m2" "missing"))))
    (c/finish-session! store "run" "child" :failed {:reason :fixture})
    (is (= :failed (:status (c/await-status store "run" "child"))))
    (is (= :missing (:status (c/await-status store "run" "missing"))))))

(deftest concurrency-depth-cancel-and-resume
  (let [[_ store] (fixture)]
    (c/session! store "run" "a" "root")
    (c/session! store "run" "b" "a")
    (is (thrown? Exception (c/session! store "run" "c" "root")))
    (is (thrown? Exception (c/session! store "run" "deep" "b")))
    (c/cancel! store "run" "a")
    (is (= :cancelled (:status (c/await-status store "run" "b"))))
    (c/session! store "run" "c" "root")
    (c/finish-session! store "run" "c" :complete {:result 1})
    (c/resume-session! store "run" "c")
    (is (= :ready (get-in (c/get-run store "run") [:sessions "c" :status])))))

(deftest budget-includes-inflight-and-crash-uncertainty
  (let [[_ store] (fixture)]
    (c/session! store "run" "a" "root")
    (c/reserve! store "run" "q1" "root" 60000 0.0)
    (is (thrown? Exception (c/reserve! store "run" "q2" "a" 5000 0.0)))
    (c/recover! store "run")
    (is (= :unknown (get-in (c/get-run store "run") [:provider-requests "q1" :status])))
    (is (= 60000 (get-in (c/get-run store "run") [:reserved :tokens])))
    (is (thrown? Exception (c/reserve! store "run" "q1" "root" 100 0.0))))
  (let [[_ store] (fixture)]
    (c/reserve! store "run" "q1" "root" 1000 0.0)
    (c/reconcile! store "run" "q1" {:tokens 100 :usd 0.0 :model "mock-v1"})
    (is (= 100 (get-in (c/get-run store "run") [:spent :tokens])))
    (is (= 0 (get-in (c/get-run store "run") [:reserved :tokens])))
    (is (thrown? Exception (c/reconcile! store "run" "q1" {:tokens 0 :usd 0.0}))))
  (let [[_ store] (fixture)]
    (c/reserve! store "run" "q1" "root" 10 0.0)
    (c/reconcile! store "run" "q1" {:tokens 11 :usd 0.0 :model "bad-mock"})
    (is (= :budget-overrun (:status (c/get-run store "run"))))))

(deftest bounded-approved-context
  (let [[_ store] (fixture)]
    (c/put-context! store "run" "observations" [{:id "a" :ready true :estimate 3} {:id "b" :ready false :estimate 9}])
    (is (= [{:id "a"}] (:records (c/context store "run" "observations" {:where {:ready true} :select [:id]}))))
    (is (thrown? Exception (c/context store "run" "heldout-seeds" {})))
    (is (thrown? Exception (c/context store "run" "observations" {:limit 1000})))))

(deftest immutable-context-blocks-preserve-queries-and-fail-closed
  (let [[_ store] (fixture)
        rows (mapv (fn [i] {:id i :ready (even? i) :text (apply str (repeat 400 "x"))}) (range 40))
        query {:where {:ready true} :offset 2 :limit 3 :select [:id]}]
    (c/put-context! store "run" "inline" rows)
    (c/put-context-block! store "run" "trace" rows)
    (is (= (dissoc (c/context store "run" "inline" query) :handle)
           (dissoc (c/context store "run" "trace" query) :handle)))
    (let [entry (get-in (c/get-run store "run") [:contexts "trace"])]
      (is (< (count (pr-str entry)) 200))
      (is (= rows (c/context-records store "run" entry)))
      (is (thrown? Exception (c/context store "run" "trace" {:limit 40})))
      (is (thrown? Exception (c/context-records store "another-run" entry)))
      (db/transact! store (str "run/context/" (:hash entry)) (constantly [{:corrupt true}]))
      (is (thrown-with-msg? Exception #"missing or corrupt" (c/context store "run" "trace" query)))
      (is (thrown-with-msg? Exception #"Immutable context block conflict" (c/put-context-block! store "run" "trace" rows))))
    (with-redefs [c/update-run! (fn [& _] (throw (ex-info "Simulated interruption before handle publication" {})))]
      (is (thrown? Exception (c/put-context-block! store "run" "unpublished" [{:id "not-published"}]))))
    (is (thrown? Exception (c/context store "run" "unpublished" {})))))

(defn candidate [parent source]
  (a/make-artifact {:category :policy :source source :interface {:name "decide" :arity 2}
                    :dependencies [] :author "developer" :parent parent :provenance :developer-fixture}))
(deftest structural-versioning-and-corruption
  (let [base (candidate nil "(fn [obs memory] {:actions [] :memory memory})")
        root (temp-root) path [2 :actions]
        patched (a/patch base {:base-hash (:hash base) :path path :expected-hash (u/hash-value [])
                               :replacement [{:op :wait :ticks 1}] :author "developer"})]
    (is (= [{:op :wait :ticks 1}] (a/subtree (:forms patched) path)))
    (is (= (:hash base) (:parent patched)))
    (is (not= (:hash base) (:hash patched)))
    (is (thrown? Exception (a/patch base {:base-hash "stale" :path path :expected-hash (u/hash-value []) :replacement []})))
    (is (thrown? Exception (a/patch base {:base-hash (:hash base) :path [99] :expected-hash (u/hash-value []) :replacement []})))
    (a/save! root patched)
    (is (= patched (a/load! root (:hash patched))))
    (spit (a/path-for root (:hash patched)) (pr-str (assoc patched :source "(fn [a b] nil)")))
    (is (thrown? Exception (a/load! root (:hash patched)))))
  (is (thrown? Exception (a/parse-source "#=(System/exit 0)")))
  (is (thrown? Exception (a/parse-source "(fn [] 1) (fn [] 2)")))
  (is (thrown? Exception (a/make-artifact {:category :host :source "{}"}))))

(deftest promotion-boundary-cas-and-restart
  (let [[root store] (fixture)
        a (candidate "initial" "(fn [obs memory] {:actions [] :memory memory})")
        old [{:case "d1" :completed 4 :makespan 10 :score 10 :accepted-invariant-violations 0}]
        new [(assoc (first old) :makespan 8 :score 8)]
        evidence (a/promotion-evidence old new (:promotion config))]
    (is (:approved evidence))
    (is (not (:approved (a/promotion-evidence old [(assoc (first new) :completed 3)] (:promotion config)))))
    (is (not (:approved (a/promotion-evidence old old (:promotion config)))))
    (is (thrown? Exception (a/promote! store "run" root a evidence)))
    (c/finish-session! store "run" "root" :complete {:summary :fixture})
    ;; Orphan files before a database commit never activate themselves.
    (a/save! root a)
    (is (= "initial" (:active (c/get-run store "run"))))
    (a/promote! store "run" root a evidence)
    (is (= (:hash a) (:active (c/recover! store "run"))))
    (is (thrown? Exception (a/promote! store "run" root a evidence)))))

(deftest isolation-fails-closed
  (with-redefs [isolation/doctor (fn [] {:ready false :reason "test fixture: unavailable"})]
    (is (thrown-with-msg? Exception #"disabled" (isolation/open-session!)))))

(deftest store-cache-sees-other-writers-and-refuses-unreadable-values
  (let [[_ store] (fixture)
        outside! (fn [request] (let [p (.start (ProcessBuilder. ^java.util.List ["python3" "scripts/store.py" store]))]
                                 (with-open [w (clojure.java.io/writer (.getOutputStream p))] (.write w (u/json-str request)))
                                 (.waitFor p) (u/json-read (slurp (.getInputStream p)))))]
    (c/update-run! store "run" #(assoc % :marker 1))
    (is (= 1 (:marker (c/get-run store "run"))))
    ;; Another process writes; the cached revision no longer matches.
    (let [{:keys [revision value]} (outside! {:op :read :key "run"})]
      (is (:success (outside! {:op :cas :key "run" :revision revision
                               :value (pr-str (assoc (u/read-edn value) :marker 2))}))))
    (is (= 2 (:marker (c/get-run store "run"))))
    (is (= 3 (:marker (c/update-run! store "run" #(update % :marker inc)))))
    (is (thrown-with-msg? Exception #"dispatch denied"
                          (c/update-run! store "run" #(assoc % :bad (java.util.UUID/randomUUID)))))
    (is (= 3 (:marker (c/get-run store "run"))))
    ;; A file replaced at the same path is a new store, not the unlinked one.
    (doseq [f (.listFiles (.getParentFile (clojure.java.io/file store)))] (.delete ^java.io.File f))
    (is (nil? (c/get-run store "run")))
    (c/create-run! store "run" config "initial")
    (is (= "initial" (:active (c/get-run store "run"))))))

(defrecord FakeBackend [log]
  execution/ExecutionBackend
  (open! [_ _] (swap! log conj :open) (Thread/sleep 300) (let [w (str (gensym "worker-"))] (swap! log conj [:ready w]) w))
  (evaluate! [_ w source _] (swap! log conj [:eval w])
    (if (str/includes? source "crash") (throw (ex-info "Worker terminated without result" {})) 1))
  (close! [_ w] (swap! log conj [:close w])))

(deftest prewarm-overlaps-the-first-model-call-and-replaces-a-retired-worker
  (let [[_ store] (fixture) log (atom [])
        script (atom ["(+ 1 2)" "(crash)" "(+ 1 2)" nil])
        p (reify provider/Provider
            (invoke! [_ store run session _]
              (let [id (str (java.util.UUID/randomUUID)) source (first @script)]
                (c/reserve! store run id session 100 0.01)
                (swap! script rest)
                (Thread/sleep 400)
                (swap! log conj :model-reply)
                (let [text (if source (pr-str {:op :repl/eval :source source :bindings {}}) "{:op :done :summary \"ok\"}")
                      reply {:text text :content [{:type "text" :text text}] :stop-reason "end_turn"
                             :tokens 20 :usd 0.002 :model "fixture" :request-id id :provider-id id
                             :provenance :synthetic-fixture}]
                  (c/reconcile! store run id reply)
                  reply))))]
    (c/update-run! store "run" #(-> % (assoc-in [:config :response-envelope] :single-edn-map-v1)
                                    (assoc-in [:config :limits :usd] 1)))
    (with-redefs [execution/for-run (fn [_] (->FakeBackend log))
                  isolation/close-session! (fn [w] (swap! log conj [:close w]))]
      (is (= {:summary "ok"} (runtime/run-session! {:store store :run "run" :workers (atom {}) :prewarmed (atom {})
                                                    :provider p} "root" {:task "fixture"}))))
    (let [entries @log opens (filter #{:open} entries) ready (keep #(when (and (vector? %) (= :ready (first %))) (second %)) entries)]
      ;; The first worker started before the first model reply, not after it.
      (is (< (.indexOf ^java.util.List entries :open) (.indexOf ^java.util.List entries :model-reply)))
      ;; One prewarmed worker, then one replacement for the retired one; no other opens.
      (is (= 2 (count opens) (count ready)))
      (is (= (set ready) (set (keep #(when (and (vector? %) (= :close (first %))) (second %)) entries)))))))
