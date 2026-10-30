(ns repl-lab.bridge
  "The worker's half of the programmatic tool bridge. Pure Clojure (no SCI), so the controller's
  tests load it too. The controller may grant one evaluation a set of tool names and an operation
  budget; inside that evaluation, model code calls (tool \"name\" input). The worker writes one
  request line to its only channel, the controller's pipe, and blocks on the reply line. It gains
  no capability of its own: it still cannot read, write, connect or spawn; it can only ask, by a
  name on this evaluation's allow list, at most max-ops times. An evaluation without a grant
  (every request from an existing plan) makes tool throw before anything is written."
  (:require [clojure.edn :as edn]))

(defn safe-read [s]
  (with-open [r (java.io.PushbackReader. (java.io.StringReader. s))]
    (let [opts {:eof ::eof :readers {} :default (fn [_ _] (throw (ex-info "Tagged literals denied" {})))}
          value (edn/read opts r)]
      (when-not (= ::eof (edn/read opts r)) (throw (ex-info "One form per request" {}))) value)))

(def grant (atom nil))
(def request-chars 60000)

(defn grant-of
  "The grant for one evaluation, or nil. {:allow #{names} :max-ops n}; anything else is refused."
  [tools]
  (when (some? tools)
    (when-not (and (map? tools) (= #{:allow :max-ops} (set (keys tools)))
                   (set? (:allow tools)) (every? string? (:allow tools)) (pos-int? (:max-ops tools)))
      (throw (ex-info "Invalid tool grant" {})))
    {:allow (:allow tools) :max-ops (:max-ops tools) :ops 0}))

(defn tool
  "One operation through the controller. Returns the controller's result as data, or throws
  ex-info with the controller's reason (a denied, over-budget or failed operation), which model
  code may catch. The sequence number counts every attempt that reached the wire."
  [name input]
  (let [{:keys [allow max-ops ops] :as g} @grant]
    (when-not g (throw (ex-info "No tool capabilities in this evaluation" {})))
    (when-not (and (string? name) (contains? allow name)) (throw (ex-info (str "Tool is not authorized: " name) {})))
    (when (>= ops max-ops) (throw (ex-info (str "Program operation limit reached: " max-ops) {})))
    (let [seq (inc ops)
          printed (try (pr-str {:tool-request {:seq seq :name name :input input}})
                       (catch Exception _ (throw (ex-info "Tool input is not EDN data" {}))))]
      (when (> (count printed) request-chars) (throw (ex-info "Tool input too large" {})))
      (try (safe-read printed) (catch Exception _ (throw (ex-info "Tool input is not EDN data" {}))))
      (swap! grant assoc :ops seq)
      (println printed) (flush)
      (let [line (read-line)
            reply (try (when line (safe-read line)) (catch Exception _ nil))]
        (cond (nil? line) (throw (ex-info "Tool channel closed" {}))
              (and (map? reply) (= #{:tool-result} (set (keys reply)))) (:tool-result reply)
              (and (map? reply) (= #{:tool-error} (set (keys reply))) (string? (:tool-error reply)))
              (throw (ex-info (:tool-error reply) {:tool name :seq seq}))
              :else (throw (ex-info "Malformed tool reply" {})))))))

(defmacro with-grant
  "Evaluates body with the grant in force, and clears it afterwards whatever happens."
  [tools & body]
  `(do (reset! grant (grant-of ~tools))
       (try ~@body (finally (reset! grant nil)))))
