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
The repository variable `RCA_ARTIFACT_COMMIT` pins the 40-character Hugging Face
commit SHA containing the final `release.json` upload. CI downloads both RCA
files from that immutable revision.

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
On 2026-10-15 the user explicitly approved publishing the newly trained RCA
checkpoint to the public Hugging Face repository, and the OpenShift login was
refreshed. The shared command published the checkpoint, preprocessing bundle,
model card, and `release.json` to `TomerG2/mantis-rca-telecomts`. The initial
artifact commit was `1a6767e656884d90c6ab35a1d85d4b3eed6e1019`. KServe
staged the files and brought `ran-rca-ml-service` to Ready at InferenceService
generation 1 with `ARTIFACT_REVISION=rca-196-initial`. The shared image was the
immutable digest above. Both the same-cluster Service and TLS Route returned
`Antenna Failure`, class index 0, confidence 0.9293 for the smoke fixture.

The first compatible refresh reused the image and artifact bytes, publishing a
new `release.json` at commit `2bf794bc808a8293cafd8693b2ce46dad7c0a954`.
InferenceService generation and predictor Deployment revision advanced to 2,
with `ARTIFACT_REVISION=rca-196-refresh-1`. After configuring the CI hub, the
same command published `rca-196-refresh-2` at commit
`1ffdc117e0f0c93ba779f0b5f69323d5f1c38163`. Generation and Deployment
revision advanced to 3, and a new ready predictor pod staged the artifacts.
The same Service URL and Route remained in use throughout; both smoke requests
returned class index 0 and confidence 0.9293 after each refresh. The Route is
`https://ran-rca-ml-service-external-model-serving.apps.ai-dev02.kni.syseng.devcluster.openshift.com/v1/classify`;
the same-cluster URL is
`http://ran-rca-ml-service-predictor.model-serving.svc.cluster.local/v1/classify`.
The upstream `RCA_ARTIFACT_COMMIT` Actions variable pins the final commit.
Files downloaded from that exact commit matched the expected SHA-256 values.
With the downloaded RCA files and pinned AD checkpoint, all 45 model-serving
tests passed locally, including both real-checkpoint parity tests. The dedicated
[hosted parity run](https://github.com/TomerG2/ai-driven-network-remediation/actions/runs/38758087687)
also passed against the pushed `feat/rca-ml-integration` branch and the final
artifact commit.

The existing detect InferenceService remained Ready with task `detect`. Its
same-cluster Service and the configured external TLS Route returned detect
health and readiness; the Route classified the antenna fixture as anomalous
with class index 1 and confidence 0.9995.

For the incident probe, the available `ci-hub-telco-oran` release had older
0.1.5 RCA/chatbot images and no classifier URL. The current RCA and chatbot
images were built and staged in that namespace's internal registry, then only
those two Deployments were updated to immutable image digests. The RCA
Deployment was configured with the same-cluster URL above, an empty token, and
threshold 0 **before** `rca-196-refresh-2`; its URL was unchanged afterward.
Both Deployments were Ready. This targeted CI update is outside the saved Helm
release values, so a future Helm upgrade should set
`telco.ranRcaService.env.classifyInferenceUrl` and deploy the current consumer
images to retain this configuration.

The post-refresh `co_channel_interference_severe` fixture produced incident
`9334e533`. The [live evidence](issue-04-incident.json) records the ML advice:
Co-Channel Interference (Severe), index 2, confidence 0.9502, status `used`.
The integration probe checked the original incident identity and complete KPI
window across AD, anomaly Kafka, enriched Kafka, and the API; it also checked
rejection of malformed Kafka messages. RAG/Granite supplied the final
operational category `interference`, remediation selected
`ran-interference-mitigation`, and chat distinguished the accepted ML advice
from the final LLM category. The live probe passed on 2026-10-15. Current RCA
and chatbot consumer unit suites passed locally with 107 and 70 tests.
