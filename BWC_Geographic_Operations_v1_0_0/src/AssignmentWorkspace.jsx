import { useEffect, useRef, useState } from "react";
import { localApi } from "./api.js";

export const emptyAssignmentFilters = { search: "", role: "", deviceCount: "", page: 1 };
const countChoices = [["", "All counts"], ["0", "Zero devices"], ["1", "One device"], ["2", "Two devices"], ["3+", "Three or more devices"], ["unavailable", "Count unavailable"]];
const scopeLabel = { full: "Full Devices baseline", filtered: "Filtered Devices snapshot", unavailable: "Devices unavailable" };
const timestamp = (snapshot) => snapshot ? new Date(snapshot.activatedAt).toLocaleString() : "Not loaded";

function useSavedAssignments(query, requestKey, enabled, detail = false) {
  const [result, setResult] = useState(null);
  const [failure, setFailure] = useState(null);
  const queryKey = JSON.stringify(query);
  useEffect(() => {
    if (!enabled) return undefined;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      const api = detail ? localApi.assignmentDevices : localApi.assignments;
      api(JSON.parse(queryKey), controller.signal)
        .then((data) => { if (!controller.signal.aborted) { setResult({ key: requestKey, data }); setFailure(null); } })
        .catch((error) => { if (!controller.signal.aborted) setFailure({ key: requestKey, message: error.message }); });
    }, 200);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [enabled, detail, queryKey, requestKey]);
  return { data: enabled && result?.key === requestKey ? result.data : null,
    error: enabled && failure?.key === requestKey ? failure.message : "", previous: result?.data };
}

function AssignmentDevices({ selection, workspaceRevision, onClose }) {
  const [page, setPage] = useState(1);
  const heading = useRef(null);
  useEffect(() => { heading.current?.focus(); }, []);
  const query = { userId: selection.userId, expectedRevision: workspaceRevision, page, pageSize: 50 };
  const requestKey = JSON.stringify(query);
  const { data, error } = useSavedAssignments(query, requestKey, true, true);
  const noDevices = data?.total === 0;
  return <section className="assignment-detail" aria-label={`Assigned devices for ${selection.displayName}`}>
    <div className="page-heading"><div><h3 ref={heading} tabIndex="-1">Assigned devices: {selection.displayName}</h3><p>Axon User ID: {selection.userId}</p></div><button type="button" className="secondary-button" onClick={onClose}>Close device details</button></div>
    <p role="status">{data ? `${data.total === null ? "Count unavailable" : `${data.total} assigned devices in this scope`} · ${scopeLabel[data.deviceScope]}` : error ? "Device details unavailable" : "Loading assigned devices…"}</p>
    {error && <p className="inventory-error" role="alert">{error} Close these details and use Reload saved data.</p>}
    {data?.deviceScope === "unavailable" && <p>Refresh Devices to establish this user's assignments. An unavailable count does not mean zero devices.</p>}
    {noDevices && <p>{data.deviceScope === "filtered" ? "No assigned devices appear in this filtered snapshot. Other devices may exist outside its filters." : "No devices in the full saved Devices baseline reference this Axon User ID."}</p>}
    {!!data?.rows.length && <div className="table-shell"><table><caption>Exact device records linked to the selected Axon User ID</caption><thead><tr>{["Serial / device ID", "Model", "Disposition", "Device Home", "Mapped component", "Mapped AOR"].map((label) => <th key={label} scope="col">{label}</th>)}</tr></thead><tbody>{data.rows.map((device, index) => <tr key={`${device.deviceId}:${index}`}><td>{device.serialNumber || device.deviceId || "Not supplied"}</td><td>{device.model || "Not supplied"}</td><td>{device.disposition}</td><td>{device.deviceHome || "Not supplied"}</td><td>{device.component || "Unmapped"}</td><td>{device.regionAor || "Unmapped"}</td></tr>)}</tbody></table></div>}
    {data?.totalPages > 1 && <div className="inventory-filter-actions"><span>Devices page {data.page} of {data.totalPages}</span><button type="button" className="secondary-button" disabled={data.page <= 1} onClick={() => setPage(data.page - 1)}>Previous devices</button><button type="button" className="secondary-button" disabled={data.page >= data.totalPages} onClick={() => setPage(data.page + 1)}>Next devices</button></div>}
    <p className="inventory-review-note">Device Home and mapped AOR describe device placement. They do not change the user's personnel location or Axon Group membership.</p>
  </section>;
}

export function AssignmentWorkspace({ filters, setFilters, isLive, liveData, showToast }) {
  const [reload, setReload] = useState(0);
  const [selection, setSelection] = useState(null);
  const selectionTrigger = useRef(null);
  const [exporting, setExporting] = useState(false);
  const query = { ...filters, search: filters.search.trim(), pageSize: 50 };
  const requestKey = `${JSON.stringify(query)}:${liveData.workspaceRevision}:${reload}`;
  const { data, error, previous } = useSavedAssignments(query, requestKey, isLive);
  const busy = isLive && !data && !error;
  const roles = [...new Set([...(data?.roles || previous?.roles || []), ...(filters.role ? [filters.role] : [])])].sort();
  const selected = selection?.requestKey === requestKey ? selection : null;
  const canExport = isLive && data?.userSnapshot && !exporting;
  const active = filters.search || filters.role || filters.deviceCount;
  function change(key, value) { setFilters((current) => ({ ...current, [key]: value, page: 1 })); }
  async function exportView() {
    if (!canExport) return;
    setExporting(true);
    try {
      const file = await localApi.exportAssignments({ ...query, expectedRevision: data.workspaceRevision });
      const url = URL.createObjectURL(file.blob);
      const link = document.createElement("a"); link.href = url; link.download = file.filename; link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      showToast(`Exported all ${data.total.toLocaleString()} matching users with assignment counts and snapshot details.`);
    } catch (error) { showToast(error.message); }
    finally { setExporting(false); }
  }
  return <section className="data-page inventory-workspace assignments-workspace">
    <div className="page-heading"><div><p className="eyebrow">MANAGE · DEVICE ASSIGNMENTS</p><h2>Investigate user assignments</h2><p>Filter users by role and device count, then open their exact assigned device records.</p></div><button type="button" className="primary-button" disabled={!canExport} onClick={exportView}>{exporting ? "Preparing CSV…" : "Export matching assignments"}</button></div>
    <div className="inventory-scope" role="status"><strong>{!isLive ? "Saved Users snapshot required" : data ? data.userSnapshot ? scopeLabel[data.deviceScope] : "Users snapshot unavailable" : busy ? "Loading saved assignments…" : "Assignments could not be loaded"}</strong>
      <span>Users snapshot: {timestamp(data?.userSnapshot)} · Devices snapshot: {timestamp(data?.deviceSnapshot)}</span>
      {data?.deviceScope === "filtered" && <span>Device counts cover only {JSON.stringify(data.deviceSnapshot.scope.filters)}. Zero means zero within these filters.</span>}
      {data?.userSnapshot && data.deviceScope === "unavailable" && <span>Users and roles are available. Device counts remain unavailable until Devices are refreshed.</span>}
      {!data?.userSnapshot && !busy && <span>Use Connect to Axon to refresh Users. Saved snapshots from either application are reused here.</span>}
    </div>
    <div className="inventory-filter-grid" aria-label="Assignment filters">
      <label><span>Search assignments</span><input type="search" aria-label="Search assignments" maxLength={500} value={filters.search} onChange={(event) => change("search", event.target.value)} placeholder="User name, exact ID, role, model, or state" /></label>
      <label><span>Axon Role</span><select aria-label="Axon Role" value={filters.role} onChange={(event) => change("role", event.target.value)}><option value="">All roles</option>{roles.map((role) => <option key={role}>{role}</option>)}</select></label>
      <label><span>Assigned device count</span><select aria-label="Assigned device count" value={filters.deviceCount} onChange={(event) => change("deviceCount", event.target.value)}>{countChoices.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
    </div>
    <div className="inventory-filter-actions"><div className="inventory-chips" aria-label="Active assignment filters">{[["search", "Search"], ["role", "Role"], ["deviceCount", "Device count"]].filter(([key]) => filters[key]).map(([key, label]) => <button type="button" key={key} aria-label={`Remove ${label} filter`} onClick={() => change(key, "")}>{label}: {filters[key]} <span aria-hidden="true">×</span></button>)}</div><button type="button" className="secondary-button" disabled={!active} onClick={() => setFilters({ ...emptyAssignmentFilters })}>Reset assignment filters</button><button type="button" className="secondary-button" disabled={!isLive || busy} onClick={() => setReload((value) => value + 1)}>Reload saved data</button></div>
    <p className="inventory-review-note">Each user has one Axon Role and may have multiple devices. Device counts are observations; an unusual count alone does not establish an exception.</p>
    {error && <p className="inventory-error" role="alert">{error} Use Reload saved data to retry.</p>}
<div className="table-shell large" aria-busy={busy}><table><caption>Users matching the assignment filters</caption><thead><tr>{["User", "Role", "Device count", "Assigned models", "Device states", "Review"].map((label) => <th key={label} scope="col">{label}</th>)}</tr></thead><tbody>{(data?.rows || []).map((row, index) => <tr key={`${row.userId}:${index}`}><td>{row.displayName || "Name not supplied"}<small>{row.externalId || row.userId}</small></td><td>{row.role || "Not supplied"}</td><td>{row.deviceCount ?? "Unavailable"}</td><td>{row.deviceModels}</td><td>{row.deviceStates}</td><td>{row.identityStatus !== "Exact Axon User ID" ? <span>{row.identityStatus}</span> : <button type="button" className="secondary-button" aria-expanded={selected?.userId === row.userId} aria-label={`View devices for ${row.displayName}`} onClick={(event) => { selectionTrigger.current = event.currentTarget; setSelection({ ...row, requestKey }); }}>View devices</button>}</td></tr>)}{!data?.rows.length && <tr><td colSpan="6">{busy ? "Loading users…" : error ? "Results unavailable." : !data?.userSnapshot ? "No saved Users snapshot loaded." : "No users match. Remove a filter or reset assignment filters."}</td></tr>}</tbody></table></div>
    <div className="crosswalk-pagination"><span aria-live="polite">{data?.userSnapshot ? `${data.total.toLocaleString()} matching users of ${data.scopeTotal.toLocaleString()} · Page ${data.page} of ${data.totalPages}` : "User totals unavailable"}</span><div><button type="button" className="secondary-button" disabled={!data || data.page <= 1} onClick={() => setFilters((current) => ({ ...current, page: data.page - 1 }))}>Previous</button><button type="button" className="secondary-button" disabled={!data || data.page >= data.totalPages} onClick={() => setFilters((current) => ({ ...current, page: data.page + 1 }))}>Next</button></div></div>
    {selected && data && <AssignmentDevices key={`${selected.userId}:${data.workspaceRevision}`} selection={selected} workspaceRevision={data.workspaceRevision} onClose={() => { setSelection(null); selectionTrigger.current?.focus(); }} />}
  </section>;
}
