(ns repl-lab.util
  (:require [clojure.edn :as edn] [clojure.data.json :as json]
            [clojure.java.io :as io] [clojure.walk :as walk])
  (:import [java.security MessageDigest] [java.nio.file Files StandardCopyOption]
           [java.nio.charset StandardCharsets]))

(defn fail [message data] (throw (ex-info message data)))
(defn ensure! [pred message data] (when-not pred (fail message data)))
(defn canonical [x]
  (cond (map? x) (into (sorted-map-by #(compare (pr-str %1) (pr-str %2)))
                       (map (fn [[k v]] [k (canonical v)]) x))
        (set? x) (into (sorted-set-by #(compare (pr-str %1) (pr-str %2))) (map canonical x))
        (vector? x) (mapv canonical x)
        (seq? x) (apply list (map canonical x))
        :else x))
(defn sha [s]
  (let [bytes (.digest (MessageDigest/getInstance "SHA-256")
                       (.getBytes (str s) StandardCharsets/UTF_8))]
    (apply str (map #(format "%02x" (bit-and 255 %)) bytes))))
(defn hash-value [x] (sha (pr-str (canonical x))))
(defn bounded-reader-input! [^String s]
  ;; Bound parser recursion before invoking the recursive EDN reader. Restrict
  ;; reader dispatch to sets; tagged values and discard macros are unnecessary.
  (loop [i 0 depth 0 quoted false escaped false comment false]
    (when (< i (count s))
      (let [ch (.charAt s i)]
        (cond
          comment (recur (inc i) depth quoted false (not= ch \newline))
          quoted (recur (inc i) depth (or escaped (not= ch \")) (and (not escaped) (= ch \\)) false)
          (= ch \;) (recur (inc i) depth false false true)
          (= ch (char 34)) (recur (inc i) depth true false false)
          (= ch \#) (do (ensure! (or (and (< (inc i) (count s)) (= \{ (.charAt s (inc i))))
                                      (re-find #"^#:[a-zA-Z][a-zA-Z0-9_.-]*\{" (subs s i))) "Reader dispatch denied" {})
                         (recur (inc i) depth false false false))
          (#{\( \[ \{} ch) (do (ensure! (< depth 96) "Reader nesting limit" {}) (recur (inc i) (inc depth) false false false))
          (#{\) \] \}} ch) (recur (inc i) (dec depth) false false false)
          :else (recur (inc i) depth false false false))))))
(defn read-edn [s]
  (bounded-reader-input! s)
  (with-open [r (java.io.PushbackReader. (java.io.StringReader. s))]
    (let [opts {:eof ::eof :readers {} :default (fn [tag _] (fail "Tagged data denied" {:tag tag}))}
          v (edn/read opts r)]
      (ensure! (not= v ::eof) "Empty EDN" {})
      (ensure! (= ::eof (edn/read opts r)) "Trailing EDN" {}) v)))
(defn read-file [f] (read-edn (slurp f)))
(defn atomic-write! [path s]
  (let [f (io/file path) _ (io/make-parents f)
        tmp (Files/createTempFile (.toPath (.getParentFile (.getAbsoluteFile f)))
                                  ".write-" ".tmp" (make-array java.nio.file.attribute.FileAttribute 0))]
    (with-open [out (java.io.FileOutputStream. (.toFile tmp))]
      (.write out (.getBytes s StandardCharsets/UTF_8)) (.sync (.getFD out)))
    (Files/move tmp (.toPath f) (into-array StandardCopyOption
                                          [StandardCopyOption/ATOMIC_MOVE StandardCopyOption/REPLACE_EXISTING]))))
(defn write-edn! [path x] (atomic-write! path (str (pr-str (canonical x)) "\n")))
(defn jsonable [x]
  (walk/postwalk #(cond (set? %) (vec (sort-by pr-str %))
                        (symbol? %) (str %) :else %) x))
(defn json-str [x] (json/write-str (jsonable x)))
(defn write-json! [path x] (atomic-write! path (str (json-str x) "\n")))
(defn json-read [s] (json/read-str s :key-fn keyword))
(defn now [] (str (java.time.Instant/now)))
