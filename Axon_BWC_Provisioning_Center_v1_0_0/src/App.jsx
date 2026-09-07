import { useEffect, useMemo, useState } from "react";
import { SyncHealth } from "../../ui/SyncHealth.jsx";
import { BulkChanges } from "../../ui/BulkChanges.jsx";
import { BULK_USER_FIELDS, previewBulkUsers } from "./bulkReview.js";
import { localApi } from "./api.js";
import { TaskHome, TaskNavigation } from "../../ui/TaskHome.jsx";
import "../../ui/theme.css";
import { PeopleReview } from "./PeopleReview.jsx";
import { stepForRun, approvalCurrent, submissionCopy, parseClipboard } from "./workflowUi.js";

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

function formatTime(value) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function groupOptionLabel(group) {
  const context = [group.component, group.aor, group.tier].filter(Boolean).join(" · ");
  return context ? `${group.name} — ${context}` : group.name;
}

function GroupNameSelect({ value, onChange, options, disabled, ariaLabel }) {
  const names = new Set(options.map((option) => option.name));
  return <select aria-label={ariaLabel} value={value || ""} onChange={(event) => onChange(event.target.value)} disabled={disabled}>
    <option value="">No Group selection</option>
    {value && !names.has(value) && <option value={value}>{value} — not in current Group pool</option>}
    {options.map((option) => <option value={option.name} key={`${option.externalId}:${option.name}`}>{groupOptionLabel(option)}</option>)}
  </select>;
}

function ExactGroupSelect({ row, draft, update, options }) {
  const currentExternalId = draft?.groupExternalId ?? row.groupExternalId ?? "";
  function select(externalId) {
    const option = options.find((item) => item.externalId === externalId);
    update(row.rowId, "groupExternalId", externalId);
    update(row.rowId, "groupName", option?.name || "");
  }
  return <div className="group-picker"><select aria-label={`Group for ${row.email}`} value={currentExternalId} onChange={(event) => select(event.target.value)}>
    <option value="">No Group assignment</option>
    {currentExternalId && !options.some((option) => option.externalId === currentExternalId) && <option value={currentExternalId}>{row.groupName || "Current Group"} — no longer in pool</option>}
    {options.map((option) => <option value={option.externalId} key={`${option.externalId}:${option.name}`}>{groupOptionLabel(option)}{option.name === row.recommendedGroupName ? " — recommended" : ""}</option>)}
  </select><small>{row.recommendedGroupName ? `Recommendation: ${row.recommendedGroupName}` : "No complete governed recommendation"}</small></div>;
}

function IntakeGrid({ rows, setRows, disabled, groupOptions, onError }) {
  function paste(event) {
    const text = event.clipboardData.getData("text");
    if (!/[\t\n,]/.test(text)) return;
    event.preventDefault();
    try {
      const imported = parseClipboard(text);
      if (!imported.length || disabled) return;
      if (rows.some(row => row.Email || row.Role || row["Group Name"]) &&
          !window.confirm(`Replace the current intake grid with ${imported.length} pasted user(s)? Existing saved runs are not changed.`)) return;
      setRows(imported.map(row => ({ ...row, id: crypto.randomUUID() })));
    }
    catch (error) { onError(error.message); }
  }
  function update(index, key, value) {
    setRows((current) => current.map((row, rowIndex) => (rowIndex === index ? { ...row, [key]: value } : row)));
  }
  return <div className="intake-grid-wrap">
    <table className="intake-grid" onPaste={paste}>
      <thead><tr><th>#</th><th>Email <span>required</span></th><th>Role <span>required</span></th><th>Group Name <span>optional; blank creates no Group relationship</span></th><th /></tr></thead>
      <tbody>{rows.map((row, index) => <tr key={row.id}>
        <td>{index + 1}</td>
        <td><input aria-label={`Email row ${index + 1}`} value={row.Email} onChange={(event) => update(index, "Email", event.target.value)} disabled={disabled} /></td>
        <td><input list="approved-roles" aria-label={`Role row ${index + 1}`} value={row.Role} onChange={(event) => update(index, "Role", event.target.value)} disabled={disabled} /></td>
        <td><GroupNameSelect ariaLabel={`Group Name row ${index + 1}`} value={row["Group Name"]} onChange={(value) => update(index, "Group Name", value)} options={groupOptions} disabled={disabled} /></td>
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
    ["Warnings", validation?.warningCount || 0, validation?.warningCount ? "amber" : "neutral"],
    ["Blocked", validation?.blockerCount || 0, validation?.blockerCount ? "red" : "green"],
  ];
  return <div className="summary-cards">{cards.map(([label, value, tone]) => <article className={`metric ${tone}`} key={label}><span>{label}</span><strong>{value.toLocaleString()}</strong></article>)}</div>;
}

function AssignmentTable(props) { return <PeopleReview {...props} GroupPicker={ExactGroupSelect} />; }

function History({ run }) {
  return <details className="history"><summary>Revision history ({run.history?.length || 0})</summary><ol>{run.history?.map((item) => <li key={item.revision}><strong>Revision {item.revision}</strong> · {item.event}<span>{item.reason} · {formatTime(item.createdAt)}</span></li>)}</ol></details>;
}

function ConnectionPanel({ config, session, onSaved }) {
  const [saveError, setSaveError] = useState("");
  const [values, setValues] = useState({ agencyBaseUrl: config.agencyBaseUrl || "", timeoutSeconds: config.timeoutSeconds || 90, writeOperationsEnabled: config.writeOperationsEnabled || false, groupFileFieldConfirmed: config.groupFileFieldConfirmed || false, partnerId: "", clientId: "", clientSecret: "" });
  const [busy, setBusy] = useState(false);
  useEffect(() => setValues((current) => ({ ...current, agencyBaseUrl: config.agencyBaseUrl || "", timeoutSeconds: config.timeoutSeconds || 90, writeOperationsEnabled: config.writeOperationsEnabled || false, groupFileFieldConfirmed: config.groupFileFieldConfirmed || false })), [config]);
  async function save() {
    setSaveError("");
    setBusy(true);
    try {
      const savedConfig = await localApi.saveConfig({...values,expectedWorkspaceRevision:config.workspaceRevision});
      let savedSession = session;
      if (values.partnerId || values.clientId || values.clientSecret) savedSession = await localApi.saveCredentials(values);
      onSaved(savedConfig, savedSession);
      setValues((current) => ({ ...current, partnerId: "", clientId: "", clientSecret: "" }));
    } catch (error) { setSaveError(error.message); } finally { setBusy(false); }
  }
  return <details className="connection-panel"><summary><span className={`dot ${session.configured ? "on" : ""}`} /> Axon connection · {session.configured ? `credentials loaded ${session.partnerHint}` : "not configured"}</summary><div className="connection-grid">
    {session.credentialWarning && <p role="alert">{session.credentialWarning}</p>}
    {session.testCredentialsLoaded && <p>Local test credential file loaded. Loading the file does not verify access with Axon. Leave credential fields blank to keep it. The plaintext file remains after exit; clearing a session does not delete it.</p>}
    {config.legacyBindingRequired && <label className="checkbox-line"><input type="checkbox" checked={Boolean(values.confirmLegacyTenant)} onChange={e=>setValues({...values,confirmLegacyTenant:e.target.checked})} /> I confirm the existing local data belongs to this tenant (one-time binding).</label>}
    {config.tenantHost && <p>Workspace bound to {config.tenantHost}.</p>}
    <label><span>Tenant HTTPS URL</span><input value={values.agencyBaseUrl} onChange={(event) => setValues({ ...values, agencyBaseUrl: event.target.value })} placeholder="https://your-tenant.evidence.com" /></label>
    <label><span>Partner / Agency ID</span><input value={values.partnerId} onChange={(event) => setValues({ ...values, partnerId: event.target.value })} /></label>
    <label><span>Client ID</span><input value={values.clientId} onChange={(event) => setValues({ ...values, clientId: event.target.value })} /></label>
    <label><span>Client secret</span><input type="password" value={values.clientSecret} onChange={(event) => setValues({ ...values, clientSecret: event.target.value })} /></label>
    <label className="check"><input type="checkbox" checked={values.writeOperationsEnabled} onChange={(event) => setValues({ ...values, writeOperationsEnabled: event.target.checked })} /><span>Enable deliberate Axon write operations</span></label>
    <label className="check"><input type="checkbox" checked={values.groupFileFieldConfirmed} onChange={(event) => setValues({ ...values, groupFileFieldConfirmed: event.target.checked })} /><span>Authorized Group import field confirmed</span></label>
    <button className="secondary" type="button" disabled={busy} onClick={async () => {
      setBusy(true);
      try {
        onSaved(await localApi.config(), session);
        setValues(current => ({ ...current, confirmLegacyTenant: false }));
        setSaveError("");
      } catch {
        setSaveError("Settings could not reload. Keep the launcher open and retry.");
      } finally { setBusy(false); }
    }}>Reload settings</button>
    <button className="secondary" type="button" disabled={busy || !session.configured} onClick={async () => {
      setBusy(true);
      try { onSaved(config, await localApi.clearCredentials()); setSaveError(""); }
      catch (error) { setSaveError(error.message); }
      finally { setBusy(false); }
    }}>Clear session credentials (keep file)</button>
    <button className="secondary" type="button" disabled={busy} onClick={save}>{busy ? "Saving…" : "Save local connection"}</button>
  </div>{saveError && <p role="alert">{saveError}</p>}<p className="muted">Credentials remain in this Python process and are never written to the shared workspace.</p></details>;
}

function RefreshPanel({ config, session, workspace, job, form, setForm, onStart, onCancel, onConnection }) {
  const running = job?.status === "running";
  return <details className="refresh-panel">
    <summary>Shared Axon snapshots <span>{workspace.snapshots?.length || 0} active scope(s)</span></summary>
    <p>Refresh here or in Geographic Operations. A shared lease prevents duplicate resource pulls, and activation occurs only after a complete validated result.</p>
    <div className="refresh-grid">
      <label><span>Resource</span><select value={form.resource} onChange={(event) => setForm({ ...form, resource: event.target.value })} disabled={running}>{["Users", "Groups", "Devices", "DeviceHomes"].map((value) => <option key={value}>{value}</option>)}</select></label>
      {form.resource === "Devices" && <><label><span>Device scope</span><select value={form.scope || "filtered"} disabled={running} onChange={e=>setForm({...form,scope:e.target.value})}><option value="filtered">Filtered devices</option><option value="full">Full inventory — all models</option></select></label><label><span>Model string(s)</span><input value={form.model} onChange={(event) => setForm({ ...form, model: event.target.value })} placeholder="Single model or comma-separated" disabled={running || form.scope === "full"} /></label><label><span>Device status</span><input value={form.status2} onChange={(event) => setForm({ ...form, status2: event.target.value })} placeholder="Exact status2 value" disabled={running || form.scope === "full"} /></label><label><span>Device Home ID</span><input value={form.homeId} onChange={(event) => setForm({ ...form, homeId: event.target.value })} placeholder="Exact home ID" disabled={running || form.scope === "full"} /></label></>}
    </div>
    {form.resource === "Devices" && <p>{form.scope === "full" ? "Full inventory ignores all model, status and Home fields above. All devices will be requested." : "Only devices matching the stated filters will be requested."}</p>}
    <div className="snapshot-list">{workspace.snapshots?.map((snapshot) => <span key={snapshot.snapshotId}><strong>{snapshot.resource}</strong> · {snapshot.scope?.type || "unknown"} · {snapshot.rowCount.toLocaleString()} rows · {formatTime(snapshot.activatedAt)}</span>)}</div>
    {job && <div className={`refresh-state ${job.status}`}><strong>{job.resource} · {job.status}</strong><span>{job.message}</span>{job.scope?.type === "filtered" && <small>Filtered Devices data remains separate from the full baseline.</small>}</div>}
    <div className="action-row"><button className="primary" type="button" onClick={onStart} disabled={running || !session.configured}>{running ? "Refreshing…" : `Refresh ${form.resource}`}</button>{running && <button className="secondary" type="button" onClick={onCancel}>Cancel safely</button>}<span>{session.configured ? "Credentials are available in this process only." : "Open Axon connection below before refreshing."}</span></div>
    <ConnectionPanel config={config} session={session} onSaved={onConnection} />
  </details>;
}

export function App() {
  const [syncHealth, setSyncHealth] = useState({error:false,checkedAt:""});
  const [retrySync,setRetrySync] = useState(0);
  const [run, setRun] = useState(null);
  const [view, setView] = useState("home");
  const [roleOptions, setRoleOptions] = useState([]);
  const [workspace, setWorkspace] = useState({ workspaceRevision: 0, snapshots: [], pendingCounts: {} });
  const [session, setSession] = useState({ configured: false, partnerHint: "" });
  const [config, setConfig] = useState({ agencyBaseUrl: "", timeoutSeconds: 90, writeOperationsEnabled: false, groupFileFieldConfirmed: false });
  const [groupOptions, setGroupOptions] = useState([]);
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
  const [bulkDraftDirty, setBulkDraftDirty] = useState(false);
  const [existingReviewOpen, setExistingReviewOpen] = useState(false);
  const [confirmAgency, setConfirmAgency] = useState("");
  const [confirmTarget, setConfirmTarget] = useState(false);
  useEffect(() => { setConfirmTarget(false); setConfirmAgency(""); }, [run?.revision, config.agencyBaseUrl, session.credentialSource]);
  const [refreshForm, setRefreshForm] = useState({ resource: "Users", model: "", status2: "", homeId: "" });
  const [refreshJob, setRefreshJob] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const activeStep = step;
  const approved = approvalCurrent(run);
  const [submitTitle, submitDescription] = submissionCopy(run);
  const changedRows = useMemo(() => Object.entries(drafts).filter(([, changes]) => Object.keys(changes).length), [drafts]);

  useEffect(() => {
    Promise.all([localApi.workspace(), localApi.latestRun(), localApi.session(), localApi.config(), localApi.groupOptions(), localApi.roleOptions()]).then(([workspaceData, runData, sessionData, configData, groupData, roleData]) => {
      setWorkspace(workspaceData); setRun(runData.run); setSession(sessionData); setConfig(configData); setGroupOptions(groupData.groups || []); setRoleOptions(roleData.roles || []);
      if (runData.run) setStep(stepForRun(runData.run));
    }).catch((requestError) => setError(requestError.message));
  }, []);

  useEffect(() => {
    const timer = window.setInterval(async () => {
      try {
        const next = await localApi.workspace();
        setSyncHealth({error:false,checkedAt:new Date().toISOString()});
        if (next.workspaceRevision !== workspace.workspaceRevision) {
          setWorkspace(next);
          setGroupOptions((await localApi.groupOptions()).groups || []);
          setRoleOptions((await localApi.roleOptions()).roles || []);
          if (run?.runId && !changedRows.length) {
            const refreshed = await localApi.getRun(run.runId);
            setRun(refreshed.run);
          }
        }
      } catch { setSyncHealth(current=>({...current,error:true})); }
    }, 4000);
    return () => window.clearInterval(timer);
  }, [workspace.workspaceRevision, run?.runId, changedRows.length, retrySync]);

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
      const filters = refreshForm.scope === "full" ? {} : { model: refreshForm.model, status2: refreshForm.status2, homeId: refreshForm.homeId };
      if (refreshForm.resource === "Devices" && refreshForm.scope !== "full" && !Object.values(filters).some(v=>String(v || "").trim())) throw Error("Enter a device filter or explicitly select Full inventory.");
      const result = await localApi.startRefresh({ resource: refreshForm.resource, filters });
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
        setRun(result.run); setStep(stepForRun(result.run)); setDrafts({}); setSelected(new Set()); setMessage(result.run.validation.valid ? (result.run.validation.warningCount ? "User import validation passed with optional warnings. Any new mapping values were queued for review; Preview is ready." : "Enrichment and validation passed. Preview is ready.") : "Enrichment finished with exceptions requiring review.");
        setWorkspace(await localApi.workspace());
      }
    } catch (requestError) { setError(requestError.message); }
    finally { setBusy(false); setEntraToken(""); }
  }

  async function saveEdits(extraEdits = [], reason = changeReason) {
    if (!reason.trim()) { setError("Enter a reason for the assignment change."); return; }
    const edits = [...changedRows.map(([rowId, changes]) => ({ rowId, changes })), ...extraEdits];
    if (!edits.length) { setError("Change at least one assignment field first."); return; }
    setBusy(true); setError("");
    try {
      const result = await localApi.editRun(run.runId, { expectedRevision: run.revision, edits, reason });
      setRun(result.run); setStep(stepForRun(result.run)); setDrafts({}); setSelected(new Set()); setExistingReviewOpen(false); setMessage("Revision saved. Dependencies, strict records, validation, and chunks were regenerated automatically.");
      setWorkspace(await localApi.workspace());
    } catch (requestError) { setError(requestError.message); if (extraEdits.length) throw requestError; }
    finally { setBusy(false); }
  }

  async function approve() {
    if (changedRows.length || bulkDraftDirty) { setError("Save or discard your edits before approving this preview."); return; }
    setBusy(true); setError("");
    try {
      const count = run.validation.updateCount || 0;
      const result = await localApi.approveRun(run.runId, { expectedRevision: run.revision, approveUpdates: count > 0, updateCount: count });
      setRun(result.run); setStep(3); setMessage(result.message);
    } catch (requestError) { setError(requestError.message); }
    finally { setBusy(false); }
  }

  async function submitNext() {
    if (changedRows.length || bulkDraftDirty || !approved) { setError("Save edits and approve the current revision before submission."); return; }
    setBusy(true); setError("");
    try {
      const result = await localApi.submitNext(run.runId, { expectedRevision: run.revision, confirmWrite: true, confirmAgency, confirmTarget, targetOrigin: session.testCredentialTarget });
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
    if (changedRows.length || bulkDraftDirty) { setError("Save or discard edits before exporting the saved revision."); return; }
    setBusy(true); setError("");
    try {
      const result = await localApi.exportRun(run.runId, run.revision);
      const anchor = document.createElement("a"); anchor.href = result.download.url; anchor.download = result.download.name; anchor.click();
      setMessage("One governed run package was exported. It is not intended for re-upload into this workflow.");
    } catch (requestError) { setError(requestError.message); }
    finally { setBusy(false); }
  }

  function newRun() {
    if (changedRows.length || bulkDraftDirty) { setError("Save or discard edits before starting another run."); return; }
    setView("people");
    setRun(null); setStep(0); setRows([{ id: crypto.randomUUID(), Email: "", Role: "", "Group Name": "" }]); setIntakeFile(null); setDirectoryFile(null); setDetection(null); setColumnMapping({}); setDrafts({}); setSelected(new Set()); setError(""); setMessage("");
  }

  function navigate(next) {
    if (busy || changedRows.length || bulkDraftDirty) { setError("Save or discard your edits before leaving this task."); return; }
    setView(next);
    window.setTimeout(() => document.getElementById("main-content")?.focus(), 0);
  }
  useEffect(() => {
    function warn(event) { if (changedRows.length || bulkDraftDirty) { event.preventDefault(); event.returnValue = ""; } }
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [changedRows.length, bulkDraftDirty]);
  useEffect(() => { setExistingReviewOpen(false); }, [run?.revision]);

  const bulkUserPanel = <BulkChanges count={selected.size}
    fields={Object.keys(BULK_USER_FIELDS)}
    options={{ Role: roleOptions, Group: groupOptions.map(g => ({value:g.externalId,label:groupOptionLabel(g)})),
      "Job category":["Standard User","First-Line Supervisor","Senior/Second-Line Supervisor"] }}
    signature={JSON.stringify([run?.runId,run?.revision,[...selected].sort()])}
    disabled={busy || !!changedRows.length} onDirtyChange={setBulkDraftDirty}
    onPreview={changes => previewBulkUsers(run, selected, changes, groupOptions)}
    onApply={async (changes, reason, preview) => {
      if (preview.runId !== run.runId || preview.revision !== run.revision) throw new Error("This run changed. Preview the bulk changes again.");
      await saveEdits(preview.edits, reason);
    }} />;

  return <div className="app">
    <a className="skip-link" href="#main-content">Skip to main content</a>
    <TaskNavigation items={[["home","Home"],["people","People"],["setup","Setup & rules"]]} current={view} onNavigate={navigate} help={() => navigate("help")} />
    <datalist id="approved-roles">{roleOptions.map(role => <option key={role} value={role} />)}</datalist>
    <SyncHealth error={syncHealth.error} checkedAt={syncHealth.checkedAt} onRetry={()=>setRetrySync(v=>v+1)} loadDiagnostics={localApi.supportDiagnostics}/>
    <main id="main-content" tabIndex="-1">
      {view === "home" && <TaskHome description="Add or update accounts. Review every change before submitting to Axon." tasks={[
        {title:"Add or update people",description:"Start with email and role. Group assignment is optional.",action:"Start a user list",onClick:newRun,primary:true},
        {title:"Review your current list",description:run ? `Revision ${run.revision} · ${run.status}` : "Your saved provisioning run will appear here.",action:run ? "Continue review" : "Add people",onClick:() => navigate("people")},
        {title:"Setup & rules",description:"Refresh saved Axon data and configure this process's connection.",action:"Open setup",onClick:() => navigate("setup")}
      ]}><section><h2>Continue your work</h2><p>{run ? `${run.rows.length} people · ${run.status}` : "No saved user list yet."}</p><p>Approval and submission are separate actions.</p>{run && <button className="secondary" onClick={() => navigate("people")}>Continue review</button>}</section><section><h2>Saved data</h2><p>{workspace.snapshots?.length || 0} saved resource scope(s)</p><button className="text-button" onClick={() => navigate("setup")}>View refresh details</button></section></TaskHome>}
      {view === "help" && <section className="panel"><h2>Provisioning help</h2><p>Add Users → Enrich → Review Exceptions → Preview → Submit → Track.</p><p>Only Email and Role are required to start. Optional location, job-category and Group mapping warnings do not block account creation.</p><p>Use Geographic Operations to edit Allowed Axon roles and other shared rules under Setup & rules. Start it with Start-Geographic-Prototype.cmd on Windows, or its Python launcher on macOS. Both apps share saved data. An optional local testing file can supply credentials independently to each process.</p><button className="secondary" onClick={() => navigate("people")}>Go to people</button></section>}
      {view === "setup" && <><h2>Saved data & connection</h2><p>Manage shared snapshots here. Edit role and mapping tables in Geographic Operations → Setup & rules.</p><RefreshPanel config={config} session={session} workspace={workspace} job={refreshJob} form={refreshForm} setForm={setRefreshForm} onStart={startRefresh} onCancel={cancelRefresh} onConnection={(nextConfig, nextSession) => { setConfig(nextConfig); setSession(nextSession); setMessage("Connection settings saved. Session ready. Credentials are checked by Axon only when a live action runs."); }} /></>}
      {view === "people" && <nav className="stepper" aria-label="Provisioning steps">{STEPS.map((label,index) => <button key={label} type="button" aria-current={index === step ? "step" : undefined} className={index === activeStep ? "active" : ""} disabled={busy || (!run && index > 0)} onClick={() => { if (changedRows.length || bulkDraftDirty) { setError("Save or discard edits before changing steps."); return; } setStep(index); }}><span>{index+1}</span>{label}</button>)}</nav>}
      {message && <div className="banner success" role="status">{message}<button type="button" onClick={() => setMessage("")}>×</button></div>}
      {error && <div className="banner error" role="alert">{error}<button type="button" onClick={() => setError("")}>×</button></div>}

      {view === "people" && step === 0 && <section className="panel">
        <div className="panel-heading"><div><span className="kicker">Step 1</span><h2>Add users</h2><p>Start with Email and Role. Group Name is optional; leave it blank for no Group assignment. Any governed recommendation appears in Preview for deliberate selection.</p></div>{run && <button className="secondary" type="button" onClick={newRun}>Start another run</button>}</div>
        <div className="intake-choice"><div className={!intakeFile ? "choice active" : "choice"}><h3>Paste or type users</h3><p>Paste rows from Excel or add them in the grid.</p></div><label className={intakeFile ? "choice active upload" : "choice upload"}><h3>Upload users</h3><p>Flexible CSV or XLSX headers are accepted.</p><input type="file" accept=".csv,.xlsx" onChange={(event) => event.target.files?.[0] && chooseIntakeFile(event.target.files[0])} /><span>{intakeFile ? `${intakeFile.name} · ${intakeFile.detail}` : "Choose .csv or .xlsx"}</span></label></div>
        {intakeFile && <button className="text-button" type="button" onClick={() => { setIntakeFile(null); setDetection(null); }}>Use paste grid instead</button>}
        {!intakeFile && <IntakeGrid rows={rows} setRows={setRows} disabled={busy} groupOptions={groupOptions} onError={setError} />}
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

      {view === "people" && step === 1 && run && <section className="panel wide-panel"><div className="panel-heading"><div><span className="kicker">Step 2</span><h2>Review exceptions</h2><p>Identity values remain read-only. Correct source identity through reconciliation; edit only governed assignment fields here.</p></div><button className="secondary" type="button" disabled={busy || bulkDraftDirty || !!changedRows.length} onClick={() => setStep(0)}>Return to intake</button></div><SummaryCards validation={run.validation} />
        {bulkUserPanel}
        {changedRows.length > 0 && <div className="callout warning">Unsaved edits. <button type="button" className="text-button" disabled={busy} onClick={() => setDrafts({})}>Discard unsaved edits</button></div>}
        <AssignmentTable run={run} onlyExceptions drafts={drafts} setDrafts={setDrafts} selected={selected} setSelected={setSelected} groupOptions={groupOptions} disabled={busy} />
        <div className="action-row"><button className="primary" type="button" onClick={() => saveEdits()} disabled={busy || !changedRows.length}>{busy ? "Saving revision…" : `Save ${changedRows.length} edited row(s)`}</button>{run.validation.valid && <button className="secondary" type="button" disabled={busy || bulkDraftDirty || !!changedRows.length} onClick={() => setStep(2)}>Continue to preview</button>}<label className="change-reason"><span>Reason for change (required)</span><input className="reason" value={changeReason} onChange={(event) => setChangeReason(event.target.value)} placeholder="Explain the basis for this change" /></label></div><History run={run} />
      </section>}

      {view === "people" && step === 2 && run && <section className="panel wide-panel"><div className="panel-heading"><div><span className="kicker">Step 3</span><h2>Preview changes</h2><p>Review current Axon values against the proposed run. Saving any edit creates a new revision and clears prior approval.</p></div><button className="secondary" type="button" onClick={exportPackage}>Export optional review package</button></div><SummaryCards validation={run.validation} />
        {run.validation.blockerCount > 0 && <div className="callout danger"><strong>{run.validation.blockerCount} blocker(s) remain.</strong><button className="text-button" type="button" onClick={() => setStep(1)}>Review exceptions</button></div>}
        {bulkUserPanel}
        <div className="bulk-bar"><strong>Assignment-only edits</strong><span>{changedRows.length} row(s) changed</span><label className="change-reason"><span>Reason for change (required)</span><input value={changeReason} onChange={(event) => setChangeReason(event.target.value)} placeholder="Explain the basis for this change" /></label><button className="secondary" type="button" onClick={() => saveEdits()} disabled={busy || !changedRows.length}>Save revision</button></div>
        <AssignmentTable run={run} drafts={drafts} setDrafts={setDrafts} selected={selected} setSelected={setSelected} groupOptions={groupOptions} disabled={busy} />
        {run.validation.updateCount > 0 && <section className="account-review"><div><h3>{run.validation.updateCount} existing account update(s)</h3><p>Open the field-level review before approval. Approval is bound to this run revision and does not submit to Axon.</p></div><button className="secondary" type="button" onClick={() => setExistingReviewOpen((current) => !current)}>{existingReviewOpen ? "Close account review" : "Open existing-account review"}</button>{existingReviewOpen && <div className="difference-list">{run.rows.filter((row) => row.existingAccount && row.differences?.length).map((row) => <article key={row.rowId}><strong>{row.email}</strong>{row.differences.map((diff) => <p key={diff.field}><span>{diff.field}</span><del>{diff.current || "blank"}</del><ins>{diff.proposed || "blank"}</ins></p>)}</article>)}</div>}</section>}
        {changedRows.length > 0 && <div className="callout warning" role="status">Unsaved edits — approval is paused. Save and revalidate, or <button type="button" className="text-button" disabled={busy} onClick={() => { setDrafts({}); setExistingReviewOpen(false); }}>Discard unsaved edits</button>.</div>}
        <div className="approval-dock"><div><strong>Revision {run.revision}</strong><span>User hash {run.generation.userHash?.slice(0, 12)} · Group hash {run.generation.groupHash?.slice(0, 12)}</span></div><button className="primary" type="button" onClick={approve} disabled={busy || bulkDraftDirty || !!changedRows.length || !run.validation.valid || (run.validation.updateCount > 0 && !existingReviewOpen)}>{run.validation.updateCount > 0 ? `Approve ${run.validation.updateCount} account updates and continue` : "Approve preview and continue"}</button></div><History run={run} />
      </section>}

      {view === "people" && step === 3 && run && <section className="panel"><div className="panel-heading"><div><span className="kicker">Step 4</span><h2>Submit</h2><p>Final writes are deliberate and are never retried automatically.</p></div></div><div className="submission-notice"><strong>{submitTitle}</strong><span>{submitDescription}</span>{!approved && <button className="text-button" onClick={() => setStep(2)}>Return to Preview Changes</button>}</div><SummaryCards validation={run.validation} /><div className="chunk-list">{run.chunks?.map((chunk) => <div key={chunk.chunkId}><span>{chunk.kind === "users" ? "User" : "Group"} chunk {chunk.ordinal}</span><strong>{chunk.rowIds.length} rows</strong><em>{chunk.status}</em></div>)}</div><ConnectionPanel config={config} session={session} onSaved={(nextConfig, nextSession) => { setConfig(nextConfig); setSession(nextSession); setMessage("Connection settings saved. Session ready. Credentials are checked by Axon only when a live action runs."); }} />{session.testCredentialsLoaded ? <label className="confirm-field"><input type="checkbox" checked={confirmTarget} onChange={e=>setConfirmTarget(e.target.checked)} /><span>I confirm submission to {config.agencyBaseUrl} using the loaded test profile ({session.partnerHint}).</span></label> : <label className="confirm-field"><span>Type the active Partner / Agency ID to confirm the target</span><input value={confirmAgency} onChange={(event) => setConfirmAgency(event.target.value)} /></label>}<div className="action-row"><button className="danger-button" type="button" disabled={busy || bulkDraftDirty || !!changedRows.length || !approved || !run.chunks?.some(c => c.status === "ready") || !session.configured || !config.writeOperationsEnabled || (session.testCredentialsLoaded ? !confirmTarget : !confirmAgency)} onClick={submitNext}>{busy ? "Submitting once…" : "Submit next eligible chunk to Axon"}</button><button className="secondary" type="button" onClick={exportPackage}>Export package instead</button></div><History run={run} /></section>}

      {view === "people" && step === 4 && run && <section className="panel"><div className="panel-heading"><div><span className="kicker">Step 5</span><h2>Track results</h2><p>User and Group jobs are tracked separately. Group jobs remain locked until applicable user jobs complete.</p><p>Completed jobs are not snapshot confirmation. Refresh Users after jobs complete to reconcile observable account values; Group membership remains separately verified.</p><p>{run.confirmationSummary?.confirmed || 0} user changes confirmed · {run.confirmationSummary?.awaiting || 0} awaiting confirmation.</p>{!!run.confirmationSummary?.unobservableFields?.length && <p>Not returned by the current snapshot: {run.confirmationSummary.unobservableFields.join(", ")}. These changes remain unverified.</p>}{!!run.confirmationSummary?.mismatchedFields?.length && <p>Values still differ: {run.confirmationSummary.mismatchedFields.join(", ")}.</p>}</div><button className="secondary" type="button" onClick={exportPackage}>Export current revision</button></div><div className={`run-state ${run.status === "Failed" ? "failed" : ""}`}><span>Run status</span><strong>{run.status}</strong><small>{run.runId} · Revision {run.revision}</small></div><div className="chunk-list detailed">{run.chunks?.map((chunk) => <div key={chunk.chunkId}><span>{chunk.chunkId}</span><strong>{chunk.status}</strong><em>{chunk.axonJobId ? `Axon job ${chunk.axonJobId}` : "Not submitted"}</em></div>)}</div><ConnectionPanel config={config} session={session} onSaved={(nextConfig, nextSession) => { setConfig(nextConfig); setSession(nextSession); }} /><div className="action-row"><button className="primary" type="button" onClick={track} disabled={busy || !session.configured}>{busy ? "Checking…" : "Check submitted job status"}</button>{run.chunks?.some((chunk) => chunk.status === "ready") && <button className="secondary" type="button" onClick={() => setStep(3)}>Submit next eligible chunk</button>}<button className="secondary" type="button" onClick={newRun}>Start another run</button></div><History run={run} /></section>}
    </main>
    <footer><span>Shared baseline and pending overlay remain distinct.</span><span>Evidence Groups are unused; compatibility column stays blank.</span><span>One Axon Role is required; the organizational Group assignment may be left blank.</span></footer>
  </div>;
}
