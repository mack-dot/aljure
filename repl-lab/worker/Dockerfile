ARG BASE_IMAGE
FROM ${BASE_IMAGE} AS build
WORKDIR /build
COPY worker/deps.edn deps.edn
RUN clojure -P && mkdir /libs && clojure -Spath > /tmp/classpath && \
    tr ':' '\n' < /tmp/classpath | while read p; do case "$p" in *.jar) cp "$p" /libs/ ;; esac; done
# Compile the worker and SCI ahead of time. Run from source, every cold worker
# compiled all of SCI on its one CPU before it could answer (about 6 s).
COPY worker/src /build/src
RUN mkdir /build/classes && java -cp "/build/src:/libs/*" clojure.main \
    -e "(binding [*compile-path* \"/build/classes\"] (compile 'repl-lab.worker))" && \
    jar cf /build/worker.jar -C /build/classes .

FROM ${BASE_IMAGE}
LABEL repl-lab.worker="1"
WORKDIR /worker
COPY --from=build /libs /libs
COPY --from=build /build/worker.jar /worker/worker.jar
COPY worker/src /worker/src
# Archive the classes a worker loads to answer its first request, under the
# exact runtime class path (CDS accepts jars only). JVM warnings go to stderr,
# never to the result wire.
RUN printf '{:source "(+ 20 22)" :bindings {}}\n' | java -XX:ArchiveClassesAtExit=/worker/worker.jsa \
    -Xlog:disable -Xlog:all=warning:stderr -Xmx160m -XX:ActiveProcessorCount=1 \
    -cp "/worker/worker.jar:/libs/*" clojure.main -m repl-lab.worker
USER 65534:65534
ENTRYPOINT ["java", "-XX:SharedArchiveFile=/worker/worker.jsa", "-Xlog:disable", "-Xlog:all=warning:stderr", "-Xmx160m", "-XX:ActiveProcessorCount=1", "-XX:+ExitOnOutOfMemoryError", "-cp", "/worker/worker.jar:/libs/*", "clojure.main", "-m", "repl-lab.worker"]
