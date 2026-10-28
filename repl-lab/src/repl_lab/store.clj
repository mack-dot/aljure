(ns repl-lab.store (:require [repl-lab.util :as u] [clojure.java.io :as io])
  (:import [java.util.concurrent LinkedBlockingQueue TimeUnit]))

;; One long-lived store process per database. Starting python3 for every read
;; and every write cost about 50 ms each, and one controller step makes a dozen.
(defonce ^:private servers (atom {}))
;; The last value read or written per key, with its revision. A read asks only
;; for the current revision, and parses the record again only after another
;; writer changed it. Every write is still a compare-and-set in SQLite.
(defonce ^:private cache (atom {}))

(def ^:private server-limit 8)

(defn- daemon!
  "Readers run on daemon threads: an agent-pool thread blocked on a store
  process would keep the JVM alive, and the process exits only at JVM exit."
  [f]
  (doto (Thread. ^Runnable f) (.setDaemon true) (.start)))

(defn- close! [db s]
  ;; Waits for the request in flight; EOF ends the store process.
  (locking s
    (swap! servers #(if (identical? s (get % db)) (dissoc % db) %))
    (swap! cache #(into {} (remove (fn [[[store _] _]] (= store db))) %))
    (try (.close ^java.io.Writer (:writer s)) (catch java.io.IOException _ nil))))

(defn- server! [db]
  (or (get @servers db)
      (let [s (locking servers
                (or (get @servers db)
                    (let [p (.start (ProcessBuilder. ^java.util.List ["python3" "scripts/store.py" db "--serve"]))
                          reader (io/reader (.getInputStream p) :encoding "UTF-8")
                          lines (LinkedBlockingQueue.) errors (java.io.ByteArrayOutputStream.)
                          s {:process p :writer (io/writer (.getOutputStream p) :encoding "UTF-8")
                             :lines lines :errors errors :used (atom (System/nanoTime))}]
                      (daemon! #(loop [] (if-let [line (try (.readLine ^java.io.BufferedReader reader)
                                                            (catch java.io.IOException _ nil))]
                                           (do (.put lines line) (recur))
                                           (.put lines ::eof))))
                      (daemon! #(try (io/copy (.getErrorStream p) errors) (catch java.io.IOException _ nil)))
                      (swap! servers assoc db s) s)))]
        ;; A test run touches many stores; keep only the most recently used.
        (doseq [[old victim] (->> @servers (sort-by (comp deref :used val)) (drop-last server-limit))]
          (close! old victim))
        s)))

(defn- stop! [db s message]
  (swap! servers #(if (identical? s (get % db)) (dissoc % db) %))
  (.destroyForcibly ^Process (:process s))
  (u/fail message {:error (let [e (str (:errors s))] (subs e 0 (min 2000 (count e))))}))

(defn request! [db request]
  (let [db (str db)]
    (loop []
      (let [{:keys [writer ^LinkedBlockingQueue lines used] :as s} (server! db)
            r (locking s
                ;; A server closed while this thread waited is replaced.
                (when (identical? s (get @servers db))
                  (reset! used (System/nanoTime))
                  (try (.write ^java.io.Writer writer (str (u/json-str request) "\n")) (.flush ^java.io.Writer writer)
                       (catch java.io.IOException _ (stop! db s "Storage failure")))
                  (let [line (.poll lines 15 TimeUnit/SECONDS)]
                    (cond (nil? line) (stop! db s "Storage timeout")
                          (not (string? line)) (stop! db s "Storage failure"))
                    (u/json-read line))))]
        (if (nil? r)
          (recur)
          (do (u/ensure! (not (:error r)) "Storage failure" {:error (:error r)}) r))))))

(defn read-record [db key]
  (let [k [(str db) key] cached (get @cache k)]
    (if (and cached (= (:revision cached) (:revision (request! db {:op :revision :key key}))))
      cached
      (let [r (update (request! db {:op :read :key key}) :value #(when % (u/read-edn %)))]
        (swap! cache assoc k r) r))))
(defn read-value [db key] (:value (read-record db key)))
(defn transact! [db key f]
  (let [k [(str db) key]]
    (loop [attempt 0 {:keys [revision value]} (or (get @cache k) (read-record db key))]
      (u/ensure! (< attempt 20) "Concurrent storage contention" {:key key})
      (let [next (f value) text (pr-str (u/canonical next))
            ;; Refuse what read-record could not read back, at write time.
            _ (u/bounded-reader-input! text)
            r (request! db {:op :cas :key key :revision revision :value text})]
        (if (:success r)
          (do (swap! cache assoc k {:revision (:revision r) :value next}) next)
          (recur (inc attempt) (read-record db key)))))))
