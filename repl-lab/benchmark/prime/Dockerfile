# Native pinned Prime. No upstream source changes; no credentials in this image.
ARG RUST_IMAGE=rust@sha256:93ce27a88655056a51dbdd8f5f2d7ddc071c7b0070fb288a37b5a285fc83971e
ARG PYTHON_IMAGE=python@sha256:fd95fa221297a88e1cf49c55ec1828edd7c5a428187e67b5d1805692d11588db
FROM ${RUST_IMAGE} AS build
WORKDIR /source
COPY source/ /source/
RUN cargo build --release --locked -j 2 -p pa-cli --bin prime-agent

FROM ${PYTHON_IMAGE}
ARG PRIME_COMMIT
LABEL repl-lab.prime-native="true" repl-lab.prime-commit="${PRIME_COMMIT}"
COPY source/ /opt/prime/
COPY --from=build /source/target/release/prime-agent /usr/local/bin/prime-agent
COPY default-packages.lock /opt/prime/default-packages.lock
# Pin the installer and use Prime's committed runtime lock. Preserve native skills.
RUN python -m pip install --no-cache-dir uv==0.8.2 && \
    UV_PROJECT_ENVIRONMENT=/opt/venv uv sync --frozen --all-groups --no-python-downloads \
      --python /usr/local/bin/python --project /opt/prime/prime-agent-runtime && \
    uv pip install --python /opt/venv/bin/python --require-hashes -r /opt/prime/default-packages.lock
RUN python - <<'PY'
from pathlib import Path
import subprocess
skills = sorted(str(p.parent) for p in Path('/opt/prime/skills').glob('*/pyproject.toml'))
subprocess.run(['uv', 'pip', 'install', '--python', '/opt/venv/bin/python', '--no-deps', *skills], check=True)
with open('/opt/prime/installed-packages.txt', 'w') as output:
    subprocess.run(['uv', 'pip', 'freeze', '--python', '/opt/venv/bin/python'], stdout=output, check=True)
PY
RUN groupadd --gid 10001 benchmark && useradd --uid 10001 --gid 10001 --home-dir /work --no-create-home benchmark && \
    mkdir /work && chown 10001:10001 /work
ENV PI_PACKAGE_DIR=/opt/prime \
    PRIME_AGENT_KERNEL_PYTHON=/opt/venv/bin/python \
    PRIME_AGENT_CODING_AGENT_DIR=/work/agent \
    PRIME_AGENT_SESSION_DIR=/work/sessions \
    DO_NOT_TRACK=1 \
    UV_OFFLINE=1 \
    PYTHONDONTWRITEBYTECODE=1
USER 10001:10001
WORKDIR /work
ENTRYPOINT ["/usr/local/bin/prime-agent"]
