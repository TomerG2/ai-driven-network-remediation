# RCA artifact rollout and second incident

## Inputs and provenance

The recovered issue-196 RCA checkpoint and `rca_preprocessing.json` are the
task artifacts. Their SHA-256 values are pinned in
`model-serving/ran-ml-service/tests/fixtures/rca_reference.json` and the
validation report in this directory. The report records the TelecomTS dataset
revision, split seed, ten-class mapping, backbone revision, training code, and
held-out metrics. The predictor image bakes the backbone offline; KServe stages
the task files from `STORAGE_URI` beneath `/mnt/models`.

The local parity check uses four TelecomTS cases: antenna failure, severe
co-channel interference, severe Doppler shift, and sudden congestion. Indices,
labels, confidence, and all ten logits are pinned. Absolute tolerances are
0.0001 for confidence and logits. The dedicated model-serving CI verifies
the checkpoint, preprocessing, notebook, and fixture hashes and keeps the AD
parity test alongside RCA. The heavy checkpoint test is outside hub unit tests.
After publication, set the repository variable `RCA_ARTIFACT_COMMIT` to the
40-character Hugging Face commit SHA containing the final `release.json` upload.
CI downloads both RCA files from that immutable revision.

## Repeatable commands

From the repository root, with `hf` authenticated for write and `oc` logged in:

```sh
# Build and deploy both heads independently from the shared image.
# Set IMAGE to an existing immutable image reference when SKIP_BUILD=1.
TASK=classify VERSION=<image-tag> ARTIFACT_REVISION=rca-196-initial \
  ./model-serving/ran-ml-service/deploy/publish-and-deploy.sh

# If an OpenShift BuildConfig produced the image, use its internal reference:
TASK=classify SKIP_BUILD=1 ARTIFACT_REVISION=rca-196-initial \
  IMAGE=image-registry.openshift-image-registry.svc:5000/model-serving/ran-ml-service@sha256:<digest> \
  ./model-serving/ran-ml-service/deploy/publish-and-deploy.sh

# A new artifact commit can reuse the same checkpoint and preprocessing bytes.
TASK=classify VERSION=<same-image-tag> SKIP_BUILD=1 \
  ARTIFACT_REVISION=rca-196-refresh-1 \
  ./model-serving/ran-ml-service/deploy/publish-and-deploy.sh

# Detect retains its defaults and its independent InferenceService.
TASK=detect SKIP_HF_UPLOAD=1 SKIP_BUILD=1 VERSION=<detect-image-tag> \
  ./model-serving/ran-ml-service/deploy/publish-and-deploy.sh
```

`STORAGE_URI`, `HF_REPO`, artifact paths, manifest paths, namespace, Service
name, Route name, and smoke fixture can be overridden through the command's
environment variables. The classifier command verifies local artifact hashes,
publishes a model card and `release.json`, checks KServe readiness and task
identity from the same-cluster Service, then smoke-tests `/v1/classify` through
both the same-cluster Service and external TLS Route. `RENDER_ONLY=1` prints the
manifests without publishing, building, or deploying. The refresh changes the
predictor environment to force a KServe revision even when the model bytes are
compatible. There is no automatic registry promotion.

Set `ADNR_CLASSIFY_INFERENCE_URL` to the full same-cluster URL from the command
output, or to `https://<route-host>/v1/classify` for an external hub. Keep it
unchanged across the artifact refresh. `ADNR_CLASSIFY_TOKEN` is optional and
only forwards a bearer header; the predictor does not enforce token auth.
For local serving, run `uv run --offline ran-ml-service` inside
`model-serving/ran-ml-service` with `TASK=classify` and `MANTIS_MODEL_PATH`
pointing to the local checkpoint beside `rca_preprocessing.json`. The backbone
must already be cached.

## Full incident probe after refresh

Keep `ADNR_DETECT_INFERENCE_URL` and `ADNR_CLASSIFY_INFERENCE_URL` configured
in the hub release. Port-forward the chatbot, RCA, and remediation Services,
then run the dedicated integration test with:

```sh
RCA_REAL_E2E=1 RCA_FIXTURE_SCENARIO=co_channel_interference_severe \
RCA_EXPECTED_MODE=used RCA_GUIDANCE_THRESHOLD=0 \
RCA_EXPECTED_CLASSIFY_URL="$ADNR_CLASSIFY_INFERENCE_URL" \
RCA_EXPECTED_CLASSIFY_TOKEN="${ADNR_CLASSIFY_TOKEN:-}" \
RCA_DEPLOYMENT_NAMESPACE=<hub-namespace> \
RCA_EVIDENCE_FILE=/tmp/issue-04-incident.json \
RAN_RCA_SERVICE_URL=http://localhost:<rca-port> \
RAN_REMEDIATION_SERVICE_URL=http://localhost:<remediation-port> \
RAN_CHATBOT_SERVICE_URL=http://localhost:<chatbot-port> \
uv run --directory hub/integration-tests pytest tests/telco/test_rca_real_e2e.py -q
```

The probe triggers the existing fixture through AD and anomaly Kafka. It
asserts incident identity, the full KPI window, pinned ML advice, enriched
Kafka and API records, the LLM's final category, the existing remediation
template handoff, and chat. Its JSON evidence file records the resulting
incident ID and chat reply. Record the two InferenceService revisions, Route
host, deployed consumer URL, and probe evidence when the live rollout runs.

## Execution status

Local hash and parity checks passed on 2026-10-15. The source-only shared image
build `ran-ml-overlay-6` succeeded in `model-serving` and pushed
`ran-ml-service:0.1.6-rca-196` with digest
`sha256:3ab782242316bdf9878f83541655ecb2d0e79e77703c98e5214de8af31c61b7c`.
The BuildConfig output tag was restored to its earlier value afterward.
On 2026-10-15, the local checkpoint and preprocessing hashes matched the pinned
values, the four-case real-checkpoint parity test passed, and predictor typecheck
passed. Hugging Face authentication was available, but the classifier repository
was absent. Automatic approval review rejected publishing the private 31 MB
checkpoint and metadata to a public repository because the generic issue request
did not clearly authorize that payload and destination. OpenShift API access was
reachable with network access but returned `Unauthorized` for the current login.
Publication, initial deployment, compatible refresh, and the post-refresh
incident remain unverified until explicit public-upload approval and a valid
OpenShift login are available.
