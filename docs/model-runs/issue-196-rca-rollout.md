# RCA classifier artifact rollout

## Inputs and provenance

The recovered issue-196 RCA checkpoint and `rca_preprocessing.json` are the
task artifacts. Their SHA-256 values are pinned in
`model-serving/shared-ml-predictor/tests/fixtures/rca_reference.json` and the
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
The parity workflow pins `RCA_ARTIFACT_COMMIT` to the 40-character Hugging Face
commit SHA containing the final `release.json` upload. CI downloads both RCA
files from that immutable revision, including for pull requests from forks.

## Repeatable commands

To deploy both services from the same existing image in one command, run
`TASK=both SKIP_HF_UPLOAD=true SKIP_BUILD=true IMAGE=<shared-image-reference>`
with the shared `publish-and-deploy.sh` command. To build the image once before
deploying both, omit `SKIP_BUILD=true` and set a new `VERSION`.

For a fresh checkout, deploy the already published RCA artifacts from Hugging
Face. Only `oc` access and a published shared predictor image are needed:

```sh
TASK=classify SKIP_HF_UPLOAD=1 SKIP_BUILD=1 \
  IMAGE=image-registry.openshift-image-registry.svc:5000/model-serving/ran-ml-service@sha256:<digest> \
  ./model-serving/shared-ml-predictor/deploy/publish-and-deploy.sh

# After a compatible Hugging Face artifact refresh, reuse the image and URL.
TASK=classify SKIP_HF_UPLOAD=1 SKIP_BUILD=1 \
  IMAGE=<same-image-reference> RCA_ARTIFACT_COMMIT=<new-verified-commit> \
  ARTIFACT_REVISION=<new-revision> \
  ./model-serving/shared-ml-predictor/deploy/publish-and-deploy.sh

# Detect retains its defaults and its independent InferenceService.
TASK=detect SKIP_HF_UPLOAD=1 SKIP_BUILD=1 IMAGE=<detect-image-reference> \
  ./model-serving/shared-ml-predictor/deploy/publish-and-deploy.sh
```

Publishing new RCA artifacts is a separate action that requires `hf` write
credentials and local checkpoint/preprocessing paths. Set `SKIP_DEPLOY=1` and
omit `SKIP_HF_UPLOAD`; the command verifies both local hashes before uploading.
Record the final Hugging Face commit, verify both files at that commit, and
update parity CI and the InferenceService manifest before deploying it.

`STORAGE_URI`, `HF_REPO`, artifact paths, manifest paths, namespace, Service
name, Route name, and smoke fixture can be overridden through the command's
environment variables. When publishing, the command uploads the model card and,
when `ARTIFACT_REVISION` is set, `release.json`. For deployment, it checks KServe readiness and task identity
from the same-cluster Service, then smoke-tests `/v1/classify` through
both the same-cluster Service and external TLS Route. `RENDER_ONLY=1` prints the
manifests without publishing, building, or deploying. The refresh changes the
predictor environment to force a KServe revision even when the model bytes are
compatible. `ARTIFACT_REVISION` is only a rollout marker; it does not select
the artifact bytes. There is no automatic registry promotion.

For local serving, run `uv run --offline ran-ml-service` inside
`model-serving/shared-ml-predictor` with `TASK=classify` and `MANTIS_MODEL_PATH`
pointing to the local checkpoint beside `rca_preprocessing.json`. The backbone
must already be cached.

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
The parity workflow pins the final commit in its `RCA_ARTIFACT_COMMIT` setting.
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
