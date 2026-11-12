(ns repl-lab.isolation (:require [repl-lab.util :as u] [repl-lab.limits :as limits] [clojure.java.io :as io] [clojure.string :as str])
  (:import [java.util.concurrent TimeUnit]))
(defn verify-limits [check requested]
  (let [limits (:limits check)
        actual {:memory-mb (:memory_mb limits) :cpus (:cpus limits) :pids (:pids limits)
                :scratch-mb (:scratch_mb limits) :wall-ms (* 1000 (get limits :wall_seconds 0))
                :output-bytes (:output_bytes limits)}]
    (if (and (:ready check) (not= requested actual))
      (assoc check :ready false :reason "Configured isolation limits differ from the enforced worker limits"
             :requested requested :enforced actual)
      check)))
(defn script [language]
  (case language :clojure "scripts/isolation.py" :python "scripts/python_isolation.py"
        (u/fail "Unknown execution language" {:language language})))
(defn output-bound
  "Per-expression output bound shared with scripts/isolation.py: 64 KB by
  default (the benchmark control), 1 MB only when explicitly configured."
  []
  (let [value (or (System/getenv "REPL_LAB_WORKER_OUTPUT_BYTES") "65536")]
    (u/ensure! (#{"65536" "1048576"} value) "Unsupported worker output bound" {})
    (Long/parseLong value)))
(defn proof-path []
  (let [bound (output-bound)]
    (if (= 65536 bound) "var/isolation-proof.json" (str "var/isolation-proof-" bound ".json"))))
(def ^:dynamic *doctor-wait-s* 12)
(defn- audit-dir [] (System/getenv "REPL_LAB_WORKER_AUDIT_DIR"))
(defn- record-refusal!
  "A supervisor stopped before it could record its own preflight leaves this
  refusal instead, so the paired runner still sees the gate fail and stops."
  [reason]
  (when-let [dir (audit-dir)]
    (let [f (io/file dir "preflight" (str (str/replace (str (java.util.UUID/randomUUID)) "-" "") ".json"))]
      (io/make-parents f)
      (spit f (u/json-str {:ready false :reason reason :doctor-wait-s *doctor-wait-s*})))))
(defn doctor
  ([] (doctor :clojure))
  ([language]
  (let [p (.start (ProcessBuilder. ^java.util.List ["python3" (script language) "doctor"]))
        output (future (slurp (.getInputStream p)))]
    (if (.waitFor p *doctor-wait-s* TimeUnit/SECONDS)
      (verify-limits (u/json-read @output) (cond-> (:isolation (u/read-file "config/experiment.edn"))
                                             (= language :clojure) (assoc :output-bytes (output-bound))))
      (do (.destroyForcibly p) (record-refusal! "Isolation preflight timeout")
          {:ready false :reason "Isolation preflight timeout"})))))
(def negative-cases #{:loop :allocation :oversized-result :read :write :process :network :evaluator :reader-eval})
(defn validate-proof! [check proof]
  (u/ensure! (:ready check) "Generated-code execution disabled" check)
  (u/ensure! (and (= "TESTED" (:status proof)) (= 2 (:gate-version proof))
                  (= (:supervisor-sha256 proof) (u/sha (slurp "scripts/isolation.py")))
                  (= negative-cases (set (keys (:startup proof)))) (every? true? (vals (:startup proof)))
                  (= (:image check) (:image proof)) (= (output-bound) (:output-bytes proof))
                  (= #{:at-bound :over-bound} (set (keys (:boundary proof)))) (every? true? (vals (:boundary proof)))
                  (= negative-cases (set (keys (:results proof))))
                  (every? true? (vals (:results proof))))
             "Isolation proof is incomplete or differs from the worker image; run make isolation-test" {})
  check)
(defn require-tested! []
  (let [check (doctor) path (io/file (proof-path))]
    (u/ensure! (:ready check) "Generated-code execution disabled" check)
    (u/ensure! (.isFile path) "Run make isolation-test successfully before live execution" {})
    (validate-proof! check (u/json-read (slurp path)))))
(defn open-session!
  ([] (open-session! nil))
  ([deadline-ms] (open-session! deadline-ms :clojure))
  ([deadline-ms language]
  (limits/timeout-ms deadline-ms 120000)
  (let [check (if (= language :clojure) (doctor) (doctor language))]
    (u/ensure! (:ready check) "Generated-code execution disabled" check)
    (limits/timeout-ms deadline-ms 120000)
    (let [builder (ProcessBuilder. ^java.util.List ["python3" (script language) "session"])
          _ (when deadline-ms (.put (.environment builder) "REPL_LAB_TASK_DEADLINE_MS" (str deadline-ms)))
          p (.start builder)]
      {:process p :writer (io/writer (.getOutputStream p)) :reader (io/reader (.getInputStream p))
       :language language :deadline-ms deadline-ms :errors (future (slurp (.getErrorStream p)))}))))
(defn close-session! [{:keys [process writer errors]}]
  ;; A worker that already stopped has a closed pipe; its exit is still confirmed below.
  (try (.close ^java.io.Writer writer) (catch java.io.IOException _ nil))
  ;; Closing stdin asks the supervisor to reap the entire container. The supervisor
  ;; enforces its own wall deadline even if this controller crashes.
  ;; The supervisor may take up to about 45 s to confirm removal under host load.
  (when-not (.waitFor process 60 TimeUnit/SECONDS)
    (u/fail "Supervisor did not confirm worker termination" {}))
  (when (= 3 (.exitValue process))
    (u/fail "Worker cleanup unconfirmed" {:supervisor-exit 3
             :worker-stderr (when errors (deref errors 1000 "Diagnostics unavailable"))})))
(def reply-bound
  "The supervisor's per-line input limit (scripts/isolation.py LIMITS input_bytes); a longer
  reply line would stop the worker, so a larger tool result is refused before it is written."
  65535)

(defn- read-line! [{:keys [reader deadline-ms] :as session}]
  (let [read-result (future (.readLine ^java.io.BufferedReader reader))
        line (deref read-result (limits/timeout-ms deadline-ms 20000) ::timeout)]
    (when (= line ::timeout) (close-session! session) (u/fail "Worker response timeout" {}))
    (u/ensure! (string? line) "Worker terminated without result"
               (when-not (string? line)
                 {:worker-stderr (if-let [errors (:errors session)] (deref errors 5000 "Diagnostics unavailable") "Diagnostics unavailable")}))
    (u/ensure! (<= (count line) (output-bound)) "Worker result too large" {})
    line))

(defn request!
  "One request to the worker; its value, or a failure. With a handler, lines of the form
  {:tool-request {:seq :name :input}} that the worker writes while it evaluates are tool
  requests (worker/src/repl_lab/bridge.clj): each is answered with the handler's
  {:tool-result v} or {:tool-error message} on the same pipe, and reading resumes. A handler
  failure, or a reply line the supervisor would refuse, becomes a tool error; the worker is
  never left waiting. Without a handler, a tool request is answered with a tool error, so a
  request that granted no tools behaves exactly as before."
  ([session request] (request! session request nil))
  ([{:keys [writer deadline-ms language] :as session} request handler]
   (let [wire ((if (= language :python) u/json-str pr-str) request)]
     (limits/timeout-ms deadline-ms 20000)
     (u/ensure! (<= (count (.getBytes wire "UTF-8")) 65535) "Worker input too large" {})
     (.write writer (str wire "\n")) (.flush writer)
     (loop []
       (let [line (read-line! session)
             result ((if (= language :python) u/json-read u/read-edn) line)]
         (if-let [tool-request (and (= language :clojure) (map? result) (= #{:tool-request} (set (keys result)))
                                    (map? (:tool-request result)) (:tool-request result))]
           (let [reply (try (if handler
                              (let [r (handler tool-request)]
                                (if (and (map? r) (#{#{:tool-result} #{:tool-error}} (set (keys r)))
                                         (or (contains? r :tool-result) (string? (:tool-error r))))
                                  r
                                  {:tool-error "Bridge returned a malformed reply"}))
                              {:tool-error "No tool bridge in this session"})
                            (catch Exception e {:tool-error (let [m (str (.getMessage e))] (subs m 0 (min 1000 (count m))))}))
                 reply-wire (pr-str reply)
                 reply-wire (if (<= (count (.getBytes reply-wire "UTF-8")) (dec reply-bound))
                              reply-wire
                              (pr-str {:tool-error (str "Tool result too large for the worker (" (count (.getBytes reply-wire "UTF-8"))
                                                        " bytes); request a smaller slice")}))]
             (.write writer (str reply-wire "\n")) (.flush writer)
             (recur))
           (do (u/ensure! (not (:error result)) (str "Worker rejected expression: " (:error result)) {:error (:error result)})
               (:value result))))))))

(defn evaluate!
  "One evaluation. The SCI worker takes a source string; the Python worker also takes a
  request map ({:source :display} or {:source :answer}), whose extra keys it validates."
  [session source bindings]
  (u/ensure! (or (string? source) (and (map? source) (= :python (:language session)))) "Invalid worker source" {})
  (request! session (if (map? source) (assoc source :bindings bindings) {:source source :bindings bindings})))

(defn run-program!
  "One evaluation with a tool grant: bridge requests are answered by handler."
  [session source bindings tools handler]
  (request! session {:source source :bindings bindings :tools tools} handler))
