# Lightspeed Demo Recording Script

## Overview

This demo shows the **AI-Driven Network Remediation** system handling a novel failure
type that has no pre-built AAP playbook. Instead of using a known template, the system
automatically asks **Red Hat Ansible Lightspeed** (OLS) to generate a remediation
playbook on the fly, then notifies the team via Slack.

**Flow**: Kafka alert → Normalize → RAG retrieval → LLM Analysis (bypassed via override) →
Decision Engine routes to Lightspeed → OLS generates Ansible playbook (~12s) →
Slack notification → Audit record.

**Total demo duration**: ~90 seconds of recording.

---

## Pre-Recording Checklist

| Item | How to verify |
|------|---------------|
| Dashboard loads | Open `https://hub-frontend-hub-mtalvi.apps.ai-dev02.kni.syseng.devcluster.openshift.com` |
| Agent-service running | `oc get pod -l app.kubernetes.io/component=agent-service -n hub-mtalvi` shows Running |
| Slack channel ready | `#ai-driven-network` exists, bot is a member |
| Agent logs terminal ready | `oc logs -f deploy/hub-agent-service -n hub-mtalvi` running in a terminal |

**Before recording**: Just reload the browser (F5) on the dashboard. No rebuild needed —
all code changes are already deployed.

---

## Screen Layout for Recording

Arrange your screen with:
1. **Browser** (left ~60%) — Dashboard UI
2. **Terminal** (right top ~20%) — Agent-service logs (`oc logs -f deploy/hub-agent-service -n hub-mtalvi`)
3. **Slack** (right bottom ~20%) — `#ai-driven-network` channel visible

Alternatively, use two screens or toggle between tabs during recording.

---

## Step-by-Step Script

### Step 0 — Introduction (voiceover, 10 seconds)

**Show**: Dashboard in idle state (no active incidents).

**Say**:
> "This is the AI-Driven Network Remediation dashboard. We're about to trigger a
> novel failure scenario — a DNS failure at an edge site — where no pre-built AAP
> playbook exists. The system will automatically use Red Hat Ansible Lightspeed to
> generate a remediation playbook in real time."

---

### Step 1 — Trigger the Demo (5 seconds)

**Action**:
1. Scroll down to the **"Demo Mode"** panel
2. Click the **"Trigger Lightspeed Demo"** button

**Show**: The confirmation appears below the button showing:
- Incident ID
- Scenario: `lightspeed`
- Topic: `system-alerts`
- Kafka offset number

**Say**:
> "I'm triggering the Lightspeed demo scenario. This publishes a structured alert
> to Kafka with built-in routing overrides that guarantee the Lightspeed path."

---

### Step 2 — Watch Agent Logs (15–20 seconds)

**Action**: Switch focus to the agent-service log terminal.

**Wait**: Watch logs appear in real time. You'll see:

```
Kafka alert received topic=system-alerts ...
Invoking workflow for Kafka alert ...
Normalize node invoked
RAG retrieval node invoked
HTTP Request: GET .../v1/vector_stores ...
HTTP Request: POST .../vector_stores/.../search ...
Analyze node invoked
Decide node invoked
Lightspeed node invoked
OLS attachments count: 2
```

**Say** (as logs scroll):
> "The alert flows through the LangGraph pipeline: it's normalized, relevant runbook
> context is retrieved from the RAG vector store, then the analysis — here using
> deterministic overrides — identifies this as a DNS failure with high confidence.
> The decision engine sees this isn't a known playbook type and routes to Lightspeed."

---

### Step 3 — OLS Generates the Playbook (10–15 seconds)

**Action**: Continue watching logs. After ~12 seconds you'll see:

```
OLS responded in 12.XXs, conversation_id=...
Generated playbook 'remediate-dnsfailure-in-openshift-cluster':
---
- name: Remediate DNSFailure in OpenShift cluster
  hosts: all
  ...
```

Then:
```
LIGHTSPEED_SKIP_AAP=true, skipping AAP execution for 'remediate-dnsfailure-in-openshift-cluster'
```

**Say**:
> "Ansible Lightspeed analyzed the failure context — the namespace, pod name,
> failure type, and evidence — and generated a complete Ansible playbook in about
> 12 seconds. The playbook includes DNS operator checks, CoreDNS pod inspection,
> and resolution steps specific to our cluster."

---

### Step 4 — Slack Notification (5 seconds)

**Action**: Switch to Slack (`#ai-driven-network` channel).

**Show**: The bot message appears with:
- Header: `[MEDIUM] DNSFailure - dark-noc-edge/nginx-edge-lightspeed`
- Severity: MEDIUM
- Site: edge-01
- Status: Playbook Generated
- Resolution: "Lightspeed playbook generated: Generated playbook: remediate-dnsfailure-in-openshift-cluster"

**Say**:
> "The Slack notification confirms the playbook was generated successfully.
> The team sees the failure type, severity, affected pod, and the generated
> playbook name — all within seconds of the alert."

---

### Step 5 — Dashboard Update (5–10 seconds)

**Action**: Switch back to the browser dashboard.

**Show**: The dashboard has updated:
- **Incident Timeline** shows the new incident with "lightspeed" decision
- **SLO/Business Impact** panels reflect the new processed incident

**Say**:
> "Back on the dashboard, the incident timeline now shows the Lightspeed-handled
> incident. The audit trail confirms the full autonomous loop completed —
> from Kafka ingestion through playbook generation and notification."

---

### Step 6 — Wrap Up (10 seconds)

**Show**: Dashboard overview.

**Say**:
> "To summarize: when the system encounters a novel failure type without a
> pre-built remediation template, it leverages Ansible Lightspeed to generate
> a custom playbook in real time. Combined with the standard AAP path for known
> failures, this provides complete autonomous coverage across the edge fleet —
> no human intervention required."

---

## Timing Summary

| Step | Duration | Cumulative |
|------|----------|------------|
| 0. Introduction | 10s | 10s |
| 1. Trigger button | 5s | 15s |
| 2. Agent logs (pipeline) | 15–20s | 35s |
| 3. OLS generation | 10–15s | 50s |
| 4. Slack notification | 5s | 55s |
| 5. Dashboard update | 5–10s | 65s |
| 6. Wrap up | 10s | 75s |

**Total**: ~75–90 seconds.

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| OLS times out (60s) | Check NetworkPolicy: `oc get netpol -n openshift-lightspeed` — ensure `allow-hub-mtalvi-to-lightspeed` exists |
| Slack "not_in_channel" | Invite bot to channel: `/invite @for-telco-quickstart` in `#ai-driven-network` |
| Slack "missing_scope" | Bot needs `chat:write` scope — reinstall app in Slack settings |
| No logs appearing | Verify agent pod is running: `oc get pod -l app.kubernetes.io/component=agent-service -n hub-mtalvi` |
| Dashboard not updating | Reload page (F5); check chatbot-service pod is running |

---

## Key Differentiator from CrashLoop Demo

| Aspect | CrashLoop Demo | Lightspeed Demo |
|--------|---------------|-----------------|
| Failure type | CrashLoopBackOff (known) | DNSFailure (novel) |
| Decision | Remediate via AAP template | Generate playbook via Lightspeed |
| AAP interaction | Launches existing template | Skipped (playbook generated only) |
| Story | "Known failures resolved in seconds" | "Novel failures get AI-generated remediation" |
| Slack status | "Resolved" | "Playbook Generated" |
