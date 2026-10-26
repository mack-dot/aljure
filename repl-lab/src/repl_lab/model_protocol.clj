(ns repl-lab.model-protocol
  "Shared JSON command envelope; legacy EDN runs retain their original contract."
  (:require [clojure.walk :as walk] [repl-lab.util :as u]))

(defn json? [config] (= :json (:command-format config)))
(defn json-text [value]
  ;; Preserve namespaced operation names; data.json's keyword conversion uses name.
  (u/json-str (walk/postwalk #(if (keyword? %) (subs (str %) 1) %) value)))
(defn write-value [config value] (if (json? config) (json-text value) (pr-str value)))
(defn query [q]
  (cond-> q (vector? (:select q)) (update :select #(mapv (fn [x] (if (string? x) (keyword x) x)) %))))
(defn parse-command [config text]
  (u/ensure! (and (string? text) (<= (count (.getBytes text "UTF-8")) 32768)) "Command size limit" {})
  (if-not (json? config) (u/read-edn text)
    (let [_ (u/bounded-reader-input! text)
          raw (u/json-read text)
          _ (u/ensure! (and (map? raw) (string? (:op raw))) "Expected JSON command object" {})
          command (update raw :op keyword)
          command (cond-> command
                    (string? (:category command)) (update :category keyword)
                    (= :context/query (:op command)) (update :query query))]
      (cond
        (and (= :artifact/submit (:op command)) (= :workflow (:category command)))
        (update command :source #(pr-str (update-in (u/json-read %) [:strategy :context] query)))

        (and (#{:artifact/patch :artifact/subtree} (:op command)) (= :clojure (get config :execution-language :clojure)))
        (cond-> (update command :path u/read-edn)
          (= :artifact/patch (:op command)) (update :replacement u/read-edn))

        (#{:artifact/patch :artifact/subtree} (:op command))
        (update command :path #(mapv (fn [x] (if (string? x) (keyword x) x)) %))

        :else command))))

(defn write-command [config command]
  (if-not (json? config) (pr-str command)
    (json-text
      (cond
        (and (= :artifact/submit (:op command)) (= :workflow (:category command)))
        (update command :source #(json-text (u/read-edn %)))
        (and (#{:artifact/patch :artifact/subtree} (:op command)) (= :clojure (get config :execution-language :clojure)))
        (cond-> (update command :path pr-str)
          (= :artifact/patch (:op command)) (update :replacement pr-str))
        :else command))))

(defn inspect-artifact [config artifact]
  (if (and (json? config) (= :clojure (get artifact :language :clojure)))
    ;; JSON has no symbols or list/vector distinction. Return a lossless form.
    (-> artifact (dissoc :forms) (assoc :forms-edn (pr-str (:forms artifact))))
    artifact))

(defn instructions [config]
  (if-not (json? config) (slurp "resources/base-instructions.txt")
    (str (slurp "resources/model-common.txt") "\n"
         (slurp (str "resources/model-" (name (get config :execution-language :clojure)) ".txt")))))
