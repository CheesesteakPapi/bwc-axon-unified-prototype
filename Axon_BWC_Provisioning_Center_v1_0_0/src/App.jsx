import { useEffect, useMemo, useState } from "react";
import { localApi } from "./api.js";

const STEPS = ["Add Users", "Review Exceptions", "Preview Changes", "Submit", "Track Results"];
const ASSIGNMENT_FIELDS = [
  ["role", "Role"],
  ["groupName", "Group"],
  ["location", "Location"],
  ["personnelAor", "Personnel AOR"],
  ["jobCategory", "Job category"],
  ["supervisorEmail", "Supervisor email"],
  ["supervisorUpn", "Supervisor UPN"],
];

function stepForRun(run) {
  if (!run) return 0;
  if (run.status === "Needs Review") return 1;
  if (["Ready for Preview", "Previewed"].includes(run.status)) return 2;
  if (run.status === "Awaiting Submission") return 3;
  return 4;
}

function formatTime(value) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function IntakeGrid({ rows, setRows, disabled }) {
  function update(index, key, value) {
    setRows((current) => current.map((row, rowIndex) => (rowIndex === index ? { ...row, [key]: value } : row)));
  }
  return <div className="intake-grid-wrap">
    <table className="intake-grid">
      <thead><tr><th>#</th><th>Email <span>required</span></th><th>Role <span>required</span></th><th>Group Name <span>optional override</span></th><th /></tr></thead>
      <tbody>{rows.map((row, index) => <tr key={row.id}>
        <td>{index + 1}</td>
        <td><input aria-label={`Email row ${index + 1}`} value={row.Email} onChange={(event) => update(index, "Email", event.target.value)} disabled={disabled} /></td>
        <td><input aria-label={`Role row ${index + 1}`} value={row.Role} onChange={(event) => update(index, "Role", event.target.value)} disabled={disabled} /></td>
        <td><input aria-label={`Group Name row ${index + 1}`} value={row["Group Name"]} onChange={(event) => update(index, "Group Name", event.target.value)} disabled={disabled} /></td>
        <td><button className="icon-button" type="button" onClick={() => setRows((current) => current.filter((_, rowIndex) => rowIndex !== index))} disabled={disabled || rows.length === 1} aria-label={`Remove row ${index + 1}`}>×</button></td>
      </tr>)}</tbody>
    </table>
    <button className="secondary" type="button" onClick={() => setRows((current) => [...current, { id: crypto.randomUUID(), Email: "", Role: "", "Group Name": "" }])} disabled={disabled}>+ Add row</button>
  </div>;
}

function ColumnMapper({ detection, mapping, setMapping }) {
  if (!detection?.needsMapper) return null;
  return <section className="callout warning">
    <h3>Confirm intake columns</h3>
    <p>The file headers are flexible, but Email and Role must resolve unambiguously.</p>
    <div className="mapper-grid">{[["email", "Email"], ["role", "Role"], ["groupName", "Group Name"]].map(([key, label]) => <label key={key}><span>{label}{key !== "groupName" && " *"}</span><select value={mapping[key] || detection.mapping?.[key] || ""} onChange={(event) => setMapping((current) => ({ ...current, [key]: event.target.value }))}><option value="">Not mapped</option>{detection.headers.map((header) => <option key={header}>{header}</option>)}</select></label>)}</div>
  </section>;
}

function SummaryCards({ validation }) {
  const cards = [
    ["New", validation?.createCount || 0, "blue"],
    ["Existing updates", validation?.updateCount || 0, "purple"],
    ["Unchanged", validation?.unchangedCount || 0, "neutral"],
    ["Blocked", validation?.blockerCount || 0, validation?.blockerCount ? "red" : "green"],
  ];
  return <div className="summary-cards">{cards.map(([label, value, tone]) => <article className={`metric ${tone}`} key={label}><span>{label}</span><strong>{value.toLocaleString()}</strong></article>)}</div>;
}

function AssignmentTable({ run, onlyExceptions = false, drafts, setDrafts, selected, setSelected }) {
  const rows = onlyExceptions ? run.rows.filter((row) => row.validationState === "Blocked") : run.rows;
  function update(rowId, field, value) {
    setDrafts((current) => ({ ...current, [rowId]: { ...(current[rowId] || {}), [field]: value } }));
  }
  return <div className="table-scroll"><table className="review-table">
    <thead><tr><th><span className="sr-only">Select</span></th><th>User / source identity</th><th>Validation</th>{ASSIGNMENT_FIELDS.map(([, label]) => <th key={label}>{label}</th>)}</tr></thead>
    <tbody>{rows.map((row) => <tr key={row.rowId} className={row.validationState === "Blocked" ? "blocked-row" : "ready-row"}>
      <td><input type="checkbox" aria-label={`Select ${row.email}`} checked={selected.has(row.rowId)} onChange={(event) => setSelected((current) => { const next = new Set(current); if (event.target.checked) next.add(row.rowId); else next.delete(row.rowId); return next; })} /></td>
      <td className="identity-cell"><strong>{row.firstName} {row.lastName}</strong><span>Email: {row.email}</span><small>UPN: {row.upn || "missing"} · External ID: {row.externalId || "missing"}</small><small>Badge / UserName: {row.badgeNumber || "missing"} · {row.username || "missing"}</small><small>{row.directoryAccountStatus} · {row.component || "No component"} · {row.jobTitle || "No job title"}</small></td>
      <td><span className={`status ${row.validationState === "Blocked" ? "bad" : "good"}`}>{row.validationState}</span>{row.blockers?.map((item) => <small className="blocker" key={item}>{item}</small>)}</td>
      {ASSIGNMENT_FIELDS.map(([field]) => <td key={field}><input aria-label={`${field} for ${row.email}`} value={drafts[row.rowId]?.[field] ?? row[field] ?? ""} onChange={(event) => update(row.rowId, field, event.target.value)} /></td>)}
    </tr>)}</tbody>
  </table>{!rows.length && <div className="empty-state">No records in this view.</div>}</div>;
}

function History({ run }) {
  return <details className="history"><summary>Revision history ({run.history?.length || 0})</summary><ol>{run.history?.map((item) => <li key={item.revision}><strong>Revision {item.revision}</strong> · {item.event}<span>{item.reason} · {formatTime(item.createdAt)}</span></li>)}</ol></details>;
}

function ConnectionPanel({ config, session, onSaved }) {
  const [values, setValues] = useState({ agencyBaseUrl: config.agencyBaseUrl || "", timeoutSeconds: config.timeoutSeconds || 90, writeOperationsEnabled: config.writeOperationsEnabled || false, groupFileFieldConfirmed: config.groupFileFieldConfirmed || false, partnerId: "", clientId: "", clientSecret: "" });
  const [busy, setBusy] = useState(false);
  useEffect(() => setValues((current) => ({ ...current, agencyBaseUrl: config.agencyBaseUrl || "", timeoutSeconds: config.timeoutSeconds || 90, writeOperationsEnabled: config.writeOperationsEnabled || false, groupFileFieldConfirmed: config.groupFileFieldConfirmed || false })), [config]);
  async function save() {
    setBusy(true);
    try {
      const savedConfig = await localApi.saveConfig(values);
      let savedSession = session;
      if (values.partnerId || values.clientId || values.clientSecret) savedSession = await localApi.saveCredentials(values);
      onSaved(savedConfig, savedSession);
      setValues((current) => ({ ...current, partnerId: "", clientId: "", clientSecret: "" }));
    } finally { setBusy(false); }
  }
  return <details className="connection-panel"><summary><span className={`dot ${session.configured ? "on" : ""}`} /> Axon connection · {session.configured ? `active ${session.partnerHint}` : "not configured"}</summary><div className="connection-grid">
    <label><span>Tenant HTTPS URL</span><input value={values.agencyBaseUrl} onChange={(event) => setValues({ ...values, agencyBaseUrl: event.target.value })} placeholder="https://your-tenant.evidence.com" /></label>
    <label><span>Partner / Agency ID</span><input value={values.partnerId} onChange={(event) => setValues({ ...values, partnerId: event.target.value })} /></label>
    <label><span>Client ID</span><input value={values.clientId} onChange={(event) => setValues({ ...values, clientId: event.target.value })} /></label>
    <label><span>Client secret</span><input type="password" value={values.clientSecret} onChange={(event) => setValues({ ...values, clientSecret: event.target.value })} /></label>
    <label className="check"><input type="checkbox" checked={values.writeOperationsEnabled} onChange={(event) => setValues({ ...values, writeOperationsEnabled: event.target.checked })} /><span>Enable deliberate Axon write operations</span></label>
    <label className="check"><input type="checkbox" checked={values.groupFileFieldConfirmed} onChange={(event) => setValues({ ...values, groupFileFieldConfirmed: event.target.checked })} /><span>Authorized Group import field confirmed</span></label>
    <button className="secondary" type="button" disabled={busy} onClick={save}>{busy ? "Saving…" : "Save local connection"}</button>
  </div><p className="muted">Credentials remain in this Python process and are never written to the shared workspace.</p></details>;
}

function RefreshPanel({ config, session, workspace, job, form, setForm, onStart, onCancel, onConnection }) {
  const running = job?.status === "running";
  return <details className="refresh-panel">
    <summary>Shared Axon snapshots <span>{workspace.snapshots?.length || 0} active scope(s)</span></summary>
    <p>Refresh here or in Geographic Operations. A shared lease prevents duplicate resource pulls, and activation occurs only after a complete validated result.</p>
    <div className="refresh-grid">
      <label><span>Resource</span><select value={form.resource} onChange={(event) => setForm({ ...form, resource: event.target.value })} disabled={running}>{["Users", "Groups", "Devices", "DeviceHomes"].map((value) => <option key={value}>{value}</option>)}</select></label>
      {form.resource === "Devices" && <><label><span>Model string(s)</span><input value={form.model} onChange={(event) => setForm({ ...form, model: event.target.value })} placeholder="Single model or comma-separated" disabled={running} /></label><label><span>Device status</span><input value={form.status2} onChange={(event) => setForm({ ...form, status2: event.target.value })} placeholder="Exact status2 value" disabled={running} /></label><label><span>Device Home ID</span><input value={form.homeId} onChange={(event) => setForm({ ...form, homeId: event.target.value })} placeholder="Exact home ID" disabled={running} /></label></>}
    </div>
    <div className="snapshot-list">{workspace.snapshots?.map((snapshot) => <span key={snapshot.snapshotId}><strong>{snapshot.resource}</strong> · {snapshot.scope?.type || "unknown"} · {snapshot.rowCount.toLocaleString()} rows · {formatTime(snapshot.activatedAt)}</span>)}</div>
    {job && <div className={`refresh-state ${job.status}`}><strong>{job.resource} · {job.status}</strong><span>{job.message}</span>{job.scope?.type === "filtered" && <small>Filtered Devices data remains separate from the full baseline.</small>}</div>}
    <div className="action-row"><button className="primary" type="button" onClick={onStart} disabled={running || !session.configured}>{running ? "Refreshing…" : `Refresh ${form.resource}`}</button>{running && <button className="secondary" type="button" onClick={onCancel}>Cancel safely</button>}<span>{session.configured ? "Credentials are available in this process only." : "Open Axon connection below before refreshing."}</span></div>
    <ConnectionPanel config={config} session={session} onSaved={onConnection} />
  </details>;
}

export function App() {
  const [run, setRun] = useState(null);
  const [workspace, setWorkspace] = useState({ workspaceRevision: 0, snapshots: [], pendingCounts: {} });
  const [session, setSession] = useState({ configured: false, partnerHint: "" });
  const [config, setConfig] = useState({ agencyBaseUrl: "", timeoutSeconds: 90, writeOperationsEnabled: false, groupFileFieldConfirmed: false });
  const [step, setStep] = useState(0);
  const [rows, setRows] = useState([{ id: crypto.randomUUID(), Email: "", Role: "", "Group Name": "" }]);
  const [intakeFile, setIntakeFile] = useState(null);
  const [directoryFile, setDirectoryFile] = useState(null);
  const [provider, setProvider] = useState("directory-file");
  const [entraToken, setEntraToken] = useState("");
  const [detection, setDetection] = useState(null);
  const [columnMapping, setColumnMapping] = useState({});
  const [drafts, setDrafts] = useState({});
  const [selected, setSelected] = useState(new Set());
  const [changeReason, setChangeReason] = useState("");
  const [bulkField, setBulkField] = useState("role");
  const [bulkValue, setBulkValue] = useState("");
  const [existingReviewOpen, setExistingReviewOpen] = useState(false);
  const [confirmAgency, setConfirmAgency] = useState("");
  const [refreshForm, setRefreshForm] = useState({ resource: "Users", model: "", status2: "", homeId: "" });
  const [refreshJob, setRefreshJob] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const activeStep = run ? stepForRun(run) : step;
  const changedRows = useMemo(() => Object.entries(drafts).filter(([, changes]) => Object.keys(changes).length), [drafts]);

  useEffect(() => {
    Promise.all([localApi.workspace(), localApi.latestRun(), localApi.session(), localApi.config()]).then(([workspaceData, runData, sessionData, configData]) => {
      setWorkspace(workspaceData); setRun(runData.run); setSession(sessionData); setConfig(configData);
      if (runData.run) setStep(stepForRun(runData.run));
    }).catch((requestError) => setError(requestError.message));
  }, []);

  useEffect(() => {
    const timer = window.setInterval(async () => {
      try {
        const next = await localApi.workspace();
        if (next.workspaceRevision !== workspace.workspaceRevision) {
          setWorkspace(next);
          if (run?.runId && !changedRows.length) {
            const refreshed = await localApi.getRun(run.runId);
            setRun(refreshed.run);
          }
        }
      } catch { /* transient local poll failures surface on the next user action */ }
    }, 4000);
    return () => window.clearInterval(timer);
  }, [workspace.workspaceRevision, run?.runId, changedRows.length]);

  useEffect(() => {
    if (!refreshJob?.jobId || refreshJob.status !== "running") return undefined;
    const timer = window.setInterval(async () => {
      try {
        const result = await localApi.refreshStatus(refreshJob.jobId);
        setRefreshJob(result.job);
        if (result.job.status !== "running") {
          setWorkspace(await localApi.workspace());
          setMessage(result.job.message);
        }
      } catch (requestError) { setError(requestError.message); }
    }, 1000);
    return () => window.clearInterval(timer);
  }, [refreshJob?.jobId, refreshJob?.status]);

  async function startRefresh() {
    setError(""); setMessage("");
    try {
      const result = await localApi.startRefresh({ resource: refreshForm.resource, filters: { model: refreshForm.model, status2: refreshForm.status2, homeId: refreshForm.homeId } });
      setRefreshJob(result.job);
    } catch (requestError) { setError(requestError.message); }
  }

  async function cancelRefresh() {
    try { const result = await localApi.cancelRefresh(refreshJob.jobId); setRefreshJob(result.job); }
    catch (requestError) { setError(requestError.message); }
  }

  async function chooseIntakeFile(file) {
    setBusy(true); setError("");
    try {
      const uploaded = await localApi.uploadFile(file);
      setIntakeFile(uploaded);
      const detected = await localApi.detectIntake(uploaded.handle);
      setDetection(detected);
      setColumnMapping(detected.mapping || {});
      setMessage(`${file.name} is ready. The original file has not been changed.`);
    } catch (requestError) { setError(requestError.message); }
    finally { setBusy(false); }
  }

  async function chooseDirectoryFile(file) {
    setBusy(true); setError("");
    try { setDirectoryFile(await localApi.uploadFile(file)); setMessage(`${file.name} will be used only for directory enrichment.`); }
    catch (requestError) { setError(requestError.message); }
    finally { setBusy(false); }
  }

  async function startRun() {
    setBusy(true); setError(""); setMessage("Normalizing, enriching, mapping, generating, and validating…");
    try {
      const payload = {
        title: "BWC provisioning run",
        rows: intakeFile ? undefined : rows.filter((row) => row.Email || row.Role || row["Group Name"]),
        fileHandle: intakeFile?.handle,
        columnMapping,
        provider,
        directoryFileHandle: directoryFile?.handle,
        entraAccessToken: provider === "entra-delegated" ? entraToken : "",
      };
      const result = await localApi.createRun(payload);
      if (result.run?.needsColumnMapping) {
        setDetection(result.run); setStep(0); setMessage("Confirm the file column mapping, then run enrichment again.");
      } else {
        setRun(result.run); setStep(stepForRun(result.run)); setDrafts({}); setSelected(new Set()); setMessage(result.run.validation.valid ? "Enrichment and validation passed. Preview is ready." : "Enrichment finished with exceptions requiring review.");
        setWorkspace(await localApi.workspace());
      }
    } catch (requestError) { setError(requestError.message); }
    finally { setBusy(false); setEntraToken(""); }
  }

  async function saveEdits(extraEdits = []) {
    const edits = [...changedRows.map(([rowId, changes]) => ({ rowId, changes })), ...extraEdits];
    if (!edits.length) { setError("Change at least one assignment field first."); return; }
    setBusy(true); setError("");
    try {
      const result = await localApi.editRun(run.runId, { expectedRevision: run.revision, edits, reason: changeReason });
      setRun(result.run); setStep(stepForRun(result.run)); setDrafts({}); setSelected(new Set()); setBulkValue(""); setExistingReviewOpen(false); setMessage("Revision saved. Dependencies, strict records, validation, and chunks were regenerated automatically.");
      setWorkspace(await localApi.workspace());
    } catch (requestError) { setError(requestError.message); }
    finally { setBusy(false); }
  }

  function applyBulk() {
    if (!selected.size || !bulkValue.trim()) { setError("Select at least one user and enter a bulk value."); return; }
    saveEdits([...selected].map((rowId) => ({ rowId, changes: { [bulkField]: bulkValue } })));
  }

  async function approve() {
    setBusy(true); setError("");
    try {
      const count = run.validation.updateCount || 0;
      const result = await localApi.approveRun(run.runId, { expectedRevision: run.revision, approveUpdates: count > 0, updateCount: count });
      setRun(result.run); setStep(3); setMessage(result.message);
    } catch (requestError) { setError(requestError.message); }
    finally { setBusy(false); }
  }

  async function submitNext() {
    setBusy(true); setError("");
    try {
      const result = await localApi.submitNext(run.runId, { expectedRevision: run.revision, confirmWrite: true, confirmAgency });
      setRun(result.run); setStep(4); setConfirmAgency(""); setMessage(`Submitted ${result.submittedChunk} once. Axon job ${result.axonJobId} is now being tracked.`);
    } catch (requestError) { setError(requestError.message); }
    finally { setBusy(false); }
  }

  async function track() {
    setBusy(true); setError("");
    try {
      const result = await localApi.trackRun(run.runId, run.revision);
      setRun(result.run); setMessage(result.checked.length ? `Checked ${result.checked.length} Axon job(s).` : "No submitted jobs currently require a status check.");
    } catch (requestError) { setError(requestError.message); }
    finally { setBusy(false); }
  }

  async function exportPackage() {
    setBusy(true); setError("");
    try {
      const result = await localApi.exportRun(run.runId, run.revision);
      const anchor = document.createElement("a"); anchor.href = result.download.url; anchor.download = result.download.name; anchor.click();
      setMessage("One governed run package was exported. It is not intended for re-upload into this workflow.");
    } catch (requestError) { setError(requestError.message); }
    finally { setBusy(false); }
  }

  function newRun() {
    setRun(null); setStep(0); setRows([{ id: crypto.randomUUID(), Email: "", Role: "", "Group Name": "" }]); setIntakeFile(null); setDirectoryFile(null); setDetection(null); setColumnMapping({}); setDrafts({}); setSelected(new Set()); setError(""); setMessage("");
  }

  return <div className="app">
    <header className="topbar"><div><div className="eyebrow">ICE · Body-Worn Camera Program</div><h1>Axon Provisioning Center</h1></div><div className="release-label"><strong>Prototype · V3.1.0</strong><span>Python/PowerShell source execution</span><small>Not a signed production desktop release</small></div></header>
    <div className="workspace-strip"><span>Shared workspace revision <strong>{workspace.workspaceRevision}</strong></span><span>{workspace.snapshots?.length || 0} active resource scope(s)</span><span>{Object.values(workspace.pendingCounts || {}).reduce((sum, value) => sum + value, 0)} pending overlays</span><span>Credentials are not shared</span></div>
    <main>
      <RefreshPanel config={config} session={session} workspace={workspace} job={refreshJob} form={refreshForm} setForm={setRefreshForm} onStart={startRefresh} onCancel={cancelRefresh} onConnection={(nextConfig, nextSession) => { setConfig(nextConfig); setSession(nextSession); setMessage("Connection settings saved. Credentials remain in process memory."); }} />
      <nav className="stepper" aria-label="Provisioning progress">{STEPS.map((label, index) => <button key={label} type="button" className={`${index === activeStep ? "active" : ""} ${index < activeStep ? "complete" : ""}`} onClick={() => { if (!run && index > 0) return; setStep(index); }} disabled={!run && index > 0}><span>{index < activeStep ? "✓" : index + 1}</span>{label}</button>)}</nav>
      {message && <div className="banner success" role="status">{message}<button type="button" onClick={() => setMessage("")}>×</button></div>}
      {error && <div className="banner error" role="alert">{error}<button type="button" onClick={() => setError("")}>×</button></div>}

      {step === 0 && <section className="panel">
        <div className="panel-heading"><div><span className="kicker">Step 1</span><h2>Add users</h2><p>Start with Email and Role. Group Name is an optional friendly override; external Group IDs are resolved internally.</p></div>{run && <button className="secondary" type="button" onClick={newRun}>Start another run</button>}</div>
        <div className="intake-choice"><div className={!intakeFile ? "choice active" : "choice"}><h3>Paste or type users</h3><p>Paste rows from Excel or add them in the grid.</p></div><label className={intakeFile ? "choice active upload" : "choice upload"}><h3>Upload users</h3><p>Flexible CSV or XLSX headers are accepted.</p><input type="file" accept=".csv,.xlsx" onChange={(event) => event.target.files?.[0] && chooseIntakeFile(event.target.files[0])} /><span>{intakeFile ? `${intakeFile.name} · ${intakeFile.detail}` : "Choose .csv or .xlsx"}</span></label></div>
        {intakeFile && <button className="text-button" type="button" onClick={() => { setIntakeFile(null); setDetection(null); }}>Use paste grid instead</button>}
        {!intakeFile && <IntakeGrid rows={rows} setRows={setRows} disabled={busy} />}
        <ColumnMapper detection={detection} mapping={columnMapping} setMapping={setColumnMapping} />
        <div className="provider-box"><h3>Directory enrichment source</h3><div className="provider-options">
          <label><input type="radio" name="provider" checked={provider === "directory-file"} onChange={() => setProvider("directory-file")} /> Directory CSV/XLSX export</label>
          <label><input type="radio" name="provider" checked={provider === "sharepoint-export"} onChange={() => setProvider("sharepoint-export")} /> SharePoint / Power Automate export</label>
          <label><input type="radio" name="provider" checked={provider === "entra-delegated"} onChange={() => setProvider("entra-delegated")} /> Live Entra delegated read</label>
          <label><input type="radio" name="provider" checked={provider === "synthetic-test"} onChange={() => setProvider("synthetic-test")} /> Synthetic test records</label>
        </div>{["directory-file", "sharepoint-export"].includes(provider) && <label className="file-row"><span>Directory export file</span><input type="file" accept=".csv,.xlsx" onChange={(event) => event.target.files?.[0] && chooseDirectoryFile(event.target.files[0])} /><small>{directoryFile?.name || "Select an approved minimum-necessary export. If omitted, intake metadata is used."}</small></label>}
        {provider === "entra-delegated" && <label className="file-row"><span>Delegated Graph access token</span><input type="password" value={entraToken} onChange={(event) => setEntraToken(event.target.value)} autoComplete="off" /><small>Used in memory only. The provider resolves exact Entra mail matches, preserves UPN separately, and never requests Entra group membership.</small></label>}</div>
        <div className="action-row"><button className="primary" type="button" disabled={busy} onClick={startRun}>{busy ? "Working…" : "Enrich and continue"}</button><span>Normalize → exact directory match → map → generate → validate</span></div>
      </section>}

      {step === 1 && run && <section className="panel wide-panel"><div className="panel-heading"><div><span className="kicker">Step 2</span><h2>Review exceptions</h2><p>Identity values remain read-only. Correct source identity through reconciliation; edit only governed assignment fields here.</p></div><button className="secondary" type="button" onClick={() => setStep(0)}>Return to intake</button></div><SummaryCards validation={run.validation} />
        <div className="bulk-bar"><strong>Bulk edit {selected.size} selected</strong><select value={bulkField} onChange={(event) => setBulkField(event.target.value)}>{ASSIGNMENT_FIELDS.map(([key, label]) => <option value={key} key={key}>{label}</option>)}</select><input value={bulkValue} onChange={(event) => setBulkValue(event.target.value)} placeholder="New governed value" /><input value={changeReason} onChange={(event) => setChangeReason(event.target.value)} placeholder="Required shared change reason" /><button className="secondary" type="button" onClick={applyBulk} disabled={busy}>Apply and revalidate</button></div>
        <AssignmentTable run={run} onlyExceptions drafts={drafts} setDrafts={setDrafts} selected={selected} setSelected={setSelected} />
        <div className="action-row"><button className="primary" type="button" onClick={() => saveEdits()} disabled={busy || !changedRows.length}>{busy ? "Saving revision…" : `Save ${changedRows.length} edited row(s)`}</button>{run.validation.valid && <button className="secondary" type="button" onClick={() => setStep(2)}>Continue to preview</button>}<input className="reason" value={changeReason} onChange={(event) => setChangeReason(event.target.value)} placeholder="Required change reason" /></div><History run={run} />
      </section>}

      {step === 2 && run && <section className="panel wide-panel"><div className="panel-heading"><div><span className="kicker">Step 3</span><h2>Preview changes</h2><p>Review current Axon values against the proposed run. Saving any edit creates a new revision and clears prior approval.</p></div><button className="secondary" type="button" onClick={exportPackage}>Export optional review package</button></div><SummaryCards validation={run.validation} />
        {run.validation.blockerCount > 0 && <div className="callout danger"><strong>{run.validation.blockerCount} blocker(s) remain.</strong><button className="text-button" type="button" onClick={() => setStep(1)}>Review exceptions</button></div>}
        <div className="bulk-bar"><strong>Assignment-only edits</strong><span>{changedRows.length} row(s) changed</span><input value={changeReason} onChange={(event) => setChangeReason(event.target.value)} placeholder="Required change reason" /><button className="secondary" type="button" onClick={() => saveEdits()} disabled={busy || !changedRows.length}>Save revision</button></div>
        <AssignmentTable run={run} drafts={drafts} setDrafts={setDrafts} selected={selected} setSelected={setSelected} />
        {run.validation.updateCount > 0 && <section className="account-review"><div><h3>{run.validation.updateCount} existing account update(s)</h3><p>Open the field-level review before approval. Approval is bound to this run revision and does not submit to Axon.</p></div><button className="secondary" type="button" onClick={() => setExistingReviewOpen((current) => !current)}>{existingReviewOpen ? "Close account review" : "Open existing-account review"}</button>{existingReviewOpen && <div className="difference-list">{run.rows.filter((row) => row.existingAccount && row.differences?.length).map((row) => <article key={row.rowId}><strong>{row.email}</strong>{row.differences.map((diff) => <p key={diff.field}><span>{diff.field}</span><del>{diff.current || "blank"}</del><ins>{diff.proposed || "blank"}</ins></p>)}</article>)}</div>}</section>}
        <div className="approval-dock"><div><strong>Revision {run.revision}</strong><span>User hash {run.generation.userHash?.slice(0, 12)} · Group hash {run.generation.groupHash?.slice(0, 12)}</span></div><button className="primary" type="button" onClick={approve} disabled={busy || !run.validation.valid || (run.validation.updateCount > 0 && !existingReviewOpen)}>{run.validation.updateCount > 0 ? `Approve ${run.validation.updateCount} account updates and continue` : "Approve preview and continue"}</button></div><History run={run} />
      </section>}

      {step === 3 && run && <section className="panel"><div className="panel-heading"><div><span className="kicker">Step 4</span><h2>Submit</h2><p>Final writes are deliberate and are never retried automatically.</p></div></div><div className="submission-notice"><strong>Updates approved for submission.</strong><span>Nothing has been submitted to Axon yet.</span></div><SummaryCards validation={run.validation} /><div className="chunk-list">{run.chunks?.map((chunk) => <div key={chunk.chunkId}><span>{chunk.kind === "users" ? "User" : "Group"} chunk {chunk.ordinal}</span><strong>{chunk.rowIds.length} rows</strong><em>{chunk.status}</em></div>)}</div><ConnectionPanel config={config} session={session} onSaved={(nextConfig, nextSession) => { setConfig(nextConfig); setSession(nextSession); setMessage("Connection settings saved. Credentials remain in process memory."); }} /><label className="confirm-field"><span>Type the active Partner / Agency ID to confirm the target</span><input value={confirmAgency} onChange={(event) => setConfirmAgency(event.target.value)} /></label><div className="action-row"><button className="danger-button" type="button" disabled={busy || !session.configured || !config.writeOperationsEnabled || !confirmAgency} onClick={submitNext}>{busy ? "Submitting once…" : "Submit next eligible chunk to Axon"}</button><button className="secondary" type="button" onClick={exportPackage}>Export package instead</button></div><History run={run} /></section>}

      {step === 4 && run && <section className="panel"><div className="panel-heading"><div><span className="kicker">Step 5</span><h2>Track results</h2><p>User and Group jobs are tracked separately. Group jobs remain locked until applicable user jobs complete.</p></div><button className="secondary" type="button" onClick={exportPackage}>Export current revision</button></div><div className={`run-state ${run.status === "Failed" ? "failed" : ""}`}><span>Run status</span><strong>{run.status}</strong><small>{run.runId} · Revision {run.revision}</small></div><div className="chunk-list detailed">{run.chunks?.map((chunk) => <div key={chunk.chunkId}><span>{chunk.chunkId}</span><strong>{chunk.status}</strong><em>{chunk.axonJobId ? `Axon job ${chunk.axonJobId}` : "Not submitted"}</em></div>)}</div><ConnectionPanel config={config} session={session} onSaved={(nextConfig, nextSession) => { setConfig(nextConfig); setSession(nextSession); }} /><div className="action-row"><button className="primary" type="button" onClick={track} disabled={busy || !session.configured}>{busy ? "Checking…" : "Check submitted job status"}</button>{run.chunks?.some((chunk) => chunk.status === "ready") && <button className="secondary" type="button" onClick={() => setStep(3)}>Submit next eligible chunk</button>}<button className="secondary" type="button" onClick={newRun}>Start another run</button></div><History run={run} /></section>}
    </main>
    <footer><span>Shared baseline and pending overlay remain distinct.</span><span>Evidence Groups are unused; compatibility column stays blank.</span><span>One Axon Role and one default organizational Group per user.</span></footer>
  </div>;
}
