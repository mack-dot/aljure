(ns repl-lab.model-protocol
  "Shared JSON command envelope; legacy EDN runs retain their original contract."
  (:require [clojure.walk :as walk] [clojure.edn :as edn] [clojure.string :as str] [repl-lab.util :as u]))

(def envelope-version :single-edn-map-v1)
(declare parse-command)
(defn strict-envelope? [config] (= envelope-version (:response-envelope config)))
(defn reject! [reason recoverable]
  (u/fail "Command response rejected" {:command-envelope-error true :reason reason :recoverable recoverable}))

(defn check-envelope-syntax! [text]
  ;; Data only. No extraction, code-fence removal or comments. The existing
  ;; bounded reader permits safe EDN sets/namespaced maps, not eval or tags.
  ;; Strings remain opaque: source text is checked by SCI only after dispatch.
  (when-not (and (string? text) (<= (count (.getBytes text "UTF-8")) 32768))
    (reject! :size false))
  (try (u/bounded-reader-input! text)
       (catch Exception _ (reject! :reader-safety false)))
  (loop [chars (seq text) quoted false escaped false]
    (when-let [ch (first chars)]
      (cond
        quoted (recur (next chars) (or escaped (not= ch \")) (and (not escaped) (= ch \\)))
        (= ch \;) (reject! :comments true)
        :else (recur (next chars) (= ch \") false))))
  (when-not (str/starts-with? (str/trim text) "{") (reject! :map-envelope true)))

(defn strict-command [text schemas]
  (check-envelope-syntax! text)
  (with-open [r (java.io.PushbackReader. (java.io.StringReader. text))]
    (let [command (try
                    (edn/read {:eof ::eof :readers {} :default (fn [& _] (reject! :reader-syntax false))} r)
                    (catch Exception e
                      ;; Duplicate fields can name conflicting commands. Never choose one.
                      (reject! (if (str/includes? (or (.getMessage e) "") "Duplicate key") :duplicate-key :malformed-edn)
                               (not (str/includes? (or (.getMessage e) "") "Duplicate key")))))
          tail (str/trim (slurp r))]
      (when (seq tail)
        (reject! (if (str/starts-with? tail "{") :multiple-commands :trailing-content)
                 (not (str/starts-with? tail "{"))))
      (when-not (and (map? command) (keyword? (:op command))
                     (= (get schemas (:op command)) (set (keys command)))
                     (or (not (contains? command :source)) (string? (:source command)))
                     (or (not (contains? command :bindings)) (map? (:bindings command)))
                     (or (not= :done (:op command)) (string? (:summary command))))
        (reject! :command-schema false))
      command)))

(defn parse-response [config response schemas]
  (if-not (strict-envelope? config)
    ;; Preserve existing JSON and legacy EDN experiment contracts.
    (parse-command config (:text response))
    (let [blocks (:content response) texts (filter #(= "text" (:type %)) blocks)]
      (when-not (= "end_turn" (:stop-reason response)) (reject! :incomplete-turn false))
      (when-not (and (vector? blocks) (= 1 (count texts))
                     (every? #(#{"text" "thinking" "redacted_thinking"} (:type %)) blocks))
        (reject! :content-blocks false))
      (when-not (= (:text response) (:text (first texts))) (reject! :content-text-mismatch false))
      (strict-command (:text (first texts)) schemas))))

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
