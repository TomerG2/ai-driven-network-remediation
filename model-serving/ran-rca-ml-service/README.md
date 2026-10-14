# Mantis RCA serving

The `ran-rca-ml-service` KServe InferenceService uses the shared predictor image
with `TASK=classify`. It runs separately from the hub chart. Publish the
original `mantis_pretrained_rca.pt` export and `rca_preprocessing.json` in the
same Hugging Face repository before applying these manifests. The checkpoint
must be the pretrained RCA export from the TelecomTS notebook; the AD checkpoint
is incompatible. Set `STORAGE_URI` to the published repository. KServe stages
its contents under `/mnt/models`, where `MANTIS_MODEL_PATH` selects the RCA
checkpoint. The image bakes the Mantis-8M backbone for offline startup.
The checkpoint and preprocessing file must match the SHA-256 values in the
InferenceService annotations and the validation report.

```sh
# Run from the repository root. Requires hf, oc, and a registry login.
TASK=classify VERSION=<new-image-tag> ARTIFACT_REVISION=rca-196-initial \
  ./model-serving/ran-ml-service/deploy/publish-and-deploy.sh

# A compatible artifact refresh can reuse the same trained weights and image.
# Change ARTIFACT_REVISION so KServe creates a new predictor revision and stages
# the repository contents again. Keep the consumer URL configured as before.
TASK=classify SKIP_BUILD=1 VERSION=<deployed-image-tag> \
  ARTIFACT_REVISION=rca-196-refresh-1 \
  ./model-serving/ran-ml-service/deploy/publish-and-deploy.sh
```

The command verifies local artifact hashes, applies the InferenceService and
Route in `ISVC_NAMESPACE` (default `model-serving`), waits for readiness, checks
task identity on `/health` and `/ready`, and sends the checked-in antenna
fixture to `/v1/classify` over the TLS Route. It checks the in-cluster Service
from the predictor pod and validates the Route's TLS certificate. A changed `ARTIFACT_REVISION`
changes the predictor environment, triggering a revision even when
`STORAGE_URI` stays the same. The command republishes `release.json` with the
new revision and pinned hashes, creating a remote artifact commit. `STORAGE_URI`,
`HF_REPO`, `WEIGHTS_PATH`,
`PREPROCESSING_PATH`, `ISVC_NAME`, `ISVC_YAML`, `ROUTE_YAML`,
`EXTERNAL_ROUTE_NAME`, and `SMOKE_FIXTURE` are overridable. The default smoke
fixture must return Antenna Failure at index 0; set `SMOKE_EXPECTED_CLASS` and
`SMOKE_EXPECTED_INDEX` when selecting another fixture. For a compatible
new checkpoint, set `CHECKPOINT_SHA256` and `PREPROCESSING_SHA256` to its verified
hashes. The default artifacts are the recovered issue-196 checkpoint and bundle.

For local inference with the available files, run `cd model-serving/ran-ml-service`
then `TASK=classify MANTIS_MODEL_PATH=.private-artifacts/issue-196/mantis_pretrained_rca.pt uv run --offline ran-ml-service`.
The backbone must already be in the Hugging Face cache for offline mode.

For a caller in the cluster, set `CLASSIFY_INFERENCE_URL` to
`http://ran-rca-ml-service-predictor.model-serving.svc.cluster.local/v1/classify`.
For an external caller, use
`https://$(oc get route ran-rca-ml-service-external -n model-serving -o jsonpath='{.spec.host}')/v1/classify`.
`CLASSIFY_TOKEN` only forwards a bearer header; the predictor has no built-in
token authentication. Set `ADNR_CLASSIFY_INFERENCE_URL` and optionally
`ADNR_CLASSIFY_TOKEN` for the hub deployment; a refresh of the predictor does
not require changing either value.

The validation report at `docs/model-runs/issue-196-rca-validation.json` records
dataset revision, split seed, training code revision, backbone revision, all ten
class names, checkpoint and preprocessing hashes, and measured held-out parity.
The RCA weights were newly trained in issue 196 because the historical
checkpoint was unavailable. The report is the available provenance; no original
MLflow run is claimed for these weights.
