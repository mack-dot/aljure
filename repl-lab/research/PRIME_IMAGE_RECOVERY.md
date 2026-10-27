# Recovering the pinned native Prime runtime

Recovery has two distinct paths. An exact archive must restore its recorded image
identity. A rebuild receives a new identity and requires a new experiment freeze,
native isolation proof, and common relay proof. Never relabel a rebuild as the
missing image. Neither operation authorizes inference.

## Build inputs and scope

The unchanged recipe is `benchmark/prime/Dockerfile`. The existing builder is
`python3 scripts/setup_prime.py`. It requires a clean upstream checkout at
`c4c238ca025e382d96fb5f37e6328ca77fb82ef3`, exports only tracked source with
`git archive`, and passes no credentials or host mounts into the build.

- Rust base: `rust@sha256:93ce27a88655056a51dbdd8f5f2d7ddc071c7b0070fb288a37b5a285fc83971e`.
- Python base: `python@sha256:fd95fa221297a88e1cf49c55ec1828edd7c5a428187e67b5d1805692d11588db`.
- Cargo uses the upstream `Cargo.lock` with `--locked`.
- Python uses upstream `prime-agent-runtime/uv.lock` with `--frozen` and the
  hash-checked `benchmark/prime/default-packages.lock`. The installer is uv 0.8.2.
- Native skills are built from the same upstream source. Their upstream build
  requirements are not a fully hermetic build-tool lock. Image creation metadata
  also varies. Do not claim that a fresh build must reproduce an earlier digest.
- The source archive retains upstream license notices and attribution. No Prime
  algorithm, skill, prompt or tool implementation is changed by this procedure.

## Seal and verify an image

After `setup_prime.py` succeeds, use its new report path:

```sh
python3 -m scripts.prime_image_recovery seal \
  --build-report var/prime-builds/BUILD_REPORT.json \
  --out var/prime-image-recovery/UNIQUE_BUNDLE
```

This command refuses an existing output directory. It verifies source and base
pins, recipe/package hashes, image labels, and every source file against a fresh
archive of the pinned Git revision. It then writes:

- `image.tar`: the Docker image, outside Docker's own image/cache storage.
- `build-inputs.tar`: pinned source archive, unchanged Dockerfile, package lock,
  and original build report. The source archive includes Cargo and uv locks.
- `manifest.json`: image configuration/filesystem identity, source hashes,
  archive sizes and SHA-256 values. No runtime session, transcript or credential
  source is included.

Record the printed manifest hash in the committed research evidence. Use that
independent trusted value to verify or restore the bundle; do not trust a new
hash supplied only alongside an untrusted archive.

```sh
python3 -m scripts.prime_image_recovery verify \
  --manifest var/prime-image-recovery/UNIQUE_BUNDLE/manifest.json \
  --trusted-manifest-sha256 TRUSTED_HASH_FROM_COMMITTED_RECORD
```

Keep the large image archive outside Git. It survives Docker image/cache removal,
but a single local copy is not disaster recovery for disk loss. Copy the verified
bundle to operator-managed backup storage when available. This procedure does
not upload it or provision external infrastructure.

## Restore without substitution

```sh
python3 -m scripts.prime_image_recovery restore \
  --manifest var/prime-image-recovery/UNIQUE_BUNDLE/manifest.json \
  --trusted-manifest-sha256 TRUSTED_HASH_FROM_COMMITTED_RECORD
```

The helper verifies both archive files before calling Docker load. It rejects
tampered manifests, changed archives, unexpected file names and symlink artifacts.
After import, the image ID, configuration, architecture and filesystem identity
must match the trusted record. It does not change `var/prime-worker.env`, install
old proofs, or start an agent. Native and SCI resource restrictions remain in the
existing supervisors.

Select only the verified immutable ID for the new protocol, then run native
isolation and the actual native/SCI relay in its frozen checkout. The protocol's
`execution_images` pins must match both current proofs. A different image fails
preflight even when it has its own passing proof. New inference still requires
approval of the resulting exact plan and allocation.

The recorded recovery run must distinguish unit fixtures from an actual image
export/import and from the native/SCI relay's scripted model responses. No
offline recovery result is a live benchmark score.
