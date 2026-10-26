ARG BASE_IMAGE
FROM ${BASE_IMAGE}
LABEL repl-lab.python-worker="1"
WORKDIR /worker
COPY worker/src/repl_lab/python_worker.py /worker/python_worker.py
USER 65534:65534
ENTRYPOINT ["python3", "-I", "-u", "/worker/python_worker.py"]
