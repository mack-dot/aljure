(ns repl-lab.worker
  (:require [clojure.edn :as edn] [sci.core :as sci]))

;; No host namespaces or controller values are passed to SCI.
(def denied '[eval load-file load-string load-reader read read-string require use import
              slurp spit future future-call pmap agent send send-off shutdown-agents
              create-ns in-ns ns remove-ns resolve ns-resolve find-var intern alter-var-root
              var-get var-set with-redefs with-redefs-fn set! defmacro defprotocol deftype
              defrecord gen-class proxy reify locking monitor-enter monitor-exit
              println print prn pr printf pr-str println-str print-str])
(defn safe-read [s]
  (with-open [r (java.io.PushbackReader. (java.io.StringReader. s))]
    (let [opts {:eof ::eof :readers {} :default (fn [_ _] (throw (ex-info "Tagged literals denied" {})))}
          value (edn/read opts r)]
      (when-not (= ::eof (edn/read opts r)) (throw (ex-info "One form per request" {}))) value)))
(defn -main [& _]
  (let [ctx (sci/init {:classes {} :imports {} :deny denied :namespaces {}})]
    (loop []
      (when-let [line (read-line)]
        (let [result
              (try
                (when (> (count line) 65536) (throw (ex-info "Input too large" {})))
                (let [{:keys [source bindings]} (safe-read line)
                      form (safe-read source)]
                  (when-not (map? bindings) (throw (ex-info "Invalid bindings" {})))
                  (doseq [[k v] bindings]
                    (when-not (and (keyword? k) (nil? (namespace k))
                                   (re-matches #"[a-z][a-z0-9-]*" (name k)))
                      (throw (ex-info "Invalid binding name" {})))
                    (sci/intern ctx 'user (symbol (name k)) v))
                  ;; Never emit unreadable JVM/SCI objects into the broker wire.
                  ;; Definitions still take effect; callers should end them in nil.
                  (let [value (sci/eval-string* ctx (pr-str form))]
                    (try (safe-read (pr-str {:value value}))
                         (catch Exception _ {:error "Result is not EDN data. End definitions with nil."}))))
                (catch Exception e (let [message (or (.getMessage e) "Worker evaluation failed")]
                                     {:error (subs message 0 (min 1000 (count message)))})))]
          (prn result) (flush))
        (recur)))))
