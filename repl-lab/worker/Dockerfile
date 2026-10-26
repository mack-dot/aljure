ARG BASE_IMAGE
FROM ${BASE_IMAGE} AS build
WORKDIR /build
COPY worker/deps.edn deps.edn
RUN clojure -P && mkdir /libs && clojure -Spath > /tmp/classpath && \
    tr ':' '\n' < /tmp/classpath | while read p; do case "$p" in *.jar) cp "$p" /libs/ ;; esac; done

FROM ${BASE_IMAGE}
LABEL repl-lab.worker="1"
WORKDIR /worker
COPY --from=build /libs /libs
COPY worker/src /worker/src
USER 65534:65534
ENTRYPOINT ["java", "-Xmx160m", "-XX:ActiveProcessorCount=1", "-XX:+ExitOnOutOfMemoryError", "-cp", "/worker/src:/libs/*", "clojure.main", "-m", "repl-lab.worker"]
