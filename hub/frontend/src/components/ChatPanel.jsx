import { useState } from "react";

const EXEC_HEADERS = ["Summary", "MCP Status", "Model Output", "Next Action"];

const QUICK_ASKS = [
  "Executive summary of current incident posture",
  "MCP health status across all integrations",
  "Current remediation status for edge-site-01",
  "Provide ticket and Slack notification trace status",
];

function parseExecutiveReply(text) {
  if (!text || typeof text !== "string") return null;
  const sections = [];
  let current = null;
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    if (!line) continue;
    const header = EXEC_HEADERS.find((h) => line === `${h}:`);
    if (header) {
      current = { title: header, lines: [] };
      sections.push(current);
      continue;
    }
    if (current) current.lines.push(line);
  }
  if (sections.length < 3) return null;
  return sections;
}

export function ChatPanel({ baseUrl }) {
  const [message, setMessage] = useState("");
  const [sessionId] = useState(() => `session-${Date.now()}`);
  const [messages, setMessages] = useState([
    {
      role: "assistant",
      text: "NOC Chat online. Ask about model runtime, MCP agents, incidents, or remediation workflows.",
    },
  ]);
  const [meta, setMeta] = useState(null);
  const [brief, setBrief] = useState(null);
  const [loading, setLoading] = useState(false);

  async function sendMessage(outgoing, asBrief = false) {
    if (!outgoing.trim() || loading) return;
    setMessages((prev) => [...prev, { role: "user", text: outgoing }]);
    setMessage("");
    setLoading(true);
    try {
      const url = baseUrl ? `${baseUrl}/api/chat` : "/api/chat";
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: outgoing, session_id: sessionId }),
      });
      if (!res.ok) {
        throw new Error(`Chat request failed (${res.status})`);
      }
      const contentType = res.headers.get("content-type") || "";
      if (!contentType.includes("application/json")) {
        throw new Error(`Non-JSON response (${res.status})`);
      }
      const data = await res.json();
      const chatDeps = data._deps || { status: "ok" };
      const degradedNote =
        chatDeps.status === "degraded"
          ? ` [⚠ Partial — ${(chatDeps.unavailable || []).join(", ")} unavailable]`
          : "";
      setMessages((prev) => [
        ...prev,
        { role: "assistant", text: (data.reply || "No response") + degradedNote, brief: asBrief },
      ]);

      const model = data.model || {};
      const context = data.context || {};
      setMeta({
        modelName: model.name || "n/a",
        modelSource: model.source || "unknown",
        modelFramework: model.framework || "n/a",
        integrationsUp: context.integrations_up || 0,
        integrationsTotal: context.integrations_total || 0,
        openIncidents: context.open_incidents || 0,
        mcpStatus: data.mcp_status || [],
        degraded: chatDeps.status === "degraded",
      });

      if (asBrief) {
        setBrief({
          title: `Executive Incident Brief · ${new Date().toLocaleTimeString()}`,
          body: data.reply || "No response",
          model: model.name || "n/a",
          source: model.source || "unknown",
          framework: model.framework || "n/a",
          incidents: context.open_incidents || 0,
          up: context.integrations_up || 0,
          total: context.integrations_total || 0,
        });
      }
    } catch (err) {
      const detail = err?.message || "Chatbot endpoint unreachable.";
      setMessages((prev) => [...prev, { role: "assistant", text: detail }]);
    } finally {
      setLoading(false);
    }
  }

  async function submit(e) {
    e.preventDefault();
    await sendMessage(message.trim(), false);
  }

  async function runQuickAsk(prompt) {
    await sendMessage(prompt, false);
  }

  async function generateExecutiveBrief() {
    const prompt =
      "Generate executive incident brief with Summary, MCP Status, Model Output, and Next Action sections.";
    await sendMessage(prompt, true);
  }

  return (
    <section className="panel">
      <h2>NOC Chat</h2>
      <div className="quick-asks">
        {QUICK_ASKS.map((ask) => (
          <button
            key={ask}
            type="button"
            onClick={() => runQuickAsk(ask)}
            disabled={loading}
            className="quick-ask-btn"
          >
            {ask}
          </button>
        ))}
        <button
          type="button"
          onClick={generateExecutiveBrief}
          disabled={loading}
          className="quick-ask-btn brief"
        >
          Generate Executive Incident Brief
        </button>
      </div>
      <form onSubmit={submit} className="chat">
        <input
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder="Ask about incidents, MCP status, or remediation flow"
        />
        <button type="submit" disabled={loading}>
          {loading ? "Sending..." : "Send"}
        </button>
      </form>
      <div className="chat-log">
        {messages.map((item, idx) => {
          const parsed =
            item.role === "assistant" && item.brief
              ? parseExecutiveReply(item.text)
              : null;
          return (
            <article
              key={`${item.role}-${idx}`}
              className={`bubble ${item.role}`}
            >
              <strong>{item.role === "user" ? "You" : "NOC Agent"}</strong>
              {parsed ? (
                <div className="exec-reply">
                  {parsed.map((section) => (
                    <section key={section.title} className="exec-section">
                      <h4>{section.title}</h4>
                      <ul>
                        {(section.lines || []).map((line, lineIdx) => (
                          <li key={`${section.title}-${lineIdx}`}>{line}</li>
                        ))}
                      </ul>
                    </section>
                  ))}
                </div>
              ) : (
                <p>{item.text}</p>
              )}
            </article>
          );
        })}
      </div>
      {meta && (
        <div className="chat-meta">
          <p>
            Model: <strong>{meta.modelName}</strong> ({meta.modelSource},{" "}
            {meta.modelFramework}) · MCP up:{" "}
            <strong>
              {meta.integrationsUp}/{meta.integrationsTotal}
            </strong>{" "}
            · Open incidents: <strong>{meta.openIncidents}</strong>
          </p>
          {meta.mcpStatus.length > 0 && (
            <div className="mcp-list">
              {meta.mcpStatus.map((mcp) => (
                <span
                  key={mcp.id || mcp.name}
                  className={`pill ${mcp.status === "up" ? "up" : "down"}`}
                >
                  {mcp.name}: {mcp.status}
                </span>
              ))}
            </div>
          )}
        </div>
      )}
      {brief && (
        <div className="brief-card">
          <h3>{brief.title}</h3>
          <p className="brief-meta">
            Model: <strong>{brief.model}</strong> ({brief.source},{" "}
            {brief.framework}) · Integrations:{" "}
            <strong>
              {brief.up}/{brief.total}
            </strong>{" "}
            · Open incidents: <strong>{brief.incidents}</strong>
          </p>
          {parseExecutiveReply(brief.body) ? (
            <div className="exec-reply">
              {parseExecutiveReply(brief.body).map((section) => (
                <section
                  key={`brief-${section.title}`}
                  className="exec-section"
                >
                  <h4>{section.title}</h4>
                  <ul>
                    {section.lines.map((line, lineIdx) => (
                      <li key={`brief-${section.title}-${lineIdx}`}>{line}</li>
                    ))}
                  </ul>
                </section>
              ))}
            </div>
          ) : (
            <p>{brief.body}</p>
          )}
        </div>
      )}
    </section>
  );
}
