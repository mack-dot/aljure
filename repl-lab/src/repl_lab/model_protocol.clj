(ns repl-lab.model-protocol
  "Shared JSON command envelope; legacy EDN runs retain their original contract."
  (:require [clojure.walk :as walk] [clojure.edn :as edn] [clojure.string :as str] [repl-lab.util :as u]
            [repl-lab.programs :as programs] [repl-lab.skill-interface :as skill-interface]))

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
;; Assisted SCI surface: several forms per call, var-safe results, predefined
;; helpers and explained errors. Bounded results add previews and paging.
(defn assisted? [config] (= :assisted (:sci-surface config)))
(defn bounded? [config] (= :bounded (:sci-results config)))
;; The matched Python surface (research/Q_SUBSTRATE_BRIEF.md): the same tools, prompt
;; structure, context binding, previews, paging and answer delivery, with the Python
;; worker showing results itself. Clojure definitions are unchanged by it.
(defn execution-language [config] (get config :execution-language :clojure))
(defn python? [config] (= :python (execution-language config)))
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

(defn skill-tools [config]
  (when (skill-interface/enabled? config)
    [{:op :skill/inspect :name "artifact_inspect"
      :description (str "Read an approved artifact's verified source and invocation contract without executing it. "
                        "Use a hash from approved-functions. "
                        "section is function (default) or applicability. offset defaults to 0; limit defaults to 4096 "
                        "characters. Follow next-offset to read more. An approved artifact refused on this task is "
                        "inspectable but not callable. Past validation and predicate success do not guarantee current applicability.")
      :input_schema (object-schema {:hash {:type "string"} :section {:type "string" :enum ["function" "applicability"]}
                                    :offset {:type "integer" :minimum 0} :limit {:type "integer" :minimum 1 :maximum 4096}}
                                   ["hash"])}
     {:op :artifact/call :name "artifact_call"
      :description (str "Invoke an admitted approved artifact by its hash from artifact_inspect, with an arguments array "
                        "matching its arity and source contract. Runs the verified artifact and its dependencies in a fresh "
                        "isolated worker with the same helpers and external-context binding as repl_eval; returns its result "
                        "with provenance. Arguments are JSON data, never source code. "
                        "For computation over external-context, the same admitted function is also callable by its listed "
                        "name in repl_eval. Inspection and copying source do not count as invocation.")
      :input_schema (object-schema {:hash {:type "string"} :arguments {:type "array" :items {}}} ["hash" "arguments"])}]))

(defn program-tools
  "aljure_contract.programs (research/PROGRAMMATIC_EXECUTION.md): program_run, and the grant's
  tools as direct one-operation tools, from the frozen plan's grant. Without the switch there
  are none, so every other plan's tool definitions are unchanged."
  [config]
  (when-let [spec (get-in config [:contract :programs])]
    (let [grant (programs/grant spec)]
      (cond-> []
        (:program-tool grant)
        (conj {:op :program/run :name "program_run"
               :description (str "Run a Clojure program in this session's SCI worker (same rules and persistence as repl_eval) "
                                 "that performs controller operations without their results entering this conversation: "
                                 "(tool \"name\" input) performs one operation and returns its result as data to the program; "
                                 "only the program's final value returns here. Operations run one at a time. Tools: "
                                 (programs/describe grant)
                                 " An effect needs an :idempotency-key string in its input; a repeated key returns the first "
                                 "result without acting again. A denied, over-budget, failed or uncertain operation throws "
                                 "ex-info whose message gives the reason; wrap calls in try to handle partial failures, and "
                                 "never repeat an operation whose outcome was uncertain. Prefer one program over many single "
                                 "calls; where no computation is needed, call done directly.")
               :input_schema (object-schema {:source {:type "string"}} ["source"])})
        (:direct-tools grant)
        (into (for [[name policy] (:tools grant) :let [t (programs/tools name)]]
                {:op :tool/call :name name
                 :description (str (:describe t) (when (= :effect (:class policy)) "; an effect, needs idempotency-key")
                                   "; at most " (:max-calls policy) " calls per task.")
                 :input_schema (object-schema (:properties t) (mapv clojure.core/name (:required t)))}))))))

(defn sci-contract [] (u/json-read (slurp "resources/sci-contract.json")))
(defn python-contract [] (u/json-read (slurp "resources/python-contract.json")))
(defn sci-rules
  "The advertised rules of the configured surface and language (the Python surface has
  bounded rules only)."
  [config]
  (let [mode (if (bounded? config) "bounded" "raw")
        contract (if (python? config) (python-contract) (sci-contract))]
    (->> (:rules contract) (filter #(some #{mode} (:modes %))) (map :text))))

(defn- python-descriptions [config]
  {"repl_eval" (str "Evaluate Python in this session's isolated interpreter and return its result: what the code "
                    "printed, then the repr of a final expression. Definitions persist across calls in the same "
                    "session. " (str/join " " (sci-rules config)))
   "done" (str "Finish this session with exactly one of: summary, the result as text; or source, Python "
               "statements evaluated in this session's isolated interpreter (same rules as repl_eval) whose "
               "final expression, a string, is the result. For the root session the result is the exact "
               "final answer. For a long answer, build it in the interpreter and pass source instead of typing it.")
   "agent_call" (str "Run a child session, or resume a completed one by its id, on a subtask with selected "
                     "evidence. The child has its own interpreter worker and the same context. Returns its done summary.")})

(defn tool-definitions
  ([] (tool-definitions {}))
  ([config]
   (cond->> (mapv #(dissoc % :op) (concat command-tools (program-tools config) (skill-tools config)))
     (and (assisted? config) (python? config))
     (mapv #(if-let [text (get (python-descriptions config) (:name %))] (assoc % :description text) %))
     (and (assisted? config) (not (python? config)))
     (mapv #(case (:name %)
              "repl_eval" (assoc % :description
                                 (str "Evaluate Clojure in this session's SCI worker and return its value: a string as "
                                      "plain text, any other value as EDN. Definitions persist across calls in the "
                                      "same session. " (str/join " " (sci-rules config))))
              "done" (assoc % :description
                            (str "Finish this session with exactly one of: summary, the result as text; or source, "
                                 "Clojure forms evaluated in this session's SCI worker (same rules as repl_eval) whose "
                                 "last value, a string, is the result. For the root session the result is the exact "
                                 "final answer. For a long answer, build it in SCI and pass source instead of typing it."))
              %)))))

(defn- nesting-bounded!
  "Bounds reader recursion before the recursive Clojure reader runs. Unlike
  u/bounded-reader-input!, reader dispatch such as #\"...\" and #(...) passes."
  [^String s]
  (loop [i 0 depth 0 quoted false escaped false comment false]
    (when (< i (count s))
      (let [ch (.charAt s i)]
        (cond
          comment (recur (inc i) depth false false (not= ch \newline))
          quoted (recur (inc i) depth (or escaped (not= ch \")) (and (not escaped) (= ch \\)) false)
          ;; A character literal such as \( or \" is one token.
          (= ch \\) (recur (+ i 2) depth false false false)
          (= ch \;) (recur (inc i) depth false false true)
          (= ch \") (recur (inc i) depth true false false)
          (#{\( \[ \{} ch) (do (u/ensure! (< depth 96) "Source nesting is too deep" {})
                               (recur (inc i) (inc depth) false false false))
          (#{\) \] \}} ch) (recur (inc i) (dec depth) false false false)
          :else (recur (inc i) depth false false false))))))

(defn- source-data
  "A form read with Clojure syntax, as data the worker's EDN reader accepts: a
  regex literal becomes (re-pattern ...), and any other object is refused."
  [form]
  (walk/postwalk
   (fn [x]
     (cond (instance? java.util.regex.Pattern x) (list 're-pattern (str x))
           (or (nil? x) (boolean? x) (number? x) (string? x) (char? x) (keyword? x) (symbol? x) (coll? x)) x
           :else (u/fail (str "Source contains a " (.getSimpleName (class x))
                              " literal, which is unavailable; build the value with code.") {})))
   form))

(defn read-forms
  "Reads every form of model source with Clojure's reader, so #\"...\", #(...),
  'x, @x and #'v work as the model expects. The reader cannot evaluate (#=),
  construct records or read tagged or conditional forms, and nesting is
  bounded. A failure explains the fix; nothing reaches the worker."
  [source]
  (u/ensure! (and (string? source) (not (str/blank? source))) "Source is empty" {})
  (nesting-bounded! source)
  ;; SCI evaluates in user, so ::k and syntax-quote resolve as they would there.
  (binding [*read-eval* false *data-readers* {} *default-data-reader-fn* nil *ns* (create-ns 'user)]
    (with-open [r (java.io.PushbackReader. (java.io.StringReader. source))]
      (loop [forms []]
        (let [form (try (read {:eof ::eof} r)
                        (catch Exception e
                          (u/fail (str "Source is not readable: " (str/replace (str (.getMessage (or (.getCause e) e))) #"\.+$" "")
                                       ". Check quotes and brackets.") {})))]
          (if (= ::eof form) forms (recur (conj forms (source-data form)))))))))

(defn- python-source!
  "Python source is parsed by the worker's own ast.parse inside the container; the
  controller checks only that there is some."
  [source]
  (u/ensure! (and (string? source) (not (str/blank? source))) "Source is empty" {})
  source)

(defn assisted-source
  "Model source as one worker form: forms run in a do, the value is bound to
  last-result, and aljure-show (resources/sci-prelude.edn) makes it displayable.
  A truncated value is also bound to full-result, which paging never rebinds.
  For Python the worker does the same itself from a display request
  (worker/src/repl_lab/python_worker.py): last_result, full_result, previews."
  [config op source]
  (if (python? config)
    {:source (python-source! source) :display {:limit (if (bounded? config) 60000 1000000000000000) :preview 24000}}
  (let [body (cons 'do (read-forms source))]
    (pr-str (if (= :done/eval op)
              body
              (list 'let ['aljure-v body
                          'aljure-r (list 'if (list 'var? 'aljure-v) (list 'deref 'aljure-v) 'aljure-v)
                          'aljure-s (list 'aljure-show 'aljure-v (if (bounded? config) 60000 1000000000000000) 24000)]
                    (list 'def 'last-result 'aljure-r)
                    (list 'when (list 'and (list 'map? 'aljure-s) (list :aljure/truncated 'aljure-s))
                          (list 'def 'full-result 'aljure-r))
                    'aljure-s))))))

(defn answer-source
  "done with source: evaluate the answer once, keep it in the worker as
  aljure-answer and return only [length hash]. The controller then reads it
  out in pages below the worker's output bound and checks both, so an answer
  of any size up to the cap is delivered exactly without ever exceeding that
  bound. The hash is Clojure's (non-cryptographic) string hash: a transport
  check, not a correctness claim."
  [config source]
  (cond
    ;; The Python worker keeps the answer as aljure_answer and returns [length checksum]
    ;; (code points; the 31-polynomial checksum repl-lab.runtime recomputes over the pages).
    (python? config) {:source (python-source! source) :answer true}
    (assisted? config)
    (pr-str (list 'let ['aljure-v (cons 'do (read-forms source))]
                  (list 'def 'aljure-answer 'aljure-v)
                  (list 'if (list 'string? 'aljure-v) [(list 'count 'aljure-v) (list 'hash 'aljure-v)] :aljure/not-a-string)))
    ;; The raw surface keeps the worker's own reading and error messages.
    :else
    (str "(let [aljure-v " source "] (def aljure-answer aljure-v) "
         "(if (string? aljure-v) [(count aljure-v) (hash aljure-v)] :aljure/not-a-string))")))

(def ^:private error-hints
  [[#"Could not resolve symbol: (slurp|spit|read-string|eval|load-string|load-file|println|print|prn|pr|printf|pr-str|print-str|println-str|future|pmap|agent|require|import)$"
    " That function is denied in this sandbox; build text with str and clojure.string."]
   [#"\b(println|print|prn|pr|printf|pr-str|print-str|println-str|slurp|spit|eval|read-string|load-string|load-file|future|pmap|agent|require|import) is not allowed!"
    " That function is denied in this sandbox; build text with str and clojure.string."]
   [#"Could not resolve symbol: (Long|Math|Character|System|Double)/"
    " That class is unavailable here; use parse-long, clojure.string or String methods."]
   ;; Recorded model programs called the context tool from code (research/Q_SUBSTRATE_PHASE3.md).
   [#"Could not resolve symbol: (context_query|context-query|context_metadata|context-metadata)"
    " Tools are not callable from code. The whole context is already bound: external-context (one string) and context-lines (a vector of its lines)."]
   [#"Could not resolve symbol: "
    " It is not defined in this worker; definitions from a stopped worker are gone. The repl_eval description lists what is available."]
   [#"java\.lang\.Character cannot be cast|count not supported on this type: Character"
    " A character was used where a string is needed: iterating a string yields characters, and external-context is one string; use context-lines for its lines and (str c) for one character."]
   [#"Cannot invoke \"clojure\.lang\.IFn\.invoke\(Object\)\" because the return value of .* is null"
    " A nil was called as a function: a lookup or re-find returned no match. Check the result with when-let before using it."]
   [#"Result is not EDN data"
    " Functions, atoms and other host objects cannot be returned; return data instead. A def is fine."]
   ;; A fixed-size slice of a shorter collection (subvec, nth). subs itself is bounded by the prelude.
   [#"out of bounds for length \d+|String index out of range|begin \d+, end \d+, length \d+|Index \d+ out of bounds"
    " The requested range exceeds the value's length. (page v offset n) returns at most n characters from offset and stops at the end; subs is bounded the same way; for subvec and nth, check (count v) first."]])

(def ^:private python-error-hints
  [[#"NameError: name '[A-Za-z_][A-Za-z0-9_]*' is not defined"
    " It is not defined in this worker; definitions from a stopped worker are gone. The repl_eval description lists what is available."]
   [#"outside the computation capability set"
    " Imports are limited to ast, collections, functools, itertools, operator, math, statistics, heapq, bisect, re, json, types and copy."]
   [#"Printed output limit"
    " This call's output was discarded and the worker keeps running. Return the value instead of printing it: large values come back as a preview with paging."]])

(defn explain-error [config message]
  (if (and (skill-interface/enabled? config) (re-find #"Could not resolve symbol: (clojure.repl/)?source(?:[. ]|$)" message))
    (str message ". Use the artifact_inspect tool with a hash from approved-functions to inspect retained source. It does not execute the function.")
    (if-let [[_ hint] (and (assisted? config)
                           (first (filter #(re-find (first %) message) (if (python? config) python-error-hints error-hints))))]
    (str message (when-not (re-find #"[.!?]$" message) ".") hint)
    message)))

(defn- tool-command [config {:keys [name input]}]
  (let [{:keys [op input_schema]} (first (filter #(= name (:name %)) (concat command-tools (program-tools config) (skill-tools config))))]
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
      :tool/call {:op op :name name :input input}
      :skill/inspect (merge {:section "function" :offset 0 :limit 4096} input {:op op})
      (assoc input :op op))))

(defn- tool-response-command [config response schemas]
  (let [blocks (:content response) calls (filter #(= "tool_use" (:type %)) blocks)]
    (when-not (and (vector? blocks) (every? #(#{"text" "thinking" "redacted_thinking" "tool_use"} (:type %)) blocks))
      (reject! :content-blocks false))
    (cond
      (and (= "tool_use" (:stop-reason response)) (= 1 (count calls))) nil
      (and (= "end_turn" (:stop-reason response)) (empty? calls)) (reject! :no-tool-call true)
      (> (count calls) 1) (reject! :multiple-commands false)
      :else (reject! :incomplete-turn false))
    (let [command (tool-command config (first calls))]
      (when-not (schema-valid? command schemas false) (reject! :tool-input true))
      command)))

(defn parse-response [config response schemas]
  (cond
    (tool-envelope? config) (tool-response-command config response schemas)
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

(defn truncated-tool-turn?
  "A provider turn that ends for tool use but carries no tool call: only text or
  thinking blocks. The response contradicts itself, so no command exists and
  nothing could have run. Opus 5.5 once returned one ending in a thinking block
  that read \"This part of the response was interrupted before it finished.\""
  [response]
  (let [blocks (:content response)]
    (and (= "tool_use" (:stop-reason response)) (vector? blocks)
         (every? #(#{"text" "thinking" "redacted_thinking"} (:type %)) blocks))))

(def ^:private final-answer-marker "FINAL ANSWER: ")

(defn terminal-text-answer
  "The answer in an explicit terminal text reply, or nil. Accepted only when the
  turn ended normally with no tool call and its whole text is one line:
  FINAL ANSWER: <answer>. Commentary, partial output, extra lines and a second
  marker are all refused."
  [response]
  (let [blocks (:content response) text (str/trim (str (:text response)))]
    (when (and (= "end_turn" (:stop-reason response)) (vector? blocks)
               (every? #(#{"text" "thinking" "redacted_thinking"} (:type %)) blocks)
               (some #(= "text" (:type %)) blocks)
               (not (re-find #"[\r\n]" text)) (str/starts-with? text final-answer-marker))
      (let [answer (str/trim (subs text (count final-answer-marker)))]
        (when (and (seq answer) (<= (count answer) 4096) (not (str/includes? answer (str/trim final-answer-marker))))
          answer)))))

(defn terminal-text-instruction []
  (str "Your response had no tool call, so nothing was executed. Call done with the exact final answer as summary. "
       "If you are finished but cannot call a tool, reply with exactly one line, FINAL ANSWER: <the exact final answer>, "
       "and nothing else; any other text is rejected. This is the task's only formatting correction; normal budgets still apply."))

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
(defn- truncation-text [config {:keys [preview total-chars shown-chars items kind]}]
  (str preview "\n[... truncated: showing the first " (format "%,d" shown-chars) " of " (format "%,d" total-chars)
       " characters" (when items (str " (a " kind " of " (format "%,d" items) " items)"))
       (if (python? config)
         (str ". The full text is bound to full_result; read more with page(full_result, " shown-chars ", 24000).]")
         (str ". The full value is bound to full-result; read more with (page full-result " shown-chars " 24000).]"))))

(defn- tool-result-text [config result]
  ;; A string value reads as plain text, like native printed output; escaped
  ;; EDN would put every line on one line. Other values and errors stay EDN.
  (cond
    (and (map? result) (= #{:value} (set (keys result))))
    (let [value (:value result)]
      (cond (string? value) value
            (and (map? value) (:aljure/truncated value)) (truncation-text config value)
            :else (write-value config value)))
    (and (map? result) (string? (:error result))) (write-value config (update result :error #(explain-error config %)))
    :else (write-value config result)))

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
