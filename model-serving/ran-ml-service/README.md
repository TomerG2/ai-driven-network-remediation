# ran-ml-service

Mantis time-series ML predictor for TelecomTS anomaly detection (TASK=detect) and root cause analysis (TASK=classify).

## Deploy or refresh

Use the deploy script rather than applying the InferenceService and Route separately:

```sh
# Re-apply the existing InferenceService and external Route without rebuilding
# the image or re-uploading model weights.
SKIP_HF_UPLOAD=1 SKIP_BUILD=1 \
  ./model-serving/ran-ml-service/deploy/publish-and-deploy.sh
```

For predictor source changes, build and deploy a new, immutable image tag so
KServe creates a new revision:

```sh
SKIP_HF_UPLOAD=1 VERSION=<new-image-tag> \
  ./model-serving/ran-ml-service/deploy/publish-and-deploy.sh
```

The script waits for the InferenceService to become ready and applies the
external Route after it is ready. The Route's Authorino policy and its bearer
token remain cluster-managed configuration.

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
