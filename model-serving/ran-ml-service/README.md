# ran-ml-service

Mantis time-series ML predictor for TelecomTS anomaly detection (TASK=detect) and root cause analysis (TASK=classify).

## Deploy or refresh

Use the deploy script rather than applying the InferenceService by hand:

```sh
# Re-apply the existing InferenceService without rebuilding the image
# or re-uploading model weights.
SKIP_HF_UPLOAD=1 SKIP_BUILD=1 \
  ./model-serving/ran-ml-service/deploy/publish-and-deploy.sh
```

For predictor source changes, build and deploy a new, immutable image tag so
KServe creates a new revision:

```sh
SKIP_HF_UPLOAD=1 VERSION=<new-image-tag> \
  ./model-serving/ran-ml-service/deploy/publish-and-deploy.sh
```

### Building on macOS

On macOS, podman machine volume mounts may be unreliable. Use OpenShift BuildConfig to build on the cluster instead:

```sh
# Build on OpenShift cluster (recommended for macOS)
SKIP_HF_UPLOAD=1 USE_OPENSHIFT_BUILD=1 \
  ./model-serving/ran-ml-service/deploy/publish-and-deploy.sh
```

This uploads the build context to the cluster and uses the `ran-ml-overlay` BuildConfig to build the image.
The BuildConfig outputs to an ImageStreamTag that the InferenceService references.

The script rewrites `metadata.namespace` from `ISVC_NAMESPACE` (default `model-serving`) and waits for the InferenceService to become ready. KServe's `{.status.url}` is the in-cluster Service (`*.svc.cluster.local`). Callers outside the cluster use the Route `ran-ml-service-external`:

```bash
oc get route ran-ml-service-external -n "$ISVC_NAMESPACE" -o jsonpath='https://{.spec.host}/v1/detect'
```

Set that value as `ADNR_DETECT_INFERENCE_URL`. `ADNR_DETECT_TOKEN` is optional; the detector sends `Authorization: Bearer` only when it is set. A same-cluster caller can use `{.status.url}/v1/detect` instead.

## Endpoints

- `POST /v1/detect` — Binary anomaly detection on a 128x18 KPI window
- `GET /health` — Liveness probe
- `GET /ready` — Readiness probe (model loaded)

## Configuration

| Env Var | Description |
|---------|-------------|
| `TASK` | `detect` or `classify` |
| `MANTIS_MODEL_PATH` | Local path to `.pt` weights file |
| `MANTIS_CHECKPOINT` | HuggingFace backbone ID (default: `paris-noah/Mantis-8M`, baked into image) |
| `PORT` | HTTP port (default: 8080) |

For local RCA inference, place `mantis_pretrained_rca.pt` and
`artifacts/rca_preprocessing.json` in one directory, then run:

```sh
cd model-serving/ran-ml-service
TASK=classify MANTIS_MODEL_PATH=/path/to/mantis_pretrained_rca.pt uv run ran-ml-service
```

The Mantis-8M backbone must be present in the Hugging Face cache for offline
mode. `POST /v1/classify` accepts `{"kpi_window": [...]}` with all 128 rows and
returns `class`, `class_index`, and `confidence`. `/ready` stays unavailable if
the checkpoint task, head dimensions, or preprocessing artifact (including its
ordered RCA class mapping) is invalid.

## RCA checkpoint recovery

`scripts/train_rca.py` runs only the 10-class pretrained Mantis RCA task from
the TelecomTS notebook. It fixes the dataset revision, backbone revision,
80/20 seed-42 split, class order, and defaults of 35 epochs, batch size 64,
and learning rate `1e-4`. A non-35-epoch `--epochs` run is marked exploratory even
if its metrics pass. It requires a private, durable mounted output directory. No model is
published or deployed by this command.

The script reads the three Arrow shards of the pinned TelecomTS revision. If
they are not already cached, fetch them once with `datasets` using the revision
`1b3a88a440f4922edfcd1e230e42c003c0e13bdf` and
`data_files={"full": "**/chunked.jsonl"}`, then pass the resulting Arrow
directory as `--dataset-dir`.

```sh
cd model-serving/ran-ml-service
uv sync --locked --group train
uv run --locked --group train python scripts/train_rca.py \
  --output-dir /private/durable-storage/rca-run-196
```

The output directory contains `mantis_pretrained_rca.pt`, the paired
`rca_preprocessing.json`, and `rca_validation_report.json`. The report records
both serving-style and notebook-style scores, the 10-class confusion matrix
and per-class metrics, separate Jamming predictions, artifact SHA-256 hashes,
dependency versions, and provenance. Only the serving-style score sets the
pass/fail status. Retain a failed report for diagnosis; a failed gate is not a
validated checkpoint.
