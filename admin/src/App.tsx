import { useEffect, useState } from "react";
import { api, setApiKey, getApiKey, API_BASE } from "./api";

type Tab = "overview" | "usage" | "billing" | "keys" | "audit";

type KeyRow = {
  key_prefix: string;
  org_id: string;
  label: string;
  active: boolean;
  created_at?: string;
};

export default function App() {
  const [tab, setTab] = useState<Tab>("overview");
  const [apiKeyInput, setApiKeyInput] = useState(getApiKey());
  const [connected, setConnected] = useState(false);
  const [usage, setUsage] = useState<Record<string, unknown> | null>(null);
  const [subscription, setSubscription] = useState<Record<string, unknown> | null>(null);
  const [plans, setPlans] = useState<unknown[]>([]);
  const [audit, setAudit] = useState<unknown[]>([]);
  const [keys, setKeys] = useState<KeyRow[]>([]);
  const [error, setError] = useState("");
  const [newKeyLabel, setNewKeyLabel] = useState("admin-console");
  const [createdKey, setCreatedKey] = useState("");

  const refreshKeys = () => api<KeyRow[]>("/platform/api-keys").then(setKeys).catch(() => {});

  const connect = async () => {
    setApiKey(apiKeyInput);
    setError("");
    try {
      const u = await api<Record<string, unknown>>("/platform/usage");
      setUsage(u);
      setSubscription(await api("/billing/subscription"));
      setConnected(true);
    } catch (e) {
      setConnected(false);
      setError(String(e));
    }
  };

  useEffect(() => {
    if (connected) {
      api("/billing/plans").then(setPlans).catch(() => {});
      api("/platform/audit?limit=50").then(setAudit).catch(() => {});
      refreshKeys();
    }
  }, [connected, tab]);

  const checkout = async (planId: string) => {
    try {
      const res = await api<{ checkout_url: string }>("/billing/checkout", {
        method: "POST",
        body: JSON.stringify({ plan_id: planId }),
      });
      window.open(res.checkout_url, "_blank");
    } catch (e) {
      setError(String(e));
    }
  };

  const createKey = async () => {
    setError("");
    setCreatedKey("");
    try {
      const res = await api<{ api_key: string }>("/platform/api-keys", {
        method: "POST",
        body: JSON.stringify({ label: newKeyLabel }),
      });
      setCreatedKey(res.api_key);
      await refreshKeys();
    } catch (e) {
      setError(String(e));
    }
  };

  const revokeKey = async (keyPrefix: string) => {
    setError("");
    try {
      await api("/platform/api-keys", {
        method: "DELETE",
        body: JSON.stringify({ key_prefix: keyPrefix.replace("…", "") }),
      });
      await refreshKeys();
    } catch (e) {
      setError(String(e));
    }
  };

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="brand">
          <span className="logo">⚡</span>
          <div>
            <strong>Codebase Agent</strong>
            <small>Admin Console</small>
          </div>
        </div>
        <nav>
          {(["overview", "usage", "billing", "keys", "audit"] as Tab[]).map((t) => (
            <button key={t} className={tab === t ? "active" : ""} onClick={() => setTab(t)}>
              {t.charAt(0).toUpperCase() + t.slice(1)}
            </button>
          ))}
        </nav>
      </aside>
      <main>
        <header>
          <h1>{tab.charAt(0).toUpperCase() + tab.slice(1)}</h1>
          <div className="connect-bar">
            {!connected && (
              <>
                <input
                  type="password"
                  placeholder="API Key"
                  value={apiKeyInput}
                  onChange={(e) => setApiKeyInput(e.target.value)}
                />
                <button onClick={connect}>Connect</button>
              </>
            )}
            <a className="sso-link" href={`${API_BASE}/auth/login`}>
              Sign in with SSO
            </a>
          </div>
        </header>
        {error && <div className="error">{error}</div>}
        {connected && tab === "overview" && (
          <div className="grid">
            <Card title="Organization" value={String(usage?.org_id || "—")} />
            <Card title="Plan" value={String(subscription?.plan_name || subscription?.plan_id || "Free")} />
            <Card title="Chat this month" value={String((usage?.metrics as Record<string, number>)?.chat || 0)} />
            <Card title="Ingest this month" value={String((usage?.metrics as Record<string, number>)?.ingest || 0)} />
          </div>
        )}
        {connected && tab === "usage" && usage && (
          <pre className="json">{JSON.stringify(usage, null, 2)}</pre>
        )}
        {connected && tab === "billing" && (
          <div>
            <p>Current plan: <strong>{String(subscription?.plan_name || subscription?.plan_id)}</strong></p>
            <div className="plan-grid">
              {(plans as Record<string, unknown>[]).map((p) => (
                <div key={String(p.id)} className="plan-card">
                  <h3>{String(p.name)}</h3>
                  <p className="price">${String(p.price_monthly_usd)}/mo</p>
                  {p.id !== "free" && (
                    <button onClick={() => checkout(String(p.id))}>Upgrade</button>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
        {connected && tab === "keys" && (
          <div className="keys-panel">
            <div className="keys-create">
              <input
                placeholder="Key label"
                value={newKeyLabel}
                onChange={(e) => setNewKeyLabel(e.target.value)}
              />
              <button onClick={createKey}>Create API key</button>
            </div>
            {createdKey && (
              <div className="key-created">
                <strong>New key (copy now — shown once):</strong>
                <code>{createdKey}</code>
              </div>
            )}
            <table className="keys-table">
              <thead>
                <tr>
                  <th>Prefix</th>
                  <th>Label</th>
                  <th>Status</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {keys.map((k) => (
                  <tr key={k.key_prefix + k.label}>
                    <td><code>{k.key_prefix}</code></td>
                    <td>{k.label}</td>
                    <td>{k.active ? "active" : "revoked"}</td>
                    <td>
                      {k.active && (
                        <button className="danger" onClick={() => revokeKey(k.key_prefix)}>
                          Revoke
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {connected && tab === "audit" && (
          <pre className="json">{JSON.stringify(audit, null, 2)}</pre>
        )}
      </main>
    </div>
  );
}

function Card({ title, value }: { title: string; value: string }) {
  return (
    <div className="card">
      <span>{title}</span>
      <strong>{value}</strong>
    </div>
  );
}
