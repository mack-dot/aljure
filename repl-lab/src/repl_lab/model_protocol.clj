(ns repl-lab.model-protocol
  "Shared JSON command envelope; legacy EDN runs retain their original contract."
  (:require [clojure.walk :as walk] [clojure.edn :as edn] [clojure.string :as str] [repl-lab.util :as u]))

(def envelope-version :single-edn-map-v1)
;; The same strict map, optionally followed by one verbatim source block, so
;; executable code needs no EDN string escaping. Nothing is extracted or repaired.
(def block-envelope-version :edn-map-source-block-v1)
(declare parse-command strict-map query)
;; Each command is a provider-native tool call whose JSON input maps onto exactly
;; one command schema. Text blocks are never parsed or executed.
(def tool-envelope-version :native-tool-v1)
(defn strict-envelope? [config] (contains? #{envelope-version block-envelope-version} (:response-envelope config)))
(defn block-envelope? [config] (= block-envelope-version (:response-envelope config)))
(defn tool-envelope? [config] (= tool-envelope-version (:response-envelope config)))
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

(defn- line-matches [re s]
  (let [m (re-matcher re s)]
    (loop [found []] (if (.find m) (recur (conj found [(.start m) (.end m)])) found))))

(defn split-source-block
  "Returns [map-text source-or-nil]. A block is valid only as the last part of
  the response: a line exactly <<<SOURCE, verbatim source, a line exactly
  SOURCE>>>, then only whitespace. Any other arrangement is a recoverable
  format error; nothing is extracted from it."
  [text]
  (let [begins (line-matches #"(?m)^<<<SOURCE[ \t]*\r?$" text)]
    (if (empty? begins)
      [text nil]
      (let [_ (when (> (count begins) 1) (reject! :source-block true))
            [b0 b1] (first begins)
            after (subs text b1)
            ends (line-matches #"(?m)^SOURCE>>>[ \t]*\r?$" after)
            _ (when-not (= 1 (count ends)) (reject! :source-block true))
            [e0 e1] (first ends)
            _ (when-not (str/blank? (subs after e1)) (reject! :source-block true))
            source (-> (subs after 0 e0) (str/replace-first #"\A\r?\n" "") (str/replace #"\r?\n\z" ""))]
        (when (str/blank? source) (reject! :source-block true))
        [(subs text 0 b0) source]))))

(defn strict-command
  ([text schemas] (strict-command text schemas false))
  ([text schemas allow-block]
   (when-not (and (string? text) (<= (count (.getBytes text "UTF-8")) 32768))
     (reject! :size false))
   (let [[map-text block] (if allow-block (split-source-block text) [text nil])
         command (strict-map map-text schemas allow-block)]
     (cond
       block (if (= :block (:source command)) (assoc command :source block) (reject! :source-block true))
       (and allow-block (= :block (:source command))) (reject! :source-block true)
       :else command))))

(defn- schema-valid? [command schemas allow-block]
  (and (map? command) (keyword? (:op command))
       (= (get schemas (:op command)) (set (keys command)))
       (or (not (contains? command :source)) (string? (:source command))
           (and allow-block (= :block (:source command))))
       (or (not (contains? command :bindings)) (map? (:bindings command)))
       (or (not= :done (:op command)) (string? (:summary command)))))

(defn- strict-map [text schemas allow-block]
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
      (when-not (schema-valid? command schemas allow-block)
        (reject! :command-schema false))
      command)))

(defn- object-schema [properties required]
  {:type "object" :properties properties :required required :additionalProperties false})

;; Tool inputs have fixed fields only. Fields the tools leave out take the stated
;; defaults: repl_eval has no :bindings and agent_call :context defaults to [].
(def command-tools
  [{:op :context/metadata :name "context_metadata"
    :description "Return the record count of a context handle, without its records."
    :input_schema (object-schema {:handle {:type "string"}} ["handle"])}
   {:op :context/query :name "context_query"
    :description (str "Return records {line, text} from a context handle: at most limit records (1-64, default 20) "
                      "starting at offset (default 0). select keeps only the named fields.")
    :input_schema (object-schema {:handle {:type "string"} :offset {:type "integer" :minimum 0}
                                  :limit {:type "integer" :minimum 1 :maximum 64}
                                  :select {:type "array" :items {:type "string" :enum ["line" "text"]}}}
                                 ["handle"])}
   {:op :repl/eval :name "repl_eval"
    :description (str "Evaluate Clojure source in this session's SCI worker and return its value: a string as "
                      "plain text, any other value as EDN. Definitions persist across calls in the same session. "
                      "The source must be exactly one form; wrap several in (do ...). End definitions with nil, "
                      "because a var is not a result: (do (def rows ...) nil). The source is read as EDN data, so "
                      "reader macros are unavailable: write (re-pattern \"...\") not #\"...\", (fn [x] ...) not "
                      "#(...), (quote x) not 'x, (deref x) not @x. Most Java interop is unavailable: "
                      "Long/parseLong and parse-long fail, so parse an integer with (Integer/parseInt s). "
                      "read-string, eval, slurp and printing (println, pr-str) are denied; build strings with "
                      "str. A result over 64 KB stops the worker "
                      "and loses its definitions, so return counts, slices or summaries, not large values.")
    :input_schema (object-schema {:source {:type "string"}} ["source"])}
   {:op :agent/call :name "agent_call"
    :description (str "Run a child session, or resume a completed one by its id, on a subtask with selected "
                      "evidence. The child has its own SCI worker and the same context. Returns its done summary.")
    :input_schema (object-schema {:id {:type "string"} :task {:type "string"}
                                  :context {:type "array" :items {:type "string"}}} ["id" "task"])}
   {:op :done :name "done"
    :description (str "Finish this session with exactly one of: summary, the result as text; or source, Clojure "
                      "evaluated in this session's SCI worker (same rules as repl_eval) whose string value is the "
                      "result. For the root session the result is the exact final answer. For a long answer, build "
                      "it in SCI and pass source instead of typing it.")
    :input_schema (object-schema {:summary {:type "string"} :source {:type "string"}} [])}])

(defn tool-definitions [] (mapv #(dissoc % :op) command-tools))

(defn- tool-command [{:keys [name input]}]
  (let [{:keys [op input_schema]} (first (filter #(= name (:name %)) command-tools))]
    (when-not op (reject! :tool-name true))
    (when-not (and (map? input) (every? (set (keys (:properties input_schema))) (keys input))
                   (every? #(contains? input (keyword %)) (:required input_schema)))
      (reject! :tool-input true))
    (case op
      :context/query {:op op :handle (:handle input) :query (query (dissoc input :handle))}
      :repl/eval (assoc input :op op :bindings {})
      :agent/call (merge {:context []} (assoc input :op op))
      :done (if (and (contains? input :source) (not (contains? input :summary)))
              {:op :done/eval :source (:source input)}
              (assoc input :op op))
      (assoc input :op op))))

(defn- tool-response-command [response schemas]
  (let [blocks (:content response) calls (filter #(= "tool_use" (:type %)) blocks)]
    (when-not (and (vector? blocks) (every? #(#{"text" "thinking" "redacted_thinking" "tool_use"} (:type %)) blocks))
      (reject! :content-blocks false))
    (cond
      (and (= "tool_use" (:stop-reason response)) (= 1 (count calls))) nil
      (and (= "end_turn" (:stop-reason response)) (empty? calls)) (reject! :no-tool-call true)
      (> (count calls) 1) (reject! :multiple-commands false)
      :else (reject! :incomplete-turn false))
    (let [command (tool-command (first calls))]
      (when-not (schema-valid? command schemas false) (reject! :tool-input true))
      command)))

(defn parse-response [config response schemas]
  (cond
    (tool-envelope? config) (tool-response-command response schemas)
    ;; Preserve existing JSON and legacy EDN experiment contracts.
    (not (strict-envelope? config)) (parse-command config (:text response))
    :else
    (let [blocks (:content response) texts (filter #(= "text" (:type %)) blocks)]
      (when-not (= "end_turn" (:stop-reason response)) (reject! :incomplete-turn false))
      (when-not (and (vector? blocks) (= 1 (count texts))
                     (every? #(#{"text" "thinking" "redacted_thinking"} (:type %)) blocks))
        (reject! :content-blocks false))
      (when-not (= (:text response) (:text (first texts))) (reject! :content-text-mismatch false))
      (strict-command (:text (first texts)) schemas (block-envelope? config)))))

(defn correction-instruction [config]
  (cond
    (tool-envelope? config)
    (str "Call exactly one of the provided tools. Text outside a tool call is never executed; to finish, call done. "
         "No rejected call was executed. This is the task's only formatting correction; normal budgets still apply.")
    (block-envelope? config)
    (str "Return a new complete command: one EDN map, optionally followed by one source block "
         "(a line <<<SOURCE, the code verbatim, a line SOURCE>>>) when the map has :source :block. "
         "No markup, comments or other text. No rejected fragment was executed. "
         "This is the task's only formatting correction; normal budgets still apply.")
    :else
    "Return a new complete single EDN command map. No markup, comments or extra text. No rejected fragment was executed. This is the task's only formatting correction; normal budgets still apply."))

(defn json? [config] (= :json (:command-format config)))
(defn json-text [value]
  ;; Preserve namespaced operation names; data.json's keyword conversion uses name.
  (u/json-str (walk/postwalk #(if (keyword? %) (subs (str %) 1) %) value)))
(defn write-value [config value] (if (json? config) (json-text value) (pr-str value)))
(defn- tool-result-text [config result]
  ;; A string value reads as plain text, like native printed output; escaped
  ;; EDN would put every line on one line. Other values and errors stay EDN.
  (if (and (map? result) (= #{:value} (set (keys result))))
    (let [value (:value result)] (if (string? value) value (write-value config value)))
    (write-value config result)))

(defn result-messages
  "History entries for an executed command. Native tool turns keep the provider's
  content blocks unchanged, including thinking, and answer the call by its ID."
  [config response result]
  (if (tool-envelope? config)
    (let [call (first (filter #(= "tool_use" (:type %)) (:content response)))]
      [{:role "assistant" :content (:content response)}
       {:role "user" :content [(cond-> {:type "tool_result" :tool_use_id (:id call) :content (tool-result-text config result)}
                                 (and (map? result) (:error result)) (assoc :is_error true))]}])
    [{:role "assistant" :content (:text response)}
     {:role "user" :content (write-value config result)}]))
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
