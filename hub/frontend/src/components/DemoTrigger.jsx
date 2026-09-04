import { useState } from "react";

const SCENARIOS = [
  { id: "crashloop", label: "Trigger CrashLoop Demo" },
  { id: "oom", label: "Trigger OOM Demo" },
  { id: "lightspeed", label: "Trigger Lightspeed Demo" },
  { id: "escalation", label: "Trigger Escalation Demo" },
];

export function DemoTrigger({ baseUrl }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);

  async function trigger(scenario) {
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const url = baseUrl
        ? `${baseUrl}/api/demo/trigger`
        : "/api/demo/trigger";
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scenario, site: "edge-site-01" }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(
          body.detail || body.message || `Demo trigger failed (${res.status})`
        );
      }
      const data = await res.json();
      setResult(data);
    } catch (err) {
      setError(err.message || "Demo trigger failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="panel">
      <h2>Demo Mode</h2>
      <p className="meta">
        Run a controlled E2E simulation and follow results across AAP,
        ServiceNow, Slack, and Langfuse.
      </p>
      <div className="demo-actions">
        {SCENARIOS.map((s) => (
          <button
            key={s.id}
            disabled={loading}
            onClick={() => trigger(s.id)}
          >
            {s.label}
          </button>
        ))}
      </div>
      {error && <p className="demo-error">{error}</p>}
      {result && (
        <div className="demo-result">
          <p>
            <strong>Incident ID:</strong>{" "}
            <code>{result.incident_id || "n/a"}</code>
          </p>
          <p>
            <strong>Scenario:</strong> <code>{result.scenario}</code> · Topic:{" "}
            <code>{result.topic}</code> · Offset:{" "}
            <code>{result.kafka_offset}</code>
          </p>
          {result.event_message && (
            <p>
              <strong>Event:</strong> {result.event_message}
            </p>
          )}
        </div>
      )}
    </section>
  );
}
