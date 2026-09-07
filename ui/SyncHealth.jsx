import { useState } from "react";

export function SyncHealth({ error, checkedAt, onRetry, loadDiagnostics }) {
  const [report, setReport] = useState(null), [failure, setFailure] = useState(""), [busy, setBusy] = useState(false);
  async function inspect() {
    setBusy(true); setFailure("");
    try { setReport(await loadDiagnostics()); }
    catch { setFailure("Support details could not load. Keep the launcher open and retry."); }
    finally { setBusy(false); }
  }
  return <section className="sync-health" aria-label="Shared data synchronization">
    <div role="status"><strong>{error ? "Automatic synchronization unavailable" : checkedAt ? "Shared workspace connected" : "Checking shared workspace…"}</strong>
      <span>{error ? "Displayed data may be stale. Saved data is retained; no automatic Axon retry will occur." : "This checks local changes, not Axon freshness."}</span>
      {checkedAt && <small>Last successful local check: {new Date(checkedAt).toLocaleTimeString()}</small>}
    </div>
    {error && <button type="button" onClick={onRetry}>Retry local connection</button>}
    <details><summary>Local support diagnostics</summary><p>No personnel records, credentials or URLs are collected. Details are kept only until this process exits.</p>
      <button type="button" disabled={busy} onClick={inspect}>{busy ? "Loading…" : "Load support details"}</button>
      {failure && <p role="alert">{failure}</p>}
      {report && <><p>{report.count} recent requests · {report.failed} error responses. {report.retention}</p>
        <div className="diagnostics-table"><table><caption>Latest 10 local requests</caption><thead><tr><th>Time</th><th>Request ID</th><th>Status</th><th>Duration (ms)</th></tr></thead>
          <tbody>{report.requests.slice(-10).reverse().map(row=><tr key={row.requestId}><td>{new Date(row.at).toLocaleTimeString()}</td><td>{row.requestId}</td><td>{row.status}</td><td>{row.durationMs}</td></tr>)}</tbody></table></div></>}
    </details>
  </section>;
}
