(ns repl-lab.bridge-proof
  "Runs the programmatic tool bridge against the real isolated SCI worker and writes
  var/bridge-proof.json. Every probe goes through isolation/run-program!, the path the controller
  uses. No model, no network, no credentials. The proof binds the worker image, the bridge source
  and the supervisor, so a changed bridge or image needs a fresh proof."
  (:require [clojure.string :as str] [repl-lab.util :as u] [repl-lab.isolation :as isolation]))

(def proof-path "var/bridge-proof.json")

(def grant {:allow #{"echo"} :max-ops 3})

(defn- echo [{:keys [input]}] {:tool-result input})

(defn- attempt [session source tools handler]
  (try {:value (isolation/run-program! session source {} tools handler)}
       (catch Exception e {:error (.getMessage e)})))

(def probes
  ;; :expect is a predicate on the attempt's map.
  [{:name "granted tool returns the controller's data"
    :source "(tool \"echo\" {:x 1 :items [1 2 3]})" :tools grant :handler echo
    :expect (fn [r] (= {:x 1 :items [1 2 3]} (:value r)))}
   {:name "the sequence number counts every attempt on the wire"
    :source "(do (tool \"echo\" 1) (tool \"echo\" 2))" :tools grant
    :handler (let [seen (atom [])] (fn [{:keys [seq input]}] (swap! seen conj [seq input]) {:tool-result @seen}))
    :expect (fn [r] (= [[1 1] [2 2]] (:value r)))}
   {:name "no grant: the tool refuses before the wire"
    :source "(try (tool \"echo\" {}) (catch Exception e (ex-message e)))" :tools nil :handler echo
    :expect (fn [r] (= "No tool capabilities in this evaluation" (:value r)))}
   {:name "a tool outside the allow set is refused"
    :source "(try (tool \"other\" {}) (catch Exception e (ex-message e)))" :tools grant :handler echo
    :expect (fn [r] (= "Tool is not authorized: other" (:value r)))}
   {:name "the per-evaluation operation limit holds"
    :source "(try (dotimes [_ 4] (tool \"echo\" {})) \"over\" (catch Exception e (ex-message e)))" :tools grant :handler echo
    :expect (fn [r] (= "Program operation limit reached: 3" (:value r)))}
   {:name "a controller refusal reaches model code as a catchable error"
    :source "(try (tool \"echo\" {}) (catch Exception e [(ex-message e) (:tool (ex-data e))]))" :tools grant
    :handler (fn [_] {:tool-error "Denied: not preapproved"})
    :expect (fn [r] (= ["Denied: not preapproved" "echo"] (:value r)))}
   {:name "a handler failure becomes a tool error, the worker is not left waiting"
    :source "(try (tool \"echo\" {}) (catch Exception e (ex-message e)))" :tools grant
    :handler (fn [_] (throw (ex-info "handler crashed" {})))
    :expect (fn [r] (= "handler crashed" (:value r)))}
   {:name "a malformed handler reply becomes a tool error"
    :source "(try (tool \"echo\" {}) (catch Exception e (ex-message e)))" :tools grant
    :handler (fn [_] {:unexpected 1})
    :expect (fn [r] (= "Bridge returned a malformed reply" (:value r)))}
   {:name "a grant without a handler answers every request with an error"
    :source "(try (tool \"echo\" {}) (catch Exception e (ex-message e)))" :tools grant :handler nil
    :expect (fn [r] (= "No tool bridge in this session" (:value r)))}
   {:name "an oversized tool result is refused at the worker's line bound"
    :source "(try (count (tool \"echo\" {})) (catch Exception e (ex-message e)))" :tools grant
    :handler (fn [_] {:tool-result (apply str (repeat 70000 "x"))})
    :expect (fn [r] (str/starts-with? (str (:value r)) "Tool result too large for the worker"))}
   {:name "an oversized tool input is refused before the wire"
    :source "(try (tool \"echo\" (apply str (repeat 61000 \"y\"))) (catch Exception e (ex-message e)))" :tools grant :handler echo
    :expect (fn [r] (= "Tool input too large" (:value r)))}
   {:name "a tool wait longer than the per-expression deadline is idle time, not compute"
    :source "(tool \"echo\" :slow)" :tools grant
    :handler (fn [_] (Thread/sleep 12000) {:tool-result :answered})
    :expect (fn [r] (= :answered (:value r)))}
   {:name "the grant is cleared after the evaluation"
    :source "(try (tool \"echo\" {}) (catch Exception e (ex-message e)))" :tools nil :handler echo
    :expect (fn [r] (= "No tool capabilities in this evaluation" (:value r)))}
   {:name "program code still has no filesystem"
    :source "(try (slurp \"/etc/hostname\") (catch Exception e :refused))" :tools grant :handler echo
    :expect (fn [r] (or (= :refused (:value r)) (str/includes? (str (:error r)) "slurp")))}
   {:name "the tool name must be a string"
    :source "(try (tool :echo {}) (catch Exception e (ex-message e)))" :tools grant :handler echo
    :expect (fn [r] (= "Tool is not authorized: :echo" (:value r)))}])

(def deadline-probe
  ;; The supervisor ends the worker on a wall-time breach, so this probe gets its own session.
  {:name "compute after a tool call still meets the per-expression deadline (worker ended)"
   :source "(do (tool \"echo\" 1) (loop [] (recur)))" :tools grant :handler echo
   :expect (fn [r] (str/includes? (str (:error r)) "Worker terminated"))})

(defn- run-one [session {:keys [name source tools handler expect]}]
  (let [r (if (nil? tools)
            (try {:value (isolation/evaluate! session source {})} (catch Exception e {:error (.getMessage e)}))
            (attempt session source tools handler))
        shown (pr-str (or (:value r) (:error r)))]
    {:probe name :passed (boolean (expect r)) :shown (subs shown 0 (min 200 (count shown)))}))

(defn- in-session [f]
  (let [session (isolation/open-session! (+ (System/currentTimeMillis) 170000))]
    (try (f session) (finally (isolation/close-session! session)))))

(defn run-probes []
  (conj (in-session (fn [session] (mapv #(run-one session %) probes)))
        (in-session (fn [session] (run-one session deadline-probe)))))

(defn -main [& _]
  (let [check (isolation/doctor)
        results (run-probes)
        passed (every? :passed results)
        proof {:status (if passed "TESTED" "FAILED") :image (:image check)
               :bridge-sha256 (u/sha (slurp "worker/src/repl_lab/bridge.clj"))
               :isolation-sha256 (u/sha (slurp "src/repl_lab/isolation.clj"))
               :supervisor-sha256 (u/sha (slurp "scripts/isolation.py"))
               :probes (count results) :results results :model-calls 0}]
    (u/write-json! proof-path proof)
    (println (u/json-str (dissoc proof :results)))
    (doseq [{:keys [probe passed shown]} results :when (not passed)] (println "FAILED:" probe "->" shown))
    (shutdown-agents)
    (System/exit (if passed 0 1))))
