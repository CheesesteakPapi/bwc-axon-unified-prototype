import { useEffect, useState } from "react";
import { localApi } from "./api.js";
import { emptyInventoryFilters, illustrativeInventoryView, inventoryFields, inventoryQuery } from "./inventoryView.js";

const scopeLabels = { full: "Full saved Devices baseline", filtered: "Filtered Devices snapshot", unavailable: "Devices snapshot unavailable", illustrative: "Illustrative inventory" };

export function InventoryWorkspace({ filters, setFilters, component, setComponent, isLive, liveData, demoRows, showToast }) {
  const [response, setResponse] = useState(null);
  const [failure, setFailure] = useState(null);
  const [reload, setReload] = useState(0);
  const [exporting, setExporting] = useState(false);
  const query = inventoryQuery(filters, component);
  const queryKey = JSON.stringify(query);
  const requestKey = `${queryKey}:${liveData.workspaceRevision}:${reload}`;
  useEffect(() => {
    if (!isLive) return undefined;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      localApi.inventory(JSON.parse(queryKey), controller.signal)
        .then((payload) => { if (!controller.signal.aborted) { setResponse({ key: requestKey, payload }); setFailure(null); } })
        .catch((error) => { if (!controller.signal.aborted) setFailure({ key: requestKey, message: error.message }); });
    }, 200);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [isLive, queryKey, requestKey]);

  const data = isLive ? response?.key === requestKey ? response.payload : null : illustrativeInventoryView(demoRows, query);
  const error = failure?.key === requestKey ? failure.message : "";
  const busy = isLive && !data && !error;
  const facets = data?.facets || (isLive ? response?.payload.facets || {} : illustrativeInventoryView(demoRows, query).facets);
  const active = [...inventoryFields.filter(([key]) => query[key]), ...(query.search ? [["search", "Search"]] : []), ...(query.exceptionsOnly ? [["exceptionsOnly", "Review flags only"]] : [])];
  const canExport = isLive && data && data.mode !== "unavailable" && !exporting;
  function change(key, value) {
    if (key === "component") setComponent(value || "All Components");
    setFilters((previous) => ({ ...previous, ...(key === "component" ? {} : { [key]: value }), page: 1 }));
  }
  function reset() { setFilters({ ...emptyInventoryFilters }); setComponent("All Components"); }
  async function exportView() {
    if (!canExport) return;
    setExporting(true);
    try {
      const file = await localApi.exportInventory({ ...query, expectedRevision: data.workspaceRevision });
      const url = URL.createObjectURL(file.blob);
      const link = document.createElement("a"); link.href = url; link.download = file.filename; link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      showToast(`Exported all ${data.total.toLocaleString()} matching devices with snapshot and filter details.`);
    } catch (error) { showToast(error.message); }
    finally { setExporting(false); }
  }
  return <section className="data-page inventory-workspace">
    <div className="page-heading"><div><p className="eyebrow">MANAGE · INVENTORY</p><h2>Find and review devices</h2><p>Combine filters across the saved snapshot. Export includes every matching device across all pages.</p></div>
      {isLive && <button type="button" className="primary-button" disabled={!canExport} onClick={exportView}>{exporting ? "Preparing CSV…" : "Export matching CSV"}</button>}
    </div>
    <div className="inventory-scope" role="status">
      <strong>{data ? scopeLabels[data.mode] : busy ? "Loading saved inventory…" : "Inventory could not be loaded"}</strong>
      {data?.deviceSnapshot && <span>Device snapshot: {new Date(data.deviceSnapshot.activatedAt).toLocaleString()} · {data.scopeTotal.toLocaleString()} devices · Workspace revision {data.workspaceRevision}</span>}
      {data?.mode === "filtered" && <span>API scope: {JSON.stringify(data.deviceSnapshot.scope.filters)}. Counts cover this filtered snapshot.</span>}
      {data?.mode === "unavailable" && <span>Open Connect to Axon and refresh Devices to make inventory available.</span>}
      {!isLive && <span>Example data for exploring filters. A saved Devices snapshot enables CSV export.</span>}
    </div>
    <div className="inventory-filter-grid" aria-label="Inventory filters">
      <label className="inventory-search"><span>Search inventory</span><input type="search" value={filters.search} maxLength={500} placeholder="Serial, device ID, assigned user, or location" onChange={(event) => change("search", event.target.value)} /></label>
      {inventoryFields.map(([key, label]) => {
        const choices = [...new Set([...(facets[key] || []), ...(query[key] ? [query[key]] : [])])].sort();
        return <label key={key}><span>{label}</span><select aria-label={label} value={query[key]} onChange={(event) => change(key, event.target.value)}><option value="">All</option>{choices.map((value) => <option key={value} value={value}>{value}</option>)}</select></label>;
      })}
      <label className="inventory-review-toggle"><input type="checkbox" checked={filters.exceptionsOnly} onChange={(event) => change("exceptionsOnly", event.target.checked)} /><span>Review flags only</span></label>
    </div>
    <div className="inventory-filter-actions"><div className="inventory-chips" aria-label="Active inventory filters">{active.map(([key, label]) => <button type="button" key={key} onClick={() => change(key, key === "exceptionsOnly" ? false : "")} aria-label={`Remove ${label} filter`}>{label}{key !== "exceptionsOnly" ? `: ${query[key]}` : ""} <span aria-hidden="true">×</span></button>)}</div>
      <button type="button" className="secondary-button" disabled={!active.length} onClick={reset}>Reset filters</button><button type="button" className="secondary-button" onClick={() => setReload((value) => value + 1)} disabled={!isLive || busy}>Reload saved data</button>
    </div>
    <p className="inventory-review-note">Review flags include unmapped sites, unassigned devices, inventory dispositions, and API errors. In-stock or unassigned devices may be expected; review their context.</p>
    {error && <p className="inventory-error" role="alert">{error} Use Reload saved data to retry.</p>}
    <div className="table-shell large" aria-busy={busy}><table><caption>Devices matching the current filters</caption><thead><tr>{["Serial / device ID", "Model", "Disposition", "Assignment", "Assigned user", "Device Home", "Component", "Mapped AOR", "Review flag"].map((label) => <th key={label} scope="col">{label}</th>)}</tr></thead>
      <tbody>{(data?.rows || []).map((row, index) => <tr key={`${row.deviceId}:${row.serialNumber}:${index}`}><td>{row.serialNumber || row.deviceId || "Not supplied"}</td><td>{row.model || "Not supplied"}</td><td>{row.disposition}</td><td>{row.assignmentState}</td><td>{row.assignedUser || "—"}</td><td>{row.deviceHome || "Not supplied"}</td><td>{row.component || "Unmapped"}</td><td>{row.regionAor || "Unmapped"}</td><td>{row.needsReview ? "Review" : "—"}</td></tr>)}
        {!data?.rows.length && <tr><td colSpan="9">{busy ? "Loading saved devices…" : error ? "Results unavailable while this view reloads." : data?.mode === "unavailable" ? "No Devices snapshot loaded." : "No devices match. Remove a filter or reset filters to widen the view."}</td></tr>}
      </tbody></table></div>
    <div className="crosswalk-pagination"><span aria-live="polite">{data && data.mode !== "unavailable" ? `${data.total.toLocaleString()} matches of ${data.scopeTotal.toLocaleString()} saved devices · Page ${data.page} of ${data.totalPages}` : "Device counts unavailable"}</span><div>
      <button type="button" className="secondary-button" disabled={!data || data.page <= 1 || exporting} onClick={() => setFilters((previous) => ({ ...previous, page: data.page - 1 }))}>Previous</button>
      <button type="button" className="secondary-button" disabled={!data || data.page >= data.totalPages || exporting} onClick={() => setFilters((previous) => ({ ...previous, page: data.page + 1 }))}>Next</button>
    </div></div>
  </section>;
}
