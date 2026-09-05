import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowLeftIcon,
  CheckCircledIcon,
  CheckIcon,
  ChevronDownIcon,
  ChevronRightIcon,
  Cross2Icon,
  CubeIcon,
  DashboardIcon,
  DownloadIcon,
  DrawingPinFilledIcon,
  DrawingPinIcon,
  ExclamationTriangleIcon,
  FileTextIcon,
  GearIcon,
  GlobeIcon,
  GroupIcon,
  HomeIcon,
  InfoCircledIcon,
  LayersIcon,
  Link2Icon,
  LockClosedIcon,
  MagnifyingGlassIcon,
  MixerHorizontalIcon,
  PersonIcon,
  ReaderIcon,
  ReloadIcon,
  StarFilledIcon,
  TableIcon,
} from "./vendor/radix-icons/dist/react-icons.esm.js";
import { localApi } from "./api.js";
import { InventoryWorkspace } from "./InventoryWorkspace.jsx";
import { emptyInventoryFilters } from "./inventoryView.js";
import { AssignmentWorkspace, emptyAssignmentFilters } from "./AssignmentWorkspace.jsx";

const navGroups = [
  { label: "MONITOR", items: [["dashboard", "Dashboard", HomeIcon], ["map", "Map", DrawingPinIcon], ["exceptions", "Exceptions", ExclamationTriangleIcon]] },
  { label: "MANAGE", items: [["crosswalk", "Crosswalks", DashboardIcon], ["facilities", "Facilities", DrawingPinFilledIcon], ["access", "Users & Access", PersonIcon], ["inventory", "Inventory", CubeIcon], ["assignments", "Device Assignments", GroupIcon]] },
  { label: "GOVERNANCE", items: [["reports", "Reports", FileTextIcon], ["provenance", "Data Provenance", ReaderIcon]] },
];

const illustrativeSummary = {
  totalDevices: 24,
  assignedDevices: 16,
  unassignedDevices: 8,
  inventoryExceptions: 4,
  mappedDevices: 18,
  mappingCompletion: 75,
  unmappedDeviceHomes: 3,
  totalUsers: 12,
  totalGroups: 6,
  regionCounts: { "Area Alpha": 2, "Area Beta": 1, "Area Gamma": 1 },
  dispositionCounts: { Assigned: 16, "In Stock": 3, Unassigned: 2, Lost: 1, Relinquished: 2 },
};

const baseMapMarkers = [
  { x: 22, y: 28, type: "sac", label: "Primary command example" },
  { x: 31, y: 48, type: "cluster", count: 2, region: "Area Alpha", label: "Area Alpha examples" },
  { x: 49, y: 37, type: "dsac", label: "Secondary command example" },
  { x: 62, y: 61, type: "cluster", count: 1, region: "Area Beta", label: "Area Beta example" },
  { x: 76, y: 44, type: "ra", label: "Regional office example" },
  { x: 83, y: 67, type: "cluster", count: 1, region: "Area Gamma", label: "Area Gamma mapping example", task: "mapping" },
];

const illustrativeCrosswalk = [
  { sourceType: "Device Home", sourceId: "Example Home Alpha", normalizedKey: "example home alpha", suggestedUnit: "Component A / Area Alpha", mappingMethod: "Synthetic normalized name", confidence: "Low", reviewNotes: "Synthetic fixture only; replace with a reviewed local mapping." },
  { sourceType: "Device Home", sourceId: "Example Home Beta", normalizedKey: "example home beta", suggestedUnit: "Component B / Area Beta", mappingMethod: "Synthetic geocode + name", confidence: "Medium", reviewNotes: "Synthetic fixture only; confirm all local geographic relationships." },
  { sourceType: "Axon Group", sourceId: "Example Training", normalizedKey: "group-example-training", suggestedUnit: "Non-site group", mappingMethod: "Synthetic group register", confidence: "Medium", reviewNotes: "Do not force enterprise, training, role, or administrative Groups into a Site ID." },
];

const illustrativeInventory = [
  { deviceId: "DEMO-DEVICE-001", serialNumber: "DEMO-001", model: "Body 4", disposition: "Assigned", assignmentState: "Assigned", assignedUser: "Example User 01", deviceHome: "Example Home Alpha", mappedSiteId: "DEMO-SITE-001", regionAor: "Area Alpha", needsReview: false },
  { deviceId: "DEMO-DEVICE-002", serialNumber: "DEMO-002", model: "Body 4", disposition: "In Stock", assignmentState: "Unassigned", assignedUser: "", deviceHome: "Example Home Alpha", mappedSiteId: "DEMO-SITE-002", regionAor: "Area Alpha", needsReview: true },
  { deviceId: "DEMO-DEVICE-003", serialNumber: "DEMO-003", model: "Body 3", disposition: "Lost", assignmentState: "Assigned", assignedUser: "Example User 02", deviceHome: "Example Home Beta", mappedSiteId: "", regionAor: "Area Beta", needsReview: true },
  { deviceId: "DEMO-DEVICE-004", serialNumber: "DEMO-004", model: "Fleet 3", disposition: "Relinquished", assignmentState: "Unassigned", assignedUser: "", deviceHome: "Example Home Gamma", mappedSiteId: "DEMO-SITE-003", regionAor: "Area Gamma", needsReview: true },
];

const illustrativeAssignments = [
  { userId: "DEMO-USER-01", displayName: "Example User 01", role: "Prototype User", primaryGroup: "Component A Area Alpha Users", secondaryGroup: "Prototype Operators", organizationalAreaGroups: "Component A Area Alpha", additionalGroupCount: 1, groupDataStatus: "Synthetic tier model", deviceCount: 2, deviceModels: "Body 4; Fleet 3", deviceStates: "Assigned: 2" },
  { userId: "DEMO-USER-02", displayName: "Example User 02", role: "Prototype Supervisor", primaryGroup: "Component B Area Beta Users", secondaryGroup: "Prototype Supervisors", organizationalAreaGroups: "Component B Area Beta", additionalGroupCount: 1, groupDataStatus: "Synthetic tier model", deviceCount: 1, deviceModels: "Body 3", deviceStates: "Assigned: 1" },
];

const emptyGovernanceSummary = {
  facilities: { total: 0, validated: 0, shared: 0, externallyHosted: 0, coLocated: 0, multiComponent: 0 },
  officePresences: { total: 0, linked: 0, unlinked: 0, networkPending: 0, nonIceOrLimitedNetwork: 0 },
  groups: { total: 0, classified: 0, primary: 0, secondary: 0, organizationalArea: 0, hierarchyLinks: 0 },
  siteGroupRelationships: { total: 0, mapped: 0 },
  axonWrite: false,
};

const mappingTrend = [
  { month: "Mar", value: 82 },
  { month: "Apr", value: 84 },
  { month: "May", value: 86 },
  { month: "Jun", value: 88 },
  { month: "Jul", value: 90 },
  { month: "Aug", value: 92 },
];

const mapViews = {
  "HSI Domestic AORs": {
    asset: "/assets/synthetic-coverage-map.svg",
    alt: "Synthetic geographic placeholder with no operational boundaries",
    source: "Synthetic placeholder",
    markerMode: "all",
    legendLabel: "HSI office hierarchy and BWC site legend",
  },
  "OCIO Areas": {
    asset: "/assets/synthetic-coverage-map.svg",
    alt: "Synthetic geographic placeholder with no operational boundaries",
    source: "Synthetic placeholder",
    markerMode: "sites",
    legendLabel: "OCIO area and BWC site legend",
  },
  "ERO Field Office AORs": {
    asset: "/assets/synthetic-coverage-map.svg",
    alt: "Synthetic geographic placeholder with no operational boundaries",
    source: "Synthetic placeholder",
    markerMode: "sites",
    legendLabel: "ERO field office and BWC site legend",
  },
  "HSI International": {
    asset: "/assets/synthetic-coverage-map.svg",
    alt: "Synthetic geographic placeholder with no operational boundaries",
    source: "Synthetic placeholder",
    markerMode: "none",
    legendLabel: "HSI International reference legend",
  },
};

const emptySession = { configured: false, partnerHint: "", dataMode: "illustrative", lastSyncAt: "", credentialsPersisted: false };
const emptyConfig = { exists: false, agencyBaseUrl: "", timeoutSeconds: 90, rawJsonEnabled: false, readOnly: true };

function number(value) {
  if (value === null || value === undefined) return "—";
  return Number(value).toLocaleString();
}

function percentage(value, decimals = 1) {
  if (value === null || value === undefined) return "—";
  return `${Number(value).toFixed(decimals)}%`;
}

function dataModeLabel(mode) {
  if (mode === "live") return "FULL BASELINE";
  if (mode === "filtered") return "FILTERED RESULT";
  if (mode === "partial") return "PARTIAL AXON DATA";
  return "ILLUSTRATIVE";
}

function formatTimestamp(value) {
  if (!value) return "Synthetic demonstration data · not an Axon snapshot";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : `Axon data refreshed · ${date.toLocaleString()}`;
}

function sleep(milliseconds) {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

function TrendChart() {
  const canvasRef = useRef(null);
  useEffect(() => {
    const canvas = canvasRef.current;
    const context = canvas.getContext("2d");
    const ratio = window.devicePixelRatio || 1;
    const width = canvas.clientWidth;
    const height = canvas.clientHeight;
    canvas.width = width * ratio;
    canvas.height = height * ratio;
    context.scale(ratio, ratio);
    context.clearRect(0, 0, width, height);
    context.strokeStyle = "#d5deea";
    [0.25, 0.5, 0.75].forEach((y) => { context.beginPath(); context.moveTo(42, height * y); context.lineTo(width - 18, height * y); context.stroke(); });
    const data = mappingTrend.map(({ value }) => value);
    const left = 42, right = width - 26, top = 22, bottom = height - 28;
    context.strokeStyle = "#0a4e9b";
    context.lineWidth = 3;
    context.beginPath();
    data.forEach((value, index) => {
      const x = left + (index * (right - left)) / (data.length - 1);
      const y = bottom - ((value - 75) / 25) * (bottom - top);
      if (index === 0) context.moveTo(x, y); else context.lineTo(x, y);
    });
    context.stroke();
    context.fillStyle = "#0a4e9b";
    context.font = "600 12px Segoe UI";
    data.forEach((value, index) => {
      const x = left + (index * (right - left)) / (data.length - 1);
      const y = bottom - ((value - 75) / 25) * (bottom - top);
      context.beginPath(); context.arc(x, y, 4, 0, Math.PI * 2); context.fill(); context.fillText(`${value}%`, x - 12, y - 10);
    });
    context.fillStyle = "#586a81";
    context.font = "12px Segoe UI";
    mappingTrend.forEach(({ month }, index) => { const x = left + (index * (right - left)) / 5; context.fillText(month, x - 11, height - 8); });
  }, []);
  return <figure className="trend-chart" aria-labelledby="trend-caption"><canvas ref={canvasRef} aria-hidden="true" /><figcaption id="trend-caption" className="sr-only">Illustrative mapping completion increased from 82 percent in March to 92 percent in August 2026.<table><caption>Monthly mapping completion values</caption><thead><tr><th>Month</th><th>Completion</th></tr></thead><tbody>{mappingTrend.map(({ month, value }) => <tr key={month}><td>{month} 2026</td><td>{value}%</td></tr>)}</tbody></table></figcaption></figure>;
}

function DispositionPanel({ counts }) {
  const entries = Object.entries(counts || {}).sort((a, b) => b[1] - a[1]).slice(0, 5);
  const total = entries.reduce((sum, [, value]) => sum + value, 0) || 1;
  return <div className="disposition-list">{entries.map(([label, value]) => <div key={label}><span>{label}</span><progress max={total} value={value} aria-label={`${label}: ${value}`} /><strong>{number(value)}</strong></div>)}</div>;
}

function Sidebar({ page, setPage, exceptionCount, collapsed, setCollapsed }) {
  const [mobileOpen, setMobileOpen] = useState(false);
  function choosePage(key) {
    setPage(key);
    setMobileOpen(false);
  }
  return <aside className={`sidebar ${collapsed ? "collapsed" : ""} ${mobileOpen ? "mobile-open" : ""}`} aria-label="Primary navigation">
    <div className="brand-block"><strong>BWC</strong><span>Geographic Operations</span><button type="button" className="mobile-menu-button" aria-expanded={mobileOpen} aria-controls="primary-navigation-menu" onClick={() => setMobileOpen((current) => !current)}><TableIcon aria-hidden="true" /><span>{mobileOpen ? "Close menu" : "Open menu"}</span></button></div>
    <nav id="primary-navigation-menu">{navGroups.map((group) => <div className="nav-group" key={group.label}><div className="nav-label">{group.label}</div>{group.items.map(([key, label, Icon]) => {
      const active = page === key || (key === "access" && page === "access-groups") || (key === "reports" && page === "report-preview");
      return <button key={key} type="button" className={`nav-item ${active ? "active" : ""}`} onClick={() => choosePage(key)} aria-label={label} aria-current={active ? "page" : undefined}><Icon aria-hidden="true" /><span>{label}</span>{key === "exceptions" && <span className="nav-badge">{exceptionCount}</span>}</button>;
    })}</div>)}</nav>
    <button type="button" className={`nav-item settings ${page === "settings" ? "active" : ""}`} onClick={() => choosePage("settings")} aria-label="Settings" aria-current={page === "settings" ? "page" : undefined}><GearIcon aria-hidden="true" /><span>Settings</span></button>
    <button type="button" className="collapse-button" aria-label={`${collapsed ? "Expand" : "Collapse"} primary navigation`} aria-expanded={!collapsed} onClick={() => setCollapsed((current) => !current)}>{collapsed ? <ChevronRightIcon aria-hidden="true" /> : <ArrowLeftIcon aria-hidden="true" />}<span>{collapsed ? "Expand" : "Collapse"}</span></button>
  </aside>;
}

function AppHeader({ page, component, setComponent, orgView, setOrgView, isLive, dataMode, session, backendAvailable, onOpenConnection }) {
  const mapScoped = ["dashboard", "map", "report-preview"].includes(page);
  const componentScoped = isLive && ["dashboard", "map", "report-preview"].includes(page);
  const scopeCopy = page === "crosswalk" ? "Filters are inside Crosswalk Review" : page === "facilities" ? "Local facility governance" : ["access", "access-groups"].includes(page) ? "Users, roles, and Groups" : page === "assignments" ? "All observed assignments" : page === "reports" ? "Exports preserve their stated scope" : page === "provenance" ? "All loaded sources" : page === "settings" ? "Local preferences" : "Current workflow";
  return <header className={`topbar ${mapScoped || componentScoped ? "has-scope-controls" : "scope-compact"}`}>
    <div className="title-block"><div className="title-line"><h1>BWC Geographic Operations</h1><span className={`data-mode ${isLive ? "live" : "demo"}`}>{dataModeLabel(dataMode)}</span></div><p>{formatTimestamp(session.lastSyncAt)} <InfoCircledIcon aria-label="Data freshness information" /></p></div>
    {componentScoped && <label className="select-control"><span>Component <small>Dashboard, map, inventory</small></span><select value={component} onChange={(event) => setComponent(event.target.value)}><option>All Components</option><option>HSI</option><option>ERO</option><option>OCIO</option></select></label>}
    {mapScoped && <label className="select-control wide"><span>Organizational View <small>Map and report only</small></span><select value={orgView} onChange={(event) => setOrgView(event.target.value)}><option>HSI Domestic AORs</option><option>OCIO Areas</option><option>ERO Field Office AORs</option><option>HSI International</option></select></label>}
    {!mapScoped && !componentScoped && <div className="header-scope-note"><strong>Page scope</strong><span>{scopeCopy}</span></div>}
    <button type="button" className={`connection-button ${session.configured ? "configured" : ""}`} onClick={onOpenConnection}><Link2Icon /><span><strong>{session.configured ? `Axon connected ${session.partnerHint}` : backendAvailable ? "Connect to Axon" : "Offline preview"}</strong><small>{dataMode === "filtered" ? "Filtered result; full baseline unchanged" : isLive ? "Refresh or change filters" : session.configured ? "Ready for read-only pull" : "Local session setup"}</small></span></button>
  </header>;
}

function SyncJobBanner({ job, onOpen, onCancel }) {
  if (!job || !["queued", "running", "cancel-requested"].includes(job.status)) return null;
  const completed = job.completedResources?.length || 0;
  const total = job.resources?.length || 0;
  const count = Object.values(job.resourceCounts || {}).reduce((sum, value) => sum + Number(value || 0), 0);
  return <section className="sync-job-banner" role="status" aria-label="Axon pull progress"><ReloadIcon className="spinning" /><div><strong>{job.phase || "Read-only Axon pull in progress"}</strong><span>{completed} of {total} resources complete · {number(count)} records received{job.currentPage ? ` · page ${job.currentPage}` : ""}</span></div><button type="button" className="secondary-button" onClick={onOpen}>View details</button><button type="button" className="text-danger" onClick={onCancel} disabled={job.status === "cancel-requested"}>{job.status === "cancel-requested" ? "Stopping safely…" : "Stop after request"}</button></section>;
}

function FilterPopover({ filters, onApply, onClose }) {
  const [reviewState, setReviewState] = useState(filters.reviewState);
  useEffect(() => { setReviewState(filters.reviewState); }, [filters.reviewState]);
  useEffect(() => {
    function closeOnEscape(event) { if (event.key === "Escape") onClose(); }
    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [onClose]);
  return <div id="view-filter-popover" className="filter-popover" role="dialog" aria-label="Additional view filters"><div className="popover-heading"><strong>Local display filters</strong><button type="button" onClick={onClose} aria-label="Close filters"><Cross2Icon /></button></div>
    <p className="filter-note">This filter changes the visible Crosswalk Review list. To reduce Axon Device API time, use the model, status2, or homeId filters in Pull Axon data.</p>
    <label><span>Crosswalk review state</span><select value={reviewState} onChange={(event) => setReviewState(event.target.value)}><option>All states</option><option>Needs review</option><option>Mapped</option></select></label>
    <button type="button" className="secondary-button" onClick={() => { onApply({ reviewState }); onClose(); }}>Apply view filter</button>
  </div>;
}

function ConnectionModal({ open, backendAvailable, config, session, syncJob, onClose, onSave, onPull, onClear }) {
  const dialogRef = useRef(null);
  const closeButtonRef = useRef(null);
  const onCloseRef = useRef(onClose);
  const [agencyBaseUrl, setAgencyBaseUrl] = useState(config.agencyBaseUrl || "");
  const [timeoutSeconds, setTimeoutSeconds] = useState(config.timeoutSeconds || 90);
  const [partnerId, setPartnerId] = useState("");
  const [clientId, setClientId] = useState("");
  const [clientSecret, setClientSecret] = useState("");
  const [resources, setResources] = useState(["DeviceHomes", "Groups", "Users", "Devices"]);
  const [deviceModel, setDeviceModel] = useState("");
  const [deviceStatus, setDeviceStatus] = useState("");
  const [deviceHomeId, setDeviceHomeId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => { onCloseRef.current = onClose; }, [onClose]);
  useEffect(() => { setAgencyBaseUrl(config.agencyBaseUrl || ""); setTimeoutSeconds(config.timeoutSeconds || 90); }, [config]);
  useEffect(() => {
    if (!open) return undefined;
    const previousFocus = document.activeElement;
    closeButtonRef.current?.focus();
    function handleDialogKeys(event) {
      if (event.key === "Escape") {
        event.preventDefault();
        onCloseRef.current();
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = [...(dialogRef.current?.querySelectorAll('button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])') || [])];
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    }
    document.addEventListener("keydown", handleDialogKeys);
    return () => {
      document.removeEventListener("keydown", handleDialogKeys);
      if (previousFocus instanceof HTMLElement) previousFocus.focus();
    };
  }, [open]);
  if (!open) return null;
  const running = syncJob && ["queued", "running", "cancel-requested"].includes(syncJob.status);

  function toggleResource(name) {
    setResources((current) => current.includes(name) ? current.filter((item) => item !== name) : [...current, name]);
  }

  async function save(pullAfter) {
    setBusy(true); setError("");
    try {
      await onSave({ agencyBaseUrl, timeoutSeconds }, { partnerId, clientId, clientSecret });
      if (pullAfter) await onPull({ resources, deviceModel, deviceStatus, deviceHomeId });
      setPartnerId(""); setClientId(""); setClientSecret("");
    } catch (caught) {
      setError(caught.message);
    } finally {
      setBusy(false);
    }
  }

  return <div className="modal-backdrop" role="presentation"><section ref={dialogRef} className="connection-modal" role="dialog" aria-modal="true" aria-labelledby="connection-title">
    <div className="modal-heading"><div><p className="eyebrow">READ-ONLY LOCAL CONNECTION</p><h2 id="connection-title">Connect and pull Axon data</h2><p>Credentials stay in memory for this session. Resource calls are GET-only; the only POST to Axon requests an OAuth token.</p></div><button ref={closeButtonRef} type="button" onClick={onClose} aria-label="Close connection settings"><Cross2Icon /></button></div>
    {!backendAvailable && <div className="inline-alert"><ExclamationTriangleIcon /><span>Live connection requires the packaged Python launcher. The design preview remains illustrative.</span></div>}
    <div className="connection-grid">
      <div className="connection-section"><h3>1. Connection</h3>
        <label><span>Axon Evidence tenant URL</span><input value={agencyBaseUrl} onChange={(event) => setAgencyBaseUrl(event.target.value)} placeholder="https://your-agency.evidence.com" autoComplete="url" /></label>
        <label><span>Partner / Agency ID</span><input value={partnerId} onChange={(event) => setPartnerId(event.target.value)} placeholder={session.configured ? `Active for ${session.partnerHint}; leave blank to keep` : "Required for this session"} autoComplete="off" /></label>
        <label><span>Client ID</span><input value={clientId} onChange={(event) => setClientId(event.target.value)} placeholder={session.configured ? "Active; leave blank to keep" : "Required for this session"} autoComplete="off" /></label>
        <label><span>Client Secret</span><input type="password" value={clientSecret} onChange={(event) => setClientSecret(event.target.value)} placeholder={session.configured ? "Active; leave blank to keep" : "Required for this session"} autoComplete="new-password" /></label>
        <label><span>Request timeout (seconds)</span><input type="number" min="15" max="600" value={timeoutSeconds} onChange={(event) => setTimeoutSeconds(event.target.value)} /></label>
        <div className="security-note"><LockClosedIcon /><span>Secrets, tokens, and live rows are never written to config.json. Raw JSON retention is forced off.</span></div>
      </div>
      <div className="connection-section"><h3>2. Read-only pull</h3>
        <fieldset><legend>Resources</legend>{["DeviceHomes", "Groups", "Users", "Devices"].map((name) => <label className="check-row" key={name}><input type="checkbox" checked={resources.includes(name)} onChange={() => toggleResource(name)} /> {name}</label>)}</fieldset>
        <label><span>Device model</span><input value={deviceModel} onChange={(event) => setDeviceModel(event.target.value)} placeholder="One model or comma-separated exact model strings" /></label>
        <label><span>Exact device status2</span><input value={deviceStatus} onChange={(event) => setDeviceStatus(event.target.value)} placeholder="Optional exact Axon value" /></label>
        <label><span>Exact Device Home ID</span><input value={deviceHomeId} onChange={(event) => setDeviceHomeId(event.target.value)} placeholder="Optional exact Axon homeId" /></label>
        <div className="pacing-note"><InfoCircledIcon /><span>The Device API is automatically paced to one request every five seconds. Model filtering is sent to Axon before pagination and can materially reduce pull time.</span></div>
        {syncJob && <div className={`sync-progress ${syncJob.status}`} role="status"><ReloadIcon className={running ? "spinning" : ""} /><div><strong>{syncJob.phase}</strong><span>{syncJob.completedResources?.length || 0} of {syncJob.resources?.length || resources.length} resources complete{syncJob.currentResource ? ` · ${syncJob.currentResource} page ${syncJob.currentPage || 1} · ${number(syncJob.receivedRecords || 0)} records` : ""}</span>{syncJob.error && <span className="error-text">{syncJob.error}</span>}</div></div>}
      </div>
    </div>
    {error && <div className="inline-alert error" role="alert"><ExclamationTriangleIcon /><span>{error}</span></div>}
    <div className="modal-actions"><button type="button" className="text-danger" onClick={onClear} disabled={!session.configured || busy || running}>Clear session credentials</button><span /><button type="button" className="secondary-button" onClick={() => save(false)} disabled={!backendAvailable || busy || running}>Save connection</button><button type="button" className="primary-button" onClick={() => save(true)} disabled={!backendAvailable || busy || running}>{running ? <ReloadIcon className="spinning" /> : <DownloadIcon />} {running ? "Pulling…" : "Pull selected data"}</button></div>
  </section></div>;
}

function Marker({ marker, selectedMarker, onSelect }) {
  const selected = selectedMarker?.label === marker.label;
  if (marker.type === "cluster") return <button type="button" className={`map-marker cluster ${selected ? "selected" : ""}`} style={{ left: `${marker.x}%`, top: `${marker.y}%` }} aria-label={`${marker.count} ${marker.label}`} onClick={() => onSelect(marker)}>{marker.count}</button>;
  const Icon = marker.type === "sac" ? StarFilledIcon : marker.type === "dsac" ? CubeIcon : DrawingPinFilledIcon;
  return <button type="button" className={`map-marker office ${marker.type} ${selected ? "selected" : ""}`} style={{ left: `${marker.x}%`, top: `${marker.y}%` }} aria-label={`Open details for ${marker.label}`} title={marker.label} onClick={() => onSelect(marker)}><Icon /></button>;
}

function MapLegend({ orgView, label }) {
  if (orgView === "HSI Domestic AORs") return <div className="map-legend" aria-label={label}><div><StarFilledIcon className="legend-sac" /> SAC</div><div><CubeIcon className="legend-dsac" /> DSAC</div><div><DrawingPinFilledIcon className="legend-ra" /> RA</div><div><DrawingPinIcon /> Physical BWC site</div></div>;
  if (orgView === "OCIO Areas") return <div className="map-legend" aria-label={label}><div><LayersIcon /> Region / area reference</div><div><DrawingPinIcon /> Physical BWC site</div><div><ExclamationTriangleIcon /> Review queue</div></div>;
  if (orgView === "ERO Field Office AORs") return <div className="map-legend" aria-label={label}><div><StarFilledIcon /> Field office / AOR reference</div><div><CubeIcon /> Supporting office reference</div><div><DrawingPinIcon /> Physical BWC site</div></div>;
  return <div className="map-legend" aria-label={label}><div><GlobeIcon /> International reference coverage</div><div><InfoCircledIcon /> No domestic site overlay</div></div>;
}

function MapPanel({ selectedMarker, onMarkerSelect, orgView, summary, isLive }) {
  const [zoom, setZoom] = useState(1);
  const view = mapViews[orgView] || mapViews["HSI Domestic AORs"];
  const isInternational = orgView === "HSI International";
  useEffect(() => { setZoom(1); }, [orgView]);
  const hasDeviceScope = summary.totalDevices !== null && summary.totalDevices !== undefined;
  const markers = baseMapMarkers
    .map((marker) => marker.type === "cluster" && isLive && hasDeviceScope ? { ...marker, count: Number(summary.regionCounts?.[marker.region] || 0) } : marker)
    .filter((marker) => (!isLive || hasDeviceScope || marker.type !== "cluster") && (view.markerMode === "all" || (view.markerMode === "sites" && marker.type === "cluster")));
  return <section className="map-panel" aria-labelledby="map-heading"><div className="map-heading-row"><h2 id="map-heading">{orgView}</h2><span>{view.source} · {isLive && !isInternational ? hasDeviceScope ? "Axon device overlay in the stated scope" : "Device overlay unavailable until Devices are refreshed" : "Synthetic reference"}</span><span className="source-state provisional">Governed boundary layer: Not bundled</span><span className="source-state provisional">Local validation required</span></div>
    <div className="map-canvas" aria-label={`${orgView} interactive reference map`}><div className="map-scene" style={{ transform: `scale(${zoom})` }}><img src={view.asset} alt={view.alt} />{markers.map((marker, index) => <Marker key={`${marker.label}-${index}`} marker={marker} selectedMarker={selectedMarker} onSelect={onMarkerSelect} />)}</div>{isInternational && <div className="map-scope-note"><GlobeIcon aria-hidden="true" /><span><strong>Separate international scope</strong> Domestic BWC site markers are intentionally excluded until a reviewed international crosswalk is approved.</span></div>}<div className="map-tools" aria-label="Map controls"><button type="button" aria-label="Zoom in" onClick={() => setZoom((current) => Math.min(1.3, Number((current + 0.15).toFixed(2))))} disabled={zoom >= 1.3}>+</button><button type="button" aria-label="Zoom out" onClick={() => setZoom((current) => Math.max(1, Number((current - 0.15).toFixed(2))))} disabled={zoom <= 1}>−</button><button type="button" aria-label="Recenter map" onClick={() => setZoom(1)}><DrawingPinIcon /></button></div><span className="sr-only" aria-live="polite">Map zoom {Math.round(zoom * 100)} percent</span><MapLegend orgView={orgView} label={view.legendLabel} /><div className="map-disclaimer"><InfoCircledIcon aria-hidden="true" /> Illustrative organizational layer — not for legal or operational boundary decisions</div></div>
  </section>;
}

function buildTasks(summary, isLive) {
  const homesAvailable = summary.unmappedDeviceHomes !== null && summary.unmappedDeviceHomes !== undefined;
  const devicesAvailable = summary.inventoryExceptions !== null && summary.inventoryExceptions !== undefined;
  const groupsAvailable = summary.totalGroups !== null && summary.totalGroups !== undefined;
  return [
    { id: "mapping", rank: 1, tone: "critical", title: homesAvailable ? `${number(summary.unmappedDeviceHomes)} unmapped Device Homes` : "Device Home metrics unavailable", subtitle: homesAvailable ? "Observed API names awaiting reviewed crosswalk" : "Refresh Device Homes or Devices before review", owner: "Crosswalk Team", status: homesAvailable ? "Open" : "Unavailable" },
    { id: "devices", rank: 2, tone: "warning", title: devicesAvailable ? `${number(summary.inventoryExceptions)} device exceptions` : "Device exceptions unavailable", subtitle: devicesAvailable ? "Assignment, disposition, error, or mapping review" : "Refresh Devices before review", owner: "Inventory Team", status: devicesAvailable ? "Open" : "Unavailable" },
    { id: "groups", rank: 3, tone: "info", title: groupsAvailable ? `${number(summary.totalGroups)} Groups observed` : "Group metrics unavailable", subtitle: groupsAvailable ? "Classification, tier, hierarchy, and site relationship review" : "Refresh Groups before review", owner: "Governance Team", status: groupsAvailable ? isLive ? "Pulled" : "Illustrative" : "Unavailable" },
  ];
}

function TaskRail({ selectedTask, setSelectedTask, openCrosswalk, openTasks, summary, isLive }) {
  const tasks = buildTasks(summary, isLive);
  return <aside className="task-rail" aria-label="Selected area priority tasks"><div className="task-heading"><h2>{isLive ? "Current Axon data scope" : selectedTask ? "Selected synthetic area" : "No area selected"}</h2><button type="button" aria-label="Clear selected area" onClick={() => setSelectedTask("")} disabled={!selectedTask}><Cross2Icon /></button></div><h3>PRIORITY TASKS</h3><div className="task-list">{tasks.map((task) => <button type="button" key={task.id} className={`task-card ${task.tone} ${selectedTask === task.id ? "selected" : ""}`} onClick={() => setSelectedTask(task.id)}><span className="task-rank">{task.rank}</span><span className="task-copy"><strong>{task.title}</strong><small>{task.subtitle}</small><small>Owner: {task.owner}</small></span><span className="task-status">{task.status}</span><ChevronRightIcon /></button>)}</div><button type="button" className="text-action" onClick={openTasks}>View all snapshot tasks <ChevronRightIcon /></button><button type="button" className="rail-primary" onClick={openCrosswalk}>Review affected mappings <ChevronRightIcon /></button></aside>;
}

function ProvenanceStrip({ liveData, isLive }) {
  const counts = liveData.resourceCounts || {};
  const scopeCopy = liveData.mode === "filtered"
    ? "Filtered Axon result; not the confirmed full-device baseline"
    : liveData.mode === "partial"
      ? "Partial Axon resources; device metrics unavailable"
      : isLive ? "Confirmed full Axon baseline" : "Illustrative";
  return <section className="provenance-strip" aria-label="Data provenance summary"><div><span>Data mode</span><strong className={isLive ? "good" : "provisional-text"}>{scopeCopy}</strong></div><div><span>Last refresh</span><strong>{isLive ? new Date(liveData.lastSyncAt).toLocaleString() : "Aug 28, 2026"}</strong></div><div><span>Resource rows</span><strong>{isLive ? `D ${number(counts.Devices)} · U ${number(counts.Users)} · G ${number(counts.Groups)}` : "Illustrative dataset"}</strong></div><div><span>Boundary validation</span><strong className="provisional-text">Provisional</strong></div><div className="calculation"><span>Calculation</span><strong>{liveData.mode === "partial" ? "Run a full Devices refresh to calculate device metrics" : "Mapping completion = devices with reviewed Site ID ÷ devices in the stated scope"}</strong></div><InfoCircledIcon /></section>;
}

function PendingOverlayPanel({ data }) {
  const [state, setState] = useState("All pending states");
  const pending = data.pendingUsers || [];
  if (!pending.length) return null;
  const visible = state === "All pending states" ? pending : pending.filter((row) => row.state === state);
  const projected = data.projectedSummary || {};
  return <section className="pending-overlay-panel" aria-label="Provisioning changes pending Axon confirmation"><div className="pending-overlay-heading"><div><p className="eyebrow">SHARED WORKSPACE · PROVISIONING OVERLAY</p><h2>Provisioning changes are visible, but not confirmed Axon truth</h2><p>Confirmed metrics remain unchanged. The projected user total is shown separately.</p></div><div className="pending-projection"><span>Confirmed Users</span><strong>{number(projected.confirmedUsers)}</strong><span>Baseline + Pending</span><strong>{number(projected.baselinePlusPendingUsers)}</strong></div></div><div className="pending-toolbar"><label><span>Provisioning state</span><select value={state} onChange={(event) => setState(event.target.value)}><option>All pending states</option><option>Confirmed</option><option>Proposed creation</option><option>Proposed update</option><option>Submitted—awaiting confirmation</option><option>Failed</option><option>Superseded</option></select></label><span>Workspace revision {data.workspaceRevision || 0} · {visible.length} visible</span></div><div className="table-shell"><table><caption className="sr-only">Provisioning user overlays from the shared workspace</caption><thead><tr><th>User</th><th>State</th><th>Role</th><th>Group</th><th>Location</th><th>Personnel AOR</th><th>Run revision</th></tr></thead><tbody>{visible.slice(0, 25).map((row, index) => <tr key={`${row.runId}-${row.email}-${index}`}><td>{row.name || row.email}<small>{row.email}</small></td><td><span className="source-state provisional">{row.state}</span></td><td>{row.role || "—"}</td><td>{row.group || "—"}</td><td>{row.location || "—"}</td><td>{row.personnelAor || "—"}</td><td>{row.runId} · R{row.runRevision}</td></tr>)}</tbody></table></div>{pending.length > 25 && <p className="pending-limit">Showing the first 25 overlay rows. Use Provisioning Center for run-level editing and review.</p>}</section>;
}

function Dashboard({ selectedTask, setSelectedTask, setPage, orgView, liveData, isLive, summary }) {
  const isFiltered = liveData.mode === "filtered";
  const isPartial = liveData.mode === "partial";
  const assignedPercent = summary.totalDevices
    ? percentage((summary.assignedDevices / summary.totalDevices) * 100)
    : isPartial ? "—" : "0.0%";
  const exceptionPercent = summary.totalDevices
    ? percentage((summary.inventoryExceptions / summary.totalDevices) * 100)
    : isPartial ? "—" : "0.0%";
  const metricScope = isFiltered ? "within the filtered result" : isPartial ? "full Devices baseline required" : "of devices in the full baseline";
  return <div className="dashboard-page">
    {!isLive && <div className="illustrative-banner" role="note"><InfoCircledIcon /><span><strong>Demo data — no tenant snapshot loaded.</strong> Metrics, map markers, and resolved items are illustrative.</span></div>}
    {isFiltered && <div className="illustrative-banner" role="note"><InfoCircledIcon /><span><strong>Filtered device result — not a confirmed full baseline.</strong> These device metrics apply only to the selected API filters. Run an unfiltered Devices refresh to establish confirmed dashboard totals.</span></div>}
    {isPartial && <div className="illustrative-banner" role="note"><InfoCircledIcon /><span><strong>Partial Axon data — device metrics are unavailable.</strong> Run a full Devices refresh before using inventory, assignment, or readiness totals.</span></div>}
    <section className="summary-grid" aria-label="Readiness summary"><div className="attention-card"><span className="attention-icon"><ExclamationTriangleIcon /></span><div><small>NEEDS ATTENTION</small><strong>{number(summary.unmappedDeviceHomes)} unmapped Device Homes</strong><span>{isLive ? "in the current Axon resource scope" : "in illustrative data"}</span></div><button type="button" onClick={() => setPage("crosswalk")}>Review mappings <ChevronRightIcon /></button></div><div className="metric"><span className="metric-icon blue"><PersonIcon /></span><div><strong>{number(summary.assignedDevices)}</strong><span>Assigned Devices</span><small>{assignedPercent} {metricScope}</small></div></div><div className="metric"><span className="metric-icon amber"><ExclamationTriangleIcon /></span><div><strong>{number(summary.inventoryExceptions)}</strong><span>Inventory Exceptions</span><small>{exceptionPercent} {metricScope}</small></div></div><div className="metric"><span className="metric-icon green"><LayersIcon /></span><div><strong>{percentage(summary.mappingCompletion, isLive ? 1 : 0)}</strong><span>Mapping Completion</span><small>{number(summary.mappedDevices)} devices with reviewed Site ID · {metricScope}</small></div></div></section>
    <div className="dashboard-main"><MapPanel selectedMarker={null} onMarkerSelect={(marker) => setSelectedTask(marker.task || (marker.type === "cluster" ? "devices" : "mapping"))} orgView={orgView} summary={summary} isLive={isLive} /><TaskRail selectedTask={selectedTask} setSelectedTask={setSelectedTask} openCrosswalk={() => setPage("crosswalk")} openTasks={() => setPage("exceptions")} summary={summary} isLive={isLive} /></div>
    <div className="dashboard-bottom"><section className="panel trend-panel"><div className="panel-heading"><h2>{isFiltered ? "Filtered Device Disposition" : isPartial ? "Device Disposition Unavailable" : isLive ? "Device Disposition Snapshot" : "Mapping Completion Trend"}</h2><span>{isLive ? `${number(summary.totalDevices)} devices` : "Last 6 months"}</span><InfoCircledIcon /></div>{isPartial ? <p className="pending-limit">A full Devices baseline is required for disposition metrics.</p> : isLive ? <DispositionPanel counts={summary.dispositionCounts} /> : <TrendChart />}</section><section className="panel resolved-panel"><div className="panel-heading"><h2>{isLive ? "Axon Resource Coverage" : "Recently Resolved in Southeast"}</h2></div>{isLive ? <ul><li><CheckCircledIcon />Device Homes <time>{number(liveData.resourceCounts?.DeviceHomes)} rows</time></li><li><CheckCircledIcon />Axon Groups <time>{number(liveData.resourceCounts?.Groups)} rows</time></li><li><CheckCircledIcon />Users and roles <time>{number(liveData.resourceCounts?.Users)} rows</time></li><li><CheckCircledIcon />Devices and assignments <time>{number(liveData.resourceCounts?.Devices)} rows</time></li></ul> : <ul><li><CheckCircledIcon />Devices mapped to new floor plan <time>Aug 27, 3:42 PM ET</time></li><li><CheckCircledIcon />Inventory exception cleared <time>Aug 27, 10:18 AM ET</time></li><li><CheckCircledIcon />Site certification completed <time>Aug 26, 4:05 PM ET</time></li></ul>}</section></div><ProvenanceStrip liveData={liveData} isLive={isLive} />
  </div>;
}

const crosswalkTables = {
  "approved-roles": { label: "Approved Axon Role catalog", shortLabel: "Axon Roles", supportsCreate: true, createLabel: "Add role", createTitle: "Add a reviewed Axon Role", createDescription: "Use the exact tenant Role name. Role approval is distinct from Entra group membership." },
  "personnel-aor": { label: "Personnel Location-to-AOR", shortLabel: "Personnel AOR", supportsCreate: true, createLabel: "Add location rule", createTitle: "Add a personnel Location-to-AOR rule", createDescription: "Personnel Location and AOR govern Axon Group recommendations; device location is comparison-only." },
  "job-categories": { label: "Exact job-title categories", shortLabel: "Job Categories", supportsCreate: true, createLabel: "Add job title", createTitle: "Classify an exact directory job title", createDescription: "Map only an exact observed title to Standard User, First-Line Supervisor, or Senior/Second-Line Supervisor." },
  "group-rules": { label: "Component/AOR/Job Group rules", shortLabel: "Group Rules", supportsCreate: true, createLabel: "Add Group rule", createTitle: "Add an optional Group recommendation rule", createDescription: "A rule may remain unreviewed, and Group Name may remain blank. Selected Groups must resolve against the current Axon Group master; never construct an unverified external ID." },
  "directory-attributes": { label: "Directory attribute mapping", shortLabel: "Directory Attributes" },
  "device-homes": { label: "Device Home table", shortLabel: "Device Homes" },
  "axon-groups": { label: "Axon Group table", shortLabel: "Axon Groups" },
  "non-site-groups": { label: "Non-site Group register", shortLabel: "Non-site Groups", supportsCreate: true, createLabel: "Add non-site Group", createTitle: "Add a non-site Group", createDescription: "Use this legacy-compatible register for observed command, role-related, training, enterprise, or administrative Groups that do not belong to a physical office location." },
  "facility-master": { label: "Facility Master", shortLabel: "Facilities", supportsCreate: true, createLabel: "Add facility", createTitle: "Add a physical facility", createDescription: "Create a reviewed physical building or campus record. Do not combine offices based on address similarity alone." },
  "office-presences": { label: "Office Presence register", shortLabel: "Office Presences" },
  "group-master": { label: "Tiered Group Master", shortLabel: "Group Master", supportsCreate: true, createLabel: "Add observed Group", createTitle: "Add an observed Axon Group", createDescription: "Record the exact observed Group first, then classify its purpose, tier, parent, organizational area, and site relationship." },
  "site-group-relationships": { label: "Site-to-Group relationships", shortLabel: "Site-to-Group Relationships", supportsCreate: true, createLabel: "Add relationship", createTitle: "Add a site-to-Group relationship", createDescription: "Connect an observed Group to an Office Location ID or reviewed Facility ID without treating user records as site evidence." },
};

const crosswalkSelectOptions = {
  "Mapping Status": ["Unmapped", "Candidate", "Needs review", "Mapped", "No match"],
  "Mapping Method": ["Not assessed", "Observed ID", "Exact name", "Normalized name", "Command hierarchy review", "Manual exception"],
  Confidence: ["Not rated", "Low", "Medium", "High"],
  "Group Classification": ["Command", "Role-related", "Training", "Enterprise", "Administrative", "Other non-site"],
  "Command Hierarchy Level": ["Enterprise", "Component", "Region / AOR", "Field office", "Suboffice", "Function", "Not applicable"],
  "Reporting Inclusion": ["Include", "Exclude", "Context only", "Pending review"],
};

const newRowDefaultsByTable = {
  "non-site-groups": { "Mapping Status": "Pending classification", "Reporting Inclusion": "Pending review" },
  "facility-master": { "Shared Facility": "Pending review", "Ownership / Occupancy Type": "Pending review", "Geocoding Status": "Not geocoded", "Validation Status": "Draft", "Mapping Method": "Not assessed", Confidence: "Not rated" },
  "group-master": { "Group Status": "Unknown", "Mapping Status": "Unclassified", Confidence: "Not rated" },
  "site-group-relationships": { "Mapping Status": "Pending review", "Mapping Method": "Not assessed", Confidence: "Not rated" },
};

function CrosswalkReviewQueue({ rows, isLive, defaultReviewState, onOpenTable }) {
  const [status, setStatus] = useState(defaultReviewState === "Mapped" ? "Reviewed" : defaultReviewState === "All states" ? "All records" : "Exceptions");
  const [search, setSearch] = useState("");
  const [selectedKey, setSelectedKey] = useState(rows[0]?.normalizedKey || rows[0]?.sourceId || "");
  useEffect(() => { setSelectedKey(rows[0]?.normalizedKey || rows[0]?.sourceId || ""); }, [rows]);
  useEffect(() => { setStatus(defaultReviewState === "Mapped" ? "Reviewed" : defaultReviewState === "All states" ? "All records" : "Exceptions"); }, [defaultReviewState]);
  const visibleRows = useMemo(() => rows.filter((row) => {
    const searchMatch = !search || Object.values(row).join(" ").toLowerCase().includes(search.toLowerCase());
    const reviewed = String(row.reviewStatus || "").toLowerCase() === "reviewed";
    const statusMatch = status === "All records" || (status === "Reviewed" ? reviewed : !reviewed);
    return searchMatch && statusMatch;
  }), [rows, search, status]);
  const selected = visibleRows.find((row) => (row.normalizedKey || row.sourceId) === selectedKey) || visibleRows[0];
  useEffect(() => {
    if (selected) setSelectedKey(selected.normalizedKey || selected.sourceId);
  }, [selected?.normalizedKey, selected?.sourceId]);
  function chooseRow(key, event) {
    if (event && !["Enter", " "].includes(event.key)) return;
    if (event) event.preventDefault();
    setSelectedKey(key);
  }
  return <>
    <div className="page-toolbar"><label><span>Mapping status</span><select value={status} onChange={(event) => setStatus(event.target.value)}><option>Exceptions</option><option>All records</option><option>Reviewed</option></select></label><label className="search-control"><MagnifyingGlassIcon /><input aria-label="Search crosswalk records" placeholder="Search home, group, site, city, or ID" value={search} onChange={(event) => setSearch(event.target.value)} /></label><span className="toolbar-chip">{isLive ? "Axon snapshot" : "Southeast AOR"}</span><span className="toolbar-chip critical">{visibleRows.length} review records</span></div>
    <div className="review-layout"><div className="table-shell"><table role="grid"><caption className="sr-only">Crosswalk records. Select a row to review its mapping basis.</caption><thead><tr><th>Source type</th><th>Observed source</th><th>Suggested organizational unit</th><th>Mapping method</th><th>Confidence</th></tr></thead><tbody>{visibleRows.map((row) => { const key = row.normalizedKey || row.sourceId; return <tr key={`${row.sourceType}-${key}`} className={selectedKey === key ? "selected keyboard-selectable" : "keyboard-selectable"} tabIndex="0" aria-selected={selectedKey === key} onClick={() => chooseRow(key)} onKeyDown={(event) => chooseRow(key, event)}><td>{row.sourceType}</td><td>{row.sourceId}</td><td>{row.suggestedUnit}</td><td>{row.mappingMethod}</td><td><span className={`confidence ${String(row.confidence).toLowerCase().replace(" ", "-")}`}>{row.confidence}</span></td></tr>; })}{!visibleRows.length && <tr><td colSpan="5">No crosswalk records match the current filters.</td></tr>}</tbody></table></div>
      <aside className="record-detail">{selected ? <><div className="record-title"><DrawingPinIcon /><div><span>Selected {selected.sourceType}</span><h3>{selected.sourceId}</h3></div></div><dl><div><dt>Observed source</dt><dd>{selected.sourceId}</dd></div><div><dt>Normalized key / ID</dt><dd>{selected.normalizedKey || "—"}</dd></div><div><dt>Suggested organizational unit</dt><dd>{selected.suggestedUnit}</dd></div><div><dt>Mapping method</dt><dd>{selected.mappingMethod}</dd></div><div><dt>Review basis</dt><dd>{selected.reviewNotes}</dd></div></dl><div className="review-queue-note"><InfoCircledIcon /><span>This is a triage snapshot. Record and save the governed decision in the editable shared-workspace table.</span></div><div className="detail-actions"><button type="button" className="primary-button" onClick={() => onOpenTable(selected.sourceType === "Device Home" ? "device-homes" : "axon-groups")}><TableIcon /> Open editable table</button>{selected.sourceType === "Axon Group" && selected.suggestedUnit === "Non-site group" && <button type="button" className="secondary-button" onClick={() => onOpenTable("non-site-groups")}>Open non-site register</button>}</div></> : <p>No review records match the current filters.</p>}</aside>
    </div>
  </>;
}

function recordIdentity(row) {
  return row.values["Site ID"] || row.values["Office Location ID"] || row.values["Facility ID"] || row.values["Group Name"] || row.values["Axon Group Name"] || row.values["Axon Group ID"] || `Row ${row.rowNumber}`;
}

function recordContext(row) {
  return [row.values.Component, row.values["Region / AOR"], row.values["Office Name"], row.values.City, row.values.State, row.values["Group Tier"], row.values["Group Purpose"]].filter(Boolean).slice(0, 3).join(" · ") || "Governed local record";
}

function recordStatus(row, drafts) {
  const values = { ...row.values, ...(drafts[row.rowNumber] || {}) };
  return values["Mapping Status"] || values["Facility Link Status"] || values["Validation Status"] || values["Group Status"] || "Needs review";
}

function CrosswalkEditor({ tableKey, backendAvailable, showToast, onDirtyChange, onSaved }) {
  const newRowDefaults = newRowDefaultsByTable[tableKey] || {};
  const [payload, setPayload] = useState(null);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [appliedSearch, setAppliedSearch] = useState("");
  const [drafts, setDrafts] = useState({});
  const [selectedRowNumber, setSelectedRowNumber] = useState(0);
  const [bulkSelected, setBulkSelected] = useState([]);
  const [bulkLink, setBulkLink] = useState({ facilityId: "", mappingMethod: "Manual exception", confidence: "Medium", reviewNotes: "" });
  const [savingRow, setSavingRow] = useState(0);
  const [savingAll, setSavingAll] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [creating, setCreating] = useState(false);
  const [newValues, setNewValues] = useState(newRowDefaults);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [reloadToken, setReloadToken] = useState(0);
  const pendingCount = Object.values(drafts).filter((changes) => Object.keys(changes).length).length;
  const newRowDirty = showCreate && Object.entries(newValues).some(([field, value]) => String(value || "") !== String(newRowDefaults[field] || ""));
  const unsavedRows = pendingCount + (newRowDirty ? 1 : 0);
  const hasUnsaved = unsavedRows > 0;

  useEffect(() => { onDirtyChange(hasUnsaved); }, [hasUnsaved, onDirtyChange]);
  useEffect(() => () => onDirtyChange(false), [onDirtyChange]);
  useEffect(() => {
    if (!backendAvailable) return undefined;
    let active = true;
    setLoading(true); setError("");
    localApi.crosswalk(tableKey, { page, pageSize: 25, search: appliedSearch }).then((result) => {
      if (!active) return;
      setPayload(result);
      setSelectedRowNumber((current) => result.rows.some((row) => row.rowNumber === current) ? current : result.rows[0]?.rowNumber || 0);
      setBulkSelected([]);
    }).catch((caught) => {
      if (active) setError(caught.message);
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, [tableKey, page, appliedSearch, backendAvailable, reloadToken]);
  useEffect(() => {
    function warnAboutDrafts(event) {
      if (!hasUnsaved) return;
      event.preventDefault();
      event.returnValue = "";
    }
    window.addEventListener("beforeunload", warnAboutDrafts);
    return () => window.removeEventListener("beforeunload", warnAboutDrafts);
  }, [hasUnsaved]);

  function updateDraft(row, field, value) {
    setDrafts((current) => {
      const next = { ...current };
      const changes = { ...(next[row.rowNumber] || {}) };
      if (value === String(row.values[field] ?? "")) delete changes[field]; else changes[field] = value;
      if (Object.keys(changes).length) next[row.rowNumber] = changes; else delete next[row.rowNumber];
      return next;
    });
  }

  async function persistRow(row, quiet = false) {
    const changes = drafts[row.rowNumber] || {};
    if (!Object.keys(changes).length) return null;
    const expected = Object.fromEntries(Object.entries(row.values).map(([field, value]) => [field, String(value ?? "")]));
    const result = await localApi.saveCrosswalkRow(tableKey, row.rowNumber, changes, expected);
    setPayload((current) => ({ ...current, rows: current.rows.map((item) => item.rowNumber === row.rowNumber ? result.row : item) }));
    setDrafts((current) => { const next = { ...current }; delete next[row.rowNumber]; return next; });
    if (!quiet) showToast(result.projectionWarning || `Saved ${recordIdentity(row)} to the shared workspace. The prior CSV projection was preserved as ${result.backupFileName}.`);
    return result;
  }

  async function saveRow(row, advance = false) {
    setSavingRow(row.rowNumber); setError("");
    try {
      await persistRow(row);
      onSaved?.();
      if (advance) {
        const index = rows.findIndex((item) => item.rowNumber === row.rowNumber);
        setSelectedRowNumber(rows[Math.min(index + 1, rows.length - 1)]?.rowNumber || row.rowNumber);
      }
    } catch (caught) {
      setError(caught.message);
    } finally {
      setSavingRow(0);
    }
  }

  async function saveAll() {
    const changedRows = rows.filter((row) => Object.keys(drafts[row.rowNumber] || {}).length);
    if (!changedRows.length) return;
    setSavingAll(true); setError("");
    let saved = 0;
    let projectionWarnings = 0;
    try {
      for (const row of changedRows) {
        const result = await persistRow(row, true);
        if (result?.projectionWarning) projectionWarnings += 1;
        saved += 1;
      }
      onSaved?.();
      showToast(projectionWarnings
        ? `Saved ${saved} shared-workspace record${saved === 1 ? "" : "s"}; ${projectionWarnings} CSV projection refresh${projectionWarnings === 1 ? " needs" : "es need"} attention.`
        : `Saved ${saved} shared-workspace record${saved === 1 ? "" : "s"}. Each prior CSV projection was preserved in the backup folder.`);
    } catch (caught) {
      setError(`${saved} record${saved === 1 ? "" : "s"} saved before the next record failed: ${caught.message}`);
    } finally {
      setSavingAll(false);
    }
  }

  function stageBulkFacilityLink() {
    if (!bulkSelected.length) { showToast("Select at least one office presence."); return; }
    if (!bulkLink.facilityId.trim() || !bulkLink.reviewNotes.trim()) { showToast("Enter an existing Facility ID and review notes before staging the link."); return; }
    const selectedRows = rows.filter((row) => bulkSelected.includes(row.rowNumber));
    setDrafts((current) => {
      const next = { ...current };
      selectedRows.forEach((row) => {
        next[row.rowNumber] = {
          ...(next[row.rowNumber] || {}),
          "Facility ID": bulkLink.facilityId.trim(),
          "Facility Link Status": "Linked",
          "Mapping Method": bulkLink.mappingMethod,
          Confidence: bulkLink.confidence,
          "Review Notes": bulkLink.reviewNotes.trim(),
        };
      });
      return next;
    });
    showToast(`Staged one reviewed facility link for ${selectedRows.length} office presence${selectedRows.length === 1 ? "" : "s"}. Review the changed records, then Save all changes.`);
  }

  async function createRow(event) {
    event.preventDefault();
    setCreating(true); setError("");
    try {
      const result = await localApi.addCrosswalkRow(tableKey, newValues);
      setNewValues(newRowDefaults);
      setShowCreate(false); setPage(result.rowNumber ? Math.ceil(result.rowNumber / 25) : 1); setAppliedSearch(""); setSearch(""); setReloadToken((value) => value + 1);
      onSaved?.();
      showToast(result.projectionWarning || `Added ${result.row.values["Facility Name"] || result.row.values["Group Name"] || result.row.values["Office Location ID"] || "the governed record"} to the shared workspace. The prior CSV projection was preserved as ${result.backupFileName}.`);
    } catch (caught) {
      setError(caught.message);
    } finally {
      setCreating(false);
    }
  }

  function fieldControl(row, field) {
    const currentValue = String(drafts[row.rowNumber]?.[field] ?? row.values[field] ?? "");
    const controlledOptions = payload?.fieldOptions?.[field] || crosswalkSelectOptions[field];
    if (controlledOptions) {
      const options = [...new Set([currentValue, ...controlledOptions].filter(Boolean))];
      return <select value={currentValue} onChange={(event) => updateDraft(row, field, event.target.value)}>{options.map((option) => <option key={option}>{option}</option>)}</select>;
    }
    if (field === "Review Notes") return <textarea rows="4" value={currentValue} onChange={(event) => updateDraft(row, field, event.target.value)} />;
    return <input value={currentValue} onChange={(event) => updateDraft(row, field, event.target.value)} />;
  }

  function submitSearch(event) {
    event.preventDefault();
    if (hasUnsaved) { showToast("Save or discard staged changes before searching."); return; }
    setPage(1); setAppliedSearch(search.trim());
  }

  if (!backendAvailable) return <div className="inline-alert crosswalk-local-alert"><ExclamationTriangleIcon /><span>Editable governance tables require the packaged macOS or Windows launcher. The browser-only preview cannot update the shared workspace.</span></div>;
  const rows = payload?.rows || [];
  const editableFields = payload?.editableFields || [];
  const editable = new Set(editableFields);
  const lockedColumns = (payload?.columns || []).filter((column) => !editable.has(typeof column === "string" ? column : column.key));
  const selectedRow = rows.find((row) => row.rowNumber === selectedRowNumber) || rows[0];
  const selectedDirty = Boolean(selectedRow && Object.keys(drafts[selectedRow.rowNumber] || {}).length);
  return <div className="crosswalk-editor">
    <div className="local-edit-notice"><LockClosedIcon /><div><strong>Focused shared-workspace editing</strong><span>Changes commit to the authoritative shared SQLite workspace. {payload?.fileName || "The governed CSV"} is refreshed as a review/export projection, and every save creates a timestamped CSV backup. Axon remains read-only.</span></div>{hasUnsaved && <><span className="toolbar-chip critical" aria-live="polite">{unsavedRows} staged row{unsavedRows === 1 ? "" : "s"}</span><button type="button" className="primary-button save-all-button" disabled={savingAll} onClick={saveAll}>{savingAll ? "Saving…" : "Save all changes"}</button></>}</div>
    <form className="page-toolbar crosswalk-editor-toolbar" onSubmit={submitSearch}>
      <label className="search-control"><MagnifyingGlassIcon /><input aria-label={`Search ${crosswalkTables[tableKey].shortLabel} table`} placeholder={tableKey === "facility-master" ? "Search facility, host, city, ownership, or notes" : tableKey === "office-presences" ? "Search Office Location ID, component, facility, network, or office" : tableKey === "non-site-groups" || tableKey === "group-master" ? "Search Group ID, name, tier, hierarchy, or notes" : tableKey === "site-group-relationships" ? "Search Office Location ID, Facility ID, Group ID, or relationship" : "Search Site ID, office, API name, or Group ID"} value={search} onChange={(event) => setSearch(event.target.value)} /></label>
      <button type="submit" className="secondary-button">Search</button>
      <button type="button" className="secondary-button" onClick={() => { if (hasUnsaved) { showToast("Save or discard staged changes before reloading."); return; } setReloadToken((value) => value + 1); }}><ReloadIcon /> Reload</button>
      {crosswalkTables[tableKey].supportsCreate && <button type="button" className="primary-button" onClick={() => { if (showCreate && newRowDirty) { showToast("Use Cancel to discard the unfinished local row."); return; } setShowCreate((value) => !value); }}>{showCreate ? <Cross2Icon /> : <TableIcon />} {showCreate ? "Close new row" : crosswalkTables[tableKey].createLabel}</button>}
      {hasUnsaved ? <button type="button" className="secondary-button export-button" onClick={() => showToast("Save or reset staged changes before exporting the governed CSV.")}><DownloadIcon /> Export full CSV</button> : <a className="secondary-button export-button" href={localApi.crosswalkExportUrl(tableKey)}><DownloadIcon /> Export full CSV</a>}
      <span className="toolbar-chip">{payload ? `${payload.total.toLocaleString()} rows` : "Loading rows"}</span>
    </form>
    {error && <div className="inline-alert crosswalk-error" role="alert"><ExclamationTriangleIcon /><span>{error}</span></div>}
    {tableKey === "office-presences" && payload && <section className="bulk-link-panel" aria-labelledby="bulk-link-title"><div><strong id="bulk-link-title">Link reviewed co-located offices together</strong><span>Select office presences below, then stage one existing Facility ID and one documented review basis for all selected offices. Address or city similarity never creates a link automatically.</span></div><label><span>Existing Facility ID</span><input value={bulkLink.facilityId} onChange={(event) => setBulkLink((current) => ({ ...current, facilityId: event.target.value }))} /></label><label><span>Mapping method</span><select value={bulkLink.mappingMethod} onChange={(event) => setBulkLink((current) => ({ ...current, mappingMethod: event.target.value }))}>{crosswalkSelectOptions["Mapping Method"].map((option) => <option key={option}>{option}</option>)}</select></label><label><span>Confidence</span><select value={bulkLink.confidence} onChange={(event) => setBulkLink((current) => ({ ...current, confidence: event.target.value }))}>{crosswalkSelectOptions.Confidence.map((option) => <option key={option}>{option}</option>)}</select></label><label className="bulk-notes"><span>Review notes</span><input value={bulkLink.reviewNotes} onChange={(event) => setBulkLink((current) => ({ ...current, reviewNotes: event.target.value }))} /></label><button type="button" className="secondary-button" onClick={stageBulkFacilityLink}>Stage link for {bulkSelected.length} selected</button></section>}
    {showCreate && payload && <form className="new-crosswalk-row" onSubmit={createRow}><div className="new-row-heading"><div><strong>{crosswalkTables[tableKey].createTitle}</strong><span>{crosswalkTables[tableKey].createDescription} Required identity and evidence fields are validated before the shared workspace changes.</span></div><span className="toolbar-chip">Shared workspace</span></div><div className="new-row-grid">{editableFields.map((field) => { const options = payload.fieldOptions?.[field] || crosswalkSelectOptions[field]; return <label key={field}><span>{field}</span>{options ? <select value={newValues[field] || ""} onChange={(event) => setNewValues((current) => ({ ...current, [field]: event.target.value }))}><option value="">Select…</option>{options.map((option) => <option key={option}>{option}</option>)}</select> : field === "Review Notes" ? <textarea rows="3" value={newValues[field] || ""} onChange={(event) => setNewValues((current) => ({ ...current, [field]: event.target.value }))} /> : <input value={newValues[field] || ""} onChange={(event) => setNewValues((current) => ({ ...current, [field]: event.target.value }))} />}</label>; })}</div><div className="new-row-actions"><button type="submit" className="primary-button" disabled={creating}>{creating ? "Adding…" : "Validate and add"}</button><button type="button" className="secondary-button" onClick={() => { setShowCreate(false); setNewValues(newRowDefaults); }}>Cancel</button></div></form>}
    {loading && <div className="crosswalk-loading" role="status">Loading the local governance table…</div>}
    {!loading && payload && <div className="governance-editor-layout"><section className="governance-record-list" aria-label={`${crosswalkTables[tableKey].label} records`}><div className="record-list-heading"><div><strong>Records</strong><span>Select one to review and edit</span></div>{tableKey === "office-presences" && <span>{bulkSelected.length} selected</span>}</div>{rows.length ? <ul>{rows.map((row) => { const dirty = Boolean(Object.keys(drafts[row.rowNumber] || {}).length); const checked = bulkSelected.includes(row.rowNumber); return <li key={row.rowNumber} className={`${selectedRow?.rowNumber === row.rowNumber ? "selected" : ""} ${dirty ? "dirty" : ""}`}>{tableKey === "office-presences" && <label className="record-checkbox"><input type="checkbox" checked={checked} aria-label={`Select ${recordIdentity(row)} for facility linking`} onChange={(event) => setBulkSelected((current) => event.target.checked ? [...current, row.rowNumber] : current.filter((value) => value !== row.rowNumber))} /></label>}<button type="button" onClick={() => setSelectedRowNumber(row.rowNumber)} aria-current={selectedRow?.rowNumber === row.rowNumber ? "true" : undefined}><span><strong>{recordIdentity(row)}</strong><small>{recordContext(row)}</small></span><span className={`record-status ${dirty ? "changed" : ""}`}>{dirty ? "Changed" : recordStatus(row, drafts)}</span></button></li>; })}</ul> : <p className="empty-record-list">No rows match the current search.</p>}</section><section className="governance-detail-editor" aria-live="polite">{selectedRow ? <><div className="detail-editor-heading"><div><span>Selected record</span><h3>{recordIdentity(selectedRow)}</h3><p>{recordContext(selectedRow)}</p></div>{selectedDirty && <span className="toolbar-chip critical">Unsaved changes</span>}</div><details className="locked-source-fields"><summary><LockClosedIcon /> Source and locked fields</summary><dl>{lockedColumns.map((column) => { const key = typeof column === "string" ? column : column.key; return <div key={key}><dt>{key}</dt><dd>{selectedRow.values[key] || "—"}</dd></div>; })}</dl></details><form onSubmit={(event) => { event.preventDefault(); saveRow(selectedRow); }}><div className="detail-field-grid">{editableFields.map((field) => <label key={field}><span>{field}</span>{fieldControl(selectedRow, field)}</label>)}</div><div className="detail-editor-actions"><button type="submit" className="primary-button" disabled={!selectedDirty || savingRow === selectedRow.rowNumber}><CheckIcon /> {savingRow === selectedRow.rowNumber ? "Saving…" : "Save record"}</button><button type="button" className="secondary-button" disabled={!selectedDirty || savingRow === selectedRow.rowNumber} onClick={() => saveRow(selectedRow, true)}>Save and next</button><button type="button" className="secondary-button" disabled={!selectedDirty || savingRow === selectedRow.rowNumber} onClick={() => setDrafts((current) => { const next = { ...current }; delete next[selectedRow.rowNumber]; return next; })}>Reset</button></div></form></> : <p>Select a record to review.</p>}</section></div>}
    {payload && <div className="crosswalk-pagination"><span>Page {payload.page} of {payload.totalPages || 1}</span><div><button type="button" className="secondary-button" disabled={payload.page <= 1 || hasUnsaved} onClick={() => setPage((value) => Math.max(1, value - 1))}>Previous</button><button type="button" className="secondary-button" disabled={payload.page >= payload.totalPages || hasUnsaved} onClick={() => setPage((value) => value + 1)}>Next</button></div>{hasUnsaved && <small>Save or reset staged changes before changing pages.</small>}</div>}
  </div>;
}

function CrosswalkPage({ setPage, showToast, rows, isLive, defaultReviewState, backendAvailable, onDirtyChange }) {
  const [workspace, setWorkspace] = useState("review");
  const [tableDirty, setTableDirty] = useState(false);
  useEffect(() => { onDirtyChange(tableDirty); }, [tableDirty, onDirtyChange]);
  useEffect(() => () => onDirtyChange(false), [onDirtyChange]);
  function switchWorkspace(next) {
    if (tableDirty && next !== workspace) { showToast("Save or reset unsaved crosswalk changes before switching tables."); return; }
    setWorkspace(next);
  }
  function handleTabKey(event) {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const keys = ["review", ...Object.keys(crosswalkTables)];
    const currentIndex = keys.indexOf(workspace);
    const nextIndex = event.key === "Home" ? 0 : event.key === "End" ? keys.length - 1 : event.key === "ArrowRight" ? (currentIndex + 1) % keys.length : (currentIndex - 1 + keys.length) % keys.length;
    if (tableDirty) { showToast("Save or reset unsaved crosswalk changes before switching tables."); return; }
    setWorkspace(keys[nextIndex]);
    window.setTimeout(() => document.getElementById(`crosswalk-tab-${keys[nextIndex]}`)?.focus(), 0);
  }
  return <section className="data-page crosswalk-workspace">
    <div className="page-heading"><div><p className="eyebrow">MANAGE · LOCAL WORKSPACE</p><h2>Crosswalk Workspace</h2><p>Review provisional matches or edit the governed Device Home and Axon Group tables in the shared workspace.</p></div><button type="button" className="secondary-button" onClick={() => tableDirty ? showToast("Save or reset unsaved crosswalk changes before leaving the workspace.") : setPage("dashboard")}><ArrowLeftIcon /> Back to dashboard</button></div>
    <div className="workspace-tabs" role="tablist" aria-label="Crosswalk workspace views" onKeyDown={handleTabKey}><button id="crosswalk-tab-review" type="button" role="tab" aria-controls="crosswalk-workspace-panel" aria-selected={workspace === "review"} tabIndex={workspace === "review" ? 0 : -1} className={workspace === "review" ? "active" : ""} onClick={() => switchWorkspace("review")}><DashboardIcon /> Review queue</button>{Object.entries(crosswalkTables).map(([key, definition]) => <button id={`crosswalk-tab-${key}`} type="button" role="tab" aria-controls="crosswalk-workspace-panel" aria-selected={workspace === key} tabIndex={workspace === key ? 0 : -1} className={workspace === key ? "active" : ""} onClick={() => switchWorkspace(key)} key={key}><TableIcon /> {definition.label}</button>)}</div>
    <div id="crosswalk-workspace-panel" role="tabpanel" aria-labelledby={`crosswalk-tab-${workspace}`}>{workspace === "review" ? <CrosswalkReviewQueue rows={rows} isLive={isLive} defaultReviewState={defaultReviewState} onOpenTable={switchWorkspace} /> : <CrosswalkEditor key={workspace} tableKey={workspace} backendAvailable={backendAvailable} showToast={showToast} onDirtyChange={setTableDirty} />}</div>
  </section>;
}

function GovernanceMetric({ icon: Icon, value, label, detail, tone = "blue" }) {
  return <article className="governance-metric"><span className={`metric-icon ${tone}`}><Icon /></span><div><strong>{number(value)}</strong><span>{label}</span><small>{detail}</small></div></article>;
}

function FacilitiesPage({ backendAvailable, governanceSummary, showToast, onDirtyChange, onSaved }) {
  const [workspace, setWorkspace] = useState("facility-master");
  const [tableDirty, setTableDirty] = useState(false);
  const tabs = ["facility-master", "office-presences"];
  useEffect(() => { onDirtyChange(tableDirty); }, [tableDirty, onDirtyChange]);
  useEffect(() => () => onDirtyChange(false), [onDirtyChange]);
  function switchWorkspace(next) {
    if (tableDirty) { showToast("Save or reset unsaved facility changes before switching tables."); return; }
    setWorkspace(next);
  }
  function handleTabKey(event) {
    if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
    event.preventDefault();
    const currentIndex = tabs.indexOf(workspace);
    const nextIndex = event.key === "ArrowRight" ? (currentIndex + 1) % tabs.length : (currentIndex - 1 + tabs.length) % tabs.length;
    switchWorkspace(tabs[nextIndex]);
    window.setTimeout(() => document.getElementById(`facilities-tab-${tabs[nextIndex]}`)?.focus(), 0);
  }
  const facilities = governanceSummary.facilities || emptyGovernanceSummary.facilities;
  const offices = governanceSummary.officePresences || emptyGovernanceSummary.officePresences;
  return <section className="data-page governance-workspace">
    <div className="page-heading"><div><p className="eyebrow">MANAGE · FACILITY GOVERNANCE</p><h2>Facilities & Office Presence</h2><p>Separate physical buildings from the component offices, host organizations, and network environments operating inside them.</p></div><span className="source-state provisional">Local reviewed model</span></div>
    <div className="governance-metric-grid" aria-label="Facility governance summary">
      <GovernanceMetric icon={DrawingPinFilledIcon} value={facilities.total} label="Facilities created" detail={`${facilities.validated || 0} validated`} />
      <GovernanceMetric icon={LayersIcon} value={offices.total} label="Office locations preserved" detail="Existing Site IDs retained" tone="green" />
      <GovernanceMetric icon={Link2Icon} value={offices.unlinked} label="Unlinked office locations" detail="Facility review required" tone="amber" />
      <GovernanceMetric icon={GlobeIcon} value={offices.networkPending} label="Network status pending" detail={`${offices.nonIceOrLimitedNetwork || 0} non-ICE, mixed, limited, or offline`} tone="amber" />
      <GovernanceMetric icon={GroupIcon} value={facilities.coLocated} label="Confirmed co-located facilities" detail={`${facilities.multiComponent || 0} with multiple ICE components`} />
      <GovernanceMetric icon={HomeIcon} value={facilities.externallyHosted} label="Externally hosted facilities" detail={`${facilities.shared || 0} shared facilities total`} tone="blue" />
    </div>
    <div className="notice facility-model-note"><InfoCircledIcon /><div><strong>Copy-first location model</strong><p>An Office Location ID represents a component office. A Facility ID represents the physical building or campus. Multiple Office Location IDs may share one reviewed Facility ID; address similarity alone never creates a co-location link.</p></div></div>
    <div className="workspace-tabs" role="tablist" aria-label="Facility governance tables" onKeyDown={handleTabKey}>{tabs.map((key) => <button id={`facilities-tab-${key}`} type="button" role="tab" aria-controls="facilities-workspace-panel" aria-selected={workspace === key} tabIndex={workspace === key ? 0 : -1} className={workspace === key ? "active" : ""} onClick={() => switchWorkspace(key)} key={key}>{key === "facility-master" ? <DrawingPinFilledIcon /> : <LayersIcon />}{crosswalkTables[key].label}</button>)}</div>
    <div id="facilities-workspace-panel" role="tabpanel" aria-labelledby={`facilities-tab-${workspace}`}><CrosswalkEditor key={workspace} tableKey={workspace} backendAvailable={backendAvailable} showToast={showToast} onDirtyChange={setTableDirty} onSaved={onSaved} /></div>
  </section>;
}

function UsersAccessTable({ rows, isLive, showToast }) {
  const [search, setSearch] = useState("");
  const [roleFilter, setRoleFilter] = useState("All roles");
  const [selectedId, setSelectedId] = useState(rows[0]?.userId || "");
  useEffect(() => { if (!rows.some((row) => row.userId === selectedId)) setSelectedId(rows[0]?.userId || ""); }, [rows, selectedId]);
  const roles = ["All roles", ...new Set(rows.map((row) => row.role).filter(Boolean))];
  const visibleRows = rows.filter((row) => {
    const matchesSearch = !search || Object.values(row).join(" ").toLowerCase().includes(search.toLowerCase());
    return matchesSearch && (roleFilter === "All roles" || row.role === roleFilter);
  });
  const selected = visibleRows.find((row) => row.userId === selectedId) || visibleRows[0];
  function choose(row, event) {
    if (event && !["Enter", " "].includes(event.key)) return;
    if (event) event.preventDefault();
    setSelectedId(row.userId);
  }
  function exportCurrent() {
    const headers = ["User", "Role", "Primary Group", "Secondary Group", "Organizational Area Groups", "Additional Group Count", "Device Count", "Group Data Status"];
    const body = visibleRows.map((row) => [row.displayName, row.role, row.primaryGroup, row.secondaryGroup, row.organizationalAreaGroups, row.additionalGroupCount, row.deviceCount === null || row.deviceCount === undefined ? "Unavailable" : row.deviceCount, row.groupDataStatus]);
    const csv = [headers, ...body].map((record) => record.map((value) => `"${String(value ?? "").replaceAll('"', '""')}"`).join(",")).join("\r\n");
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    const link = document.createElement("a"); link.href = url; link.download = "bwc-user-role-group-review.csv"; link.click(); window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    showToast("User role and Group review CSV exported for the current filtered view.");
  }
  return <>
    <div className="page-toolbar"><label className="search-control"><MagnifyingGlassIcon /><input aria-label="Search users and access" placeholder="Search user, role, Group, organizational area, or device count" value={search} onChange={(event) => setSearch(event.target.value)} /></label><label><span>Role</span><select value={roleFilter} onChange={(event) => setRoleFilter(event.target.value)}>{roles.map((role) => <option key={role}>{role}</option>)}</select></label><button type="button" className="secondary-button export-button" onClick={exportCurrent}><DownloadIcon /> Export current view</button><span className="toolbar-chip">{visibleRows.length} users</span></div>
    {isLive && <div className="notice access-contract-note"><InfoCircledIcon /><div><strong>Current read-only Users contract</strong><p>Role is observed as one user profile field. Primary, secondary, and organizational-area memberships remain blank unless a reviewed source exposes them; the application does not infer them from names or sites.</p></div></div>}
    <div className="access-review-layout"><div className="table-shell"><table><caption className="sr-only">Users with one role, tiered Group memberships, and device counts.</caption><thead><tr><th>User</th><th>Role</th><th>Primary Group</th><th>Secondary Group</th><th>Organizational area</th><th>Devices</th></tr></thead><tbody>{visibleRows.map((row) => <tr key={row.userId} className={selected?.userId === row.userId ? "selected keyboard-selectable" : "keyboard-selectable"} tabIndex="0" aria-selected={selected?.userId === row.userId} onClick={() => choose(row)} onKeyDown={(event) => choose(row, event)}><td>{row.displayName}</td><td>{row.role || <span className="provisional-text">Needs review</span>}</td><td>{row.primaryGroup || "Not observed"}</td><td>{row.secondaryGroup || "—"}</td><td>{row.organizationalAreaGroups || "Not observed"}</td><td>{row.deviceCount === null || row.deviceCount === undefined ? "Unavailable" : row.deviceCount}</td></tr>)}{!visibleRows.length && <tr><td colSpan="6">No users match the current filters.</td></tr>}</tbody></table></div><aside className="record-detail access-detail">{selected ? <><div className="record-title"><PersonIcon /><div><span>Selected user</span><h3>{selected.displayName}</h3></div></div><dl><div><dt>One active role</dt><dd>{selected.role || "Needs review"}</dd></div><div><dt>Primary user Group</dt><dd>{selected.primaryGroup || "Not observed"}</dd></div><div><dt>Secondary user Group</dt><dd>{selected.secondaryGroup || "Not observed"}</dd></div><div><dt>Organizational-area Groups</dt><dd>{selected.organizationalAreaGroups || "Not observed"}</dd></div><div><dt>Additional Groups</dt><dd>{selected.additionalGroupCount || 0}</dd></div><div><dt>Assigned devices</dt><dd>{selected.deviceCount === null || selected.deviceCount === undefined ? "Unavailable — full Devices baseline required" : `${selected.deviceCount} · ${selected.deviceModels || "—"}`}</dd></div><div><dt>Membership source status</dt><dd>{selected.groupDataStatus || "Needs review"}</dd></div></dl></> : <p>No user selected.</p>}</aside></div>
  </>;
}

function UsersAccessPage({ rows, isLive, backendAvailable, governanceSummary, showToast, onDirtyChange, onSaved, initialWorkspace = "users" }) {
  const [workspace, setWorkspace] = useState(initialWorkspace);
  const [tableDirty, setTableDirty] = useState(false);
  const tabs = ["users", "group-master", "site-group-relationships"];
  useEffect(() => { onDirtyChange(tableDirty); }, [tableDirty, onDirtyChange]);
  useEffect(() => () => onDirtyChange(false), [onDirtyChange]);
  useEffect(() => { if (!tableDirty) setWorkspace(initialWorkspace); }, [initialWorkspace, tableDirty]);
  const roleExceptions = rows.filter((row) => !row.role || String(row.role).includes(";")).length;
  const missingPrimary = rows.filter((row) => !row.primaryGroup).length;
  const groups = governanceSummary.groups || emptyGovernanceSummary.groups;
  function switchWorkspace(next) {
    if (tableDirty) { showToast("Save or reset unsaved Group changes before switching views."); return; }
    setWorkspace(next);
  }
  function handleTabKey(event) {
    if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
    event.preventDefault();
    const currentIndex = tabs.indexOf(workspace);
    const nextIndex = event.key === "ArrowRight" ? (currentIndex + 1) % tabs.length : (currentIndex - 1 + tabs.length) % tabs.length;
    switchWorkspace(tabs[nextIndex]);
    window.setTimeout(() => document.getElementById(`access-tab-${tabs[nextIndex]}`)?.focus(), 0);
  }
  return <section className="data-page governance-workspace">
    <div className="page-heading"><div><p className="eyebrow">MANAGE · ACCESS GOVERNANCE</p><h2>Users, Roles & Tiered Groups</h2><p>Review one role per user alongside primary, secondary, organizational-area, and additional Axon Group relationships.</p></div><span className={`data-mode ${isLive ? "live" : "demo"}`}>{isLive ? "AXON DATA" : "ILLUSTRATIVE"}</span></div>
    <div className="governance-metric-grid compact" aria-label="User access summary">
      <GovernanceMetric icon={PersonIcon} value={rows.length} label="Users reviewed" detail="One role field per user" />
      <GovernanceMetric icon={ExclamationTriangleIcon} value={roleExceptions} label="Role exceptions" detail="Missing or multi-value role text" tone={roleExceptions ? "amber" : "green"} />
      <GovernanceMetric icon={GroupIcon} value={missingPrimary} label="Primary Group not observed" detail={isLive ? "Current Users contract boundary" : "Illustrative rows include reviewed examples"} tone="amber" />
      <GovernanceMetric icon={LayersIcon} value={groups.total} label="Groups in local master" detail={`${groups.classified || 0} classified · ${groups.hierarchyLinks || 0} parent links`} tone="green" />
    </div>
    <div className="workspace-tabs" role="tablist" aria-label="Users and access views" onKeyDown={handleTabKey}>{tabs.map((key) => <button id={`access-tab-${key}`} type="button" role="tab" aria-controls="access-workspace-panel" aria-selected={workspace === key} tabIndex={workspace === key ? 0 : -1} className={workspace === key ? "active" : ""} onClick={() => switchWorkspace(key)} key={key}>{key === "users" ? <PersonIcon /> : key === "group-master" ? <GroupIcon /> : <Link2Icon />}{key === "users" ? "User access review" : crosswalkTables[key].label}</button>)}</div>
    <div id="access-workspace-panel" role="tabpanel" aria-labelledby={`access-tab-${workspace}`}>{workspace === "users" ? <UsersAccessTable rows={rows} isLive={isLive} showToast={showToast} /> : <CrosswalkEditor key={workspace} tableKey={workspace} backendAvailable={backendAvailable} showToast={showToast} onDirtyChange={setTableDirty} onSaved={onSaved} />}</div>
  </section>;
}

function DataTablePage({ type, rows, isLive, hasDeviceScope, downloadAvailable, downloadScope, showToast }) {
  const [search, setSearch] = useState("");
  const [stateFilter, setStateFilter] = useState("All");
  const inventory = type === "inventory";
  const visibleRows = rows.filter((row) => {
    const text = Object.values(row).join(" ").toLowerCase();
    const searchMatch = !search || text.includes(search.toLowerCase());
    const stateMatch = stateFilter === "All" || (inventory ? row.disposition === stateFilter : String(row.deviceCount) === stateFilter);
    return searchMatch && stateMatch;
  });
  const headers = inventory ? ["Serial number", "Model", "Disposition", "Assignment", "Device Home", "Mapped AOR"] : ["User", "Role", "Device count", "Assigned models", "Device states"];
  const values = inventory ? (row) => [row.serialNumber || row.deviceId, row.model, row.disposition, row.assignmentState, row.deviceHome || "—", row.regionAor || "Unmapped"] : (row) => [row.displayName, row.role || "—", row.deviceCount === null ? "Unavailable" : row.deviceCount, row.deviceModels, row.deviceStates];
  const filterOptions = inventory ? ["All", ...new Set(rows.map((row) => row.disposition).filter(Boolean))] : ["All", ...new Set(rows.map((row) => row.deviceCount).filter((value) => value !== null && value !== undefined).map(String))].sort((a, b) => a === "All" ? -1 : b === "All" ? 1 : Number(a) - Number(b));
  function exportCurrent() {
    if (isLive) {
      if (!downloadAvailable) {
        showToast("Run a full or filtered Devices refresh in this session before exporting device-derived records.");
        return;
      }
      window.location.href = localApi.exportUrl(inventory ? "devices" : "assignments");
      showToast("The full session CSV export was requested from the local backend.");
      return;
    }
    const csvRows = [headers, ...visibleRows.map(values)];
    const csv = csvRows.map((row) => row.map((value) => `"${String(value ?? "").replaceAll('"', '""')}"`).join(",")).join("\r\n");
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    const link = document.createElement("a"); link.href = url; link.download = `bwc-${type}-illustrative.csv`; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    showToast(`Illustrative ${type} CSV exported for the current filtered view.`);
  }
  return <section className="data-page"><div className="page-heading"><div><p className="eyebrow">MANAGE · {isLive ? "AXON DATA" : "ILLUSTRATIVE"}</p><h2>{inventory ? "Inventory" : "Assignments"}</h2><p>{isLive && !hasDeviceScope ? "Device relationships are unavailable until a full or filtered Devices refresh completes." : inventory ? "Filter devices by model, Device Home, assignment state, and disposition." : "Review roles and zero, one, or multiple-device relationships."}</p></div>{(!isLive || downloadAvailable) && <button type="button" className="secondary-button" onClick={exportCurrent}><DownloadIcon /> Export {isLive ? `${downloadScope === "filtered" ? "filtered " : ""}session CSV` : "current view"}</button>}</div><div className="page-toolbar"><label className="search-control"><MagnifyingGlassIcon /><input aria-label={`Search ${type}`} placeholder={`Search ${type}`} value={search} onChange={(event) => setSearch(event.target.value)} /></label><label><span>{inventory ? "Disposition" : "Device count"}</span><select value={stateFilter} onChange={(event) => setStateFilter(event.target.value)} disabled={isLive && !hasDeviceScope}>{filterOptions.map((option) => <option key={option}>{option}</option>)}</select></label><span className="toolbar-chip" aria-live="polite">Showing {visibleRows.length} of {rows.length}</span></div><div className="table-shell large"><table><caption className="sr-only">{inventory ? "Device inventory with disposition, assignment, Device Home, and mapped AOR." : "Users with roles and zero, one, or multiple device assignments."}</caption><thead><tr>{headers.map((header) => <th key={header}>{header}</th>)}</tr></thead><tbody>{visibleRows.map((row, rowIndex) => <tr key={inventory ? row.deviceId || row.serialNumber || rowIndex : row.userId || rowIndex}>{values(row).map((cell, index) => <td key={`${rowIndex}-${index}`}>{cell}</td>)}</tr>)}{!visibleRows.length && <tr><td colSpan={headers.length}>No records match the current filters.</td></tr>}</tbody></table></div></section>;
}

function MapPage({ orgView, summary, isLive, liveData, setPage }) {
  const [selectedMarker, setSelectedMarker] = useState(null);
  useEffect(() => { setSelectedMarker(null); }, [orgView]);
  return <section className="data-page"><div className="page-heading"><div><p className="eyebrow">MONITOR · {isLive ? "AXON DATA" : "ILLUSTRATIVE"}</p><h2>Organizational Coverage Map</h2><p>Select a marker to view its meaning and continue to the appropriate review workflow.</p></div></div><div className="map-workspace-grid"><MapPanel selectedMarker={selectedMarker} onMarkerSelect={setSelectedMarker} orgView={orgView} summary={summary} isLive={isLive} /><aside className="map-detail-panel" aria-live="polite">{selectedMarker ? <><div className="record-title"><DrawingPinIcon /><div><span>{selectedMarker.type === "cluster" ? "Selected area" : "Selected office reference"}</span><h3>{selectedMarker.label}</h3></div></div><dl><div><dt>Organizational lens</dt><dd>{orgView}</dd></div><div><dt>Marker type</dt><dd>{selectedMarker.type === "cluster" ? "Issue/site cluster" : selectedMarker.type.toUpperCase()}</dd></div>{selectedMarker.count !== undefined && <div><dt>Visible count</dt><dd>{number(selectedMarker.count)}</dd></div>}<div><dt>Validation</dt><dd>Provisional organizational reference</dd></div></dl><div className="review-queue-note"><InfoCircledIcon /><span>Map selection is a navigation aid, not evidence of jurisdiction or an approved organizational assignment.</span></div><div className="detail-actions"><button type="button" className="primary-button" onClick={() => setPage(selectedMarker.type === "cluster" ? "crosswalk" : "facilities")}>{selectedMarker.type === "cluster" ? "Review affected mappings" : "Review facility and office records"}</button><button type="button" className="secondary-button" onClick={() => setSelectedMarker(null)}>Clear selection</button></div></> : <><div className="record-title"><GlobeIcon /><div><span>Map details</span><h3>Select a marker</h3></div></div><p>Cluster markers open mapping review. Office reference markers open facility and office-governance review.</p></>}</aside></div><ProvenanceStrip liveData={liveData} isLive={isLive} /></section>;
}

function ReportsPage({ showToast, isLive, liveData, summary, component, orgView, setPage }) {
  function illustrativeCsv() {
    const rows = [["Data Mode", "Component Scope", "Organizational View", "Devices", "Assigned Devices", "Inventory Exceptions", "Unmapped Device Homes", "Mapping Completion"], [dataModeLabel(liveData.mode), component, orgView, summary.totalDevices, summary.assignedDevices, summary.inventoryExceptions, summary.unmappedDeviceHomes, percentage(summary.mappingCompletion)]];
    const csv = rows.map((row) => row.map((value) => `"${String(value ?? "").replaceAll('"', '""')}"`).join(",")).join("\r\n");
    const link = document.createElement("a"); link.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" })); link.download = `bwc-geographic-readiness-illustrative-${orgView.toLowerCase().replaceAll(/[^a-z0-9]+/g, "-")}.csv`; link.click(); setTimeout(() => URL.revokeObjectURL(link.href), 1000); showToast("Illustrative CSV exported for the stated dashboard scope.");
  }
  const resources = ["Devices", "Users", "Groups", "DeviceHomes"];
  const available = liveData.availableDownloads || [];
  const downloadScope = liveData.downloadScope?.deviceScope;
  return <section className="data-page"><div className="page-heading"><div><p className="eyebrow">GOVERNANCE · {isLive ? "AXON DATA" : "ILLUSTRATIVE"}</p><h2>Reports & Exports</h2><p>Create a scoped readiness brief or export locally held session data.</p></div></div><div className="report-scope-summary"><InfoCircledIcon /><div><strong>Report scope</strong><span>{isLive ? `${component} · ${dataModeLabel(liveData.mode)}` : "Illustrative national sample"} · {orgView} · {formatTimestamp(liveData.lastSyncAt)}</span></div></div><div className="report-grid"><article><FileTextIcon /><h3>Geographic readiness brief</h3><p>Preview a landscape report containing scope, metrics, map, priority risks, calculation, and provenance before printing or saving as PDF.</p><button type="button" className="primary-button" onClick={() => setPage("report-preview")}>Preview PDF report</button></article><article><TableIcon /><h3>{isLive ? "Axon session exports" : "Current illustrative dataset"}</h3><p>{isLive ? available.length ? `Available CSV exports come from this session's ${downloadScope === "filtered" ? "filtered" : "stated"} pull. They may differ from a persisted full baseline.` : "No session export is available. Run the required resource refresh in this application to generate one." : "CSV export containing the stated illustrative dashboard scope."}</p>{isLive ? <div className="export-links">{resources.filter((name) => available.includes(name.toLowerCase())).map((name) => <a className="secondary-button" href={localApi.exportUrl(name)} key={name}><DownloadIcon /> {downloadScope === "filtered" && name === "Devices" ? "Filtered Devices" : name}</a>)}{available.includes("assignments") && <a className="secondary-button" href={localApi.exportUrl("assignments")}><DownloadIcon /> {downloadScope === "filtered" ? "Filtered user-device assignments" : "User-device assignments"}</a>}{available.includes("summary") && <a className="secondary-button" href={localApi.exportUrl("summary")}><DownloadIcon /> Dashboard summary</a>}</div> : <button type="button" className="primary-button" onClick={illustrativeCsv}>Export scoped CSV</button>}</article><article className="planning-intake"><ReaderIcon /><h3>Planning-source intake</h3><p><strong>BWC.pdf and seven planning-table photos received.</strong> Their scopes and dates differ, so the observed purchase, deployment, accessory, and cost totals remain separate from Axon operational metrics.</p><span className="source-state provisional">Needs validation before import</span></article></div></section>;
}

function ReportPreviewPage({ summary, component, orgView, isLive, liveData, setPage, showToast }) {
  const tasks = buildTasks(summary, isLive);
  const view = mapViews[orgView] || mapViews["HSI Domestic AORs"];
  return <section className="readiness-report"><div className="report-actions"><button type="button" className="secondary-button" onClick={() => setPage("reports")}><ArrowLeftIcon /> Back to reports</button><button type="button" className="primary-button" onClick={() => { showToast("Print dialog opened. Choose Save as PDF on macOS or Microsoft Print to PDF on Windows."); window.print(); }}><FileTextIcon /> Print or save PDF</button></div><header><div><span className={`data-mode ${isLive ? "live" : "demo"}`}>{isLive ? dataModeLabel(liveData.mode) : "ILLUSTRATIVE — DEMO DATA"}</span><h2>BWC Geographic Readiness Brief</h2><p>{component} · {orgView}</p></div><div><strong>Snapshot</strong><span>{formatTimestamp(liveData.lastSyncAt)}</span><strong>Boundary validation</strong><span>Provisional</span></div></header><section className="report-metrics" aria-label="Readiness metrics"><article><span>Devices</span><strong>{number(summary.totalDevices)}</strong></article><article><span>Assigned</span><strong>{number(summary.assignedDevices)}</strong></article><article><span>Inventory exceptions</span><strong>{number(summary.inventoryExceptions)}</strong></article><article><span>Mapping completion</span><strong>{percentage(summary.mappingCompletion, isLive ? 1 : 0)}</strong></article></section><div className="report-body"><section><h3>{orgView}</h3><img src={view.asset} alt={view.alt} /><p className="report-map-note">Illustrative organizational reference — not for legal or operational boundary decisions.</p></section><section><h3>Priority review</h3><ol>{tasks.map((task) => <li key={task.id}><strong>{task.title}</strong><span>{task.subtitle}</span><small>Owner: {task.owner} · {task.status}</small></li>)}</ol></section></div><footer><div><strong>Calculation</strong><span>Mapping completion = devices with reviewed Site ID ÷ devices in the stated scope</span></div><div><strong>Data boundary</strong><span>{isLive ? `${dataModeLabel(liveData.mode)} · read-only Axon data with local governed crosswalk decisions` : "Illustrative demo dataset; no tenant snapshot loaded"}</span></div><div><strong>Map status</strong><span>{view.source}; provisional until authoritative owner validation</span></div></footer></section>;
}

function SettingsPage({ orgView, setOrgView, onOpenConnection, onExit, showToast }) {
  function saveDefault(event) {
    const value = event.target.value;
    setOrgView(value);
    window.localStorage.setItem("bwc-default-organizational-view", value);
    showToast(`Default organizational view saved for this workstation: ${value}.`);
  }
  return <section className="data-page"><div className="page-heading"><div><p className="eyebrow">CONFIGURATION</p><h2>Settings</h2><p>Local workstation preferences and application controls.</p></div><button type="button" className="primary-button" onClick={onOpenConnection}><Link2Icon /> Axon connection and pull</button></div><div className="settings-grid"><label><span>Default organizational view</span><select value={orgView} onChange={saveDefault}><option>HSI Domestic AORs</option><option>OCIO Areas</option><option>ERO Field Office AORs</option><option>HSI International</option></select><small>Saved locally in this browser and applied immediately to Dashboard, Map, and reports.</small></label><div className="notice"><InfoCircledIcon /><div><strong>Standalone security boundary</strong><p>Connection credentials remain process-memory only. Governed CSV changes use timestamped backups and a durable hash-chained audit. Axon operational access remains read-only.</p><button type="button" className="text-danger" onClick={onExit}>Exit desktop app and clear session</button></div></div></div></section>;
}

function ProvenancePage({ isLive, liveData }) {
  const counts = liveData.resourceCounts || {};
  return <section className="data-page"><div className="page-heading"><div><p className="eyebrow">GOVERNANCE · {isLive ? dataModeLabel(liveData.mode) : "SYNTHETIC"}</p><h2>Data Provenance</h2><p>Trace geographic lenses, Axon resources, filters, and validation state.</p></div></div><div className="provenance-table"><div className="provenance-row header"><span>Source</span><span>Scope</span><span>Reference date</span><span>Rows</span><span>Validation</span></div>{isLive && ["DeviceHomes", "Groups", "Users", "Devices"].map((name) => <div className="provenance-row" key={name}><span>Axon Partner API · {name}</span><span>{liveData.baselineScopes?.[name]?.type === "filtered" ? "Filtered read-only GET" : liveData.baselineScopes?.[name]?.type === "full" ? "Full read-only GET" : "Not loaded"}</span><span>{new Date(liveData.lastSyncAt).toLocaleString()}</span><span>{number(counts[name])}</span><span className={counts[name] === null ? "provisional-text" : "good"}>{counts[name] === null ? "Unavailable" : "Pulled"}</span></div>)}<div className="provenance-row"><span>Organizational coverage layer</span><span>Local AOR and command hierarchy</span><span>Not bundled</span><span>—</span><span className="provisional-text">Configure locally</span></div><div className="provenance-row"><span>Repository demonstration layer</span><span>Non-operational synthetic placeholders</span><span>Generated fixture</span><span>4 examples</span><span className="provisional-text">Synthetic</span></div></div><div className="notice"><InfoCircledIcon /><div><strong>Live-data boundary</strong><p>Axon records are tenant truth for the fields returned by the API. Planning values remain separate. Geographic assignments are governed crosswalk decisions; names are normalized only as review keys, never treated as immutable IDs.</p></div></div>{isLive && <div className="notice"><MixerHorizontalIcon /><div><strong>Device API filters used</strong><p>Model: {liveData.filters?.deviceModel || "All"}; status2: {liveData.filters?.deviceStatus || "All"}; homeId: {liveData.filters?.deviceHomeId || "All"}. {liveData.mode === "filtered" ? "This result is not the confirmed full-device baseline." : ""}</p></div></div>}</section>;
}

function GenericPage({ page, setPage, showToast, isLive, liveData, summary, component, orgView, setOrgView, onOpenConnection, onExit }) {
  if (page === "map") return <MapPage orgView={orgView} summary={summary} isLive={isLive} liveData={liveData} setPage={setPage} />;
  if (page === "exceptions") { const tasks = buildTasks(summary, isLive); return <section className="data-page"><div className="page-heading"><div><p className="eyebrow">MONITOR · {isLive ? "AXON DATA" : "ILLUSTRATIVE"}</p><h2>Exceptions</h2><p>Prioritized mapping, inventory, assignment, and Group-classification review.</p></div></div><div className="exception-board">{tasks.map((task) => <article key={task.id} className={`exception-row ${task.tone}`}><span className="task-rank">{task.rank}</span><div><h3>{task.title}</h3><p>{task.subtitle}</p></div><span>Owner: {task.owner}</span><button type="button" onClick={() => task.id === "mapping" ? setPage("crosswalk") : task.id === "devices" ? setPage("inventory") : setPage("access-groups")}>Open <ChevronRightIcon /></button></article>)}</div></section>; }
  if (page === "reports") return <ReportsPage showToast={showToast} isLive={isLive} liveData={liveData} summary={summary} component={component} orgView={orgView} setPage={setPage} />;
  if (page === "report-preview") return <ReportPreviewPage summary={summary} component={component} orgView={orgView} isLive={isLive} liveData={liveData} setPage={setPage} showToast={showToast} />;
  if (page === "provenance") return <ProvenancePage isLive={isLive} liveData={liveData} />;
  return <SettingsPage orgView={orgView} setOrgView={setOrgView} onOpenConnection={onOpenConnection} onExit={onExit} showToast={showToast} />;
}

export function App() {
  const [page, setPage] = useState("dashboard");
  const [navCollapsed, setNavCollapsed] = useState(false);
  const [component, setComponent] = useState("All Components");
  const [inventoryFilters, setInventoryFilters] = useState({ ...emptyInventoryFilters });
  const [assignmentFilters, setAssignmentFilters] = useState({ ...emptyAssignmentFilters });
  const [orgView, setOrgView] = useState(() => window.localStorage.getItem("bwc-default-organizational-view") || "HSI Domestic AORs");
  const [connectionOpen, setConnectionOpen] = useState(false);
  const [selectedTask, setSelectedTask] = useState("mapping");
  const [toast, setToast] = useState("");
  const [backendAvailable, setBackendAvailable] = useState(false);
  const [session, setSession] = useState(emptySession);
  const [config, setConfig] = useState(emptyConfig);
  const [liveData, setLiveData] = useState({ mode: "illustrative" });
  const [syncJob, setSyncJob] = useState(null);
  const [governanceSummary, setGovernanceSummary] = useState(emptyGovernanceSummary);
  const [localWorkspaceDirty, setLocalWorkspaceDirty] = useState(false);

  useEffect(() => {
    Promise.all([localApi.health(), localApi.session(), localApi.config(), localApi.dashboard(), localApi.governanceSummary()]).then(([, sessionData, configData, dashboardData, governanceData]) => {
      setBackendAvailable(true); setSession(sessionData); setConfig(configData); setLiveData(dashboardData); setGovernanceSummary(governanceData);
      if (sessionData.activeJob) setSyncJob(sessionData.activeJob);
    }).catch(() => setBackendAvailable(false));
  }, []);

  useEffect(() => {
    if (!backendAvailable) return undefined;
    const timer = window.setInterval(async () => {
      try {
        const dashboardData = await localApi.dashboard();
        if (dashboardData.workspaceRevision !== liveData.workspaceRevision) setLiveData(dashboardData);
      } catch { /* keep the last complete shared baseline during transient local errors */ }
    }, 4000);
    return () => window.clearInterval(timer);
  }, [backendAvailable, liveData.workspaceRevision]);

  const isLive = ["live", "filtered", "partial"].includes(liveData.mode);
  const summary = isLive && component !== "All Components" && liveData.mode !== "partial" ? liveData.componentSummaries?.[component] || { ...liveData.summary, totalDevices: 0, assignedDevices: 0, unassignedDevices: 0, inventoryExceptions: 0, mappedDevices: 0, mappingCompletion: 0, unmappedDeviceHomes: 0, regionCounts: {}, dispositionCounts: {} } : isLive ? liveData.summary : illustrativeSummary;
  const inventoryRows = isLive ? (liveData.inventory || []).filter((row) => component === "All Components" || row.component === component) : illustrativeInventory;
  const assignmentRows = isLive ? liveData.assignments || [] : illustrativeAssignments;
  const crosswalkRows = isLive ? liveData.crosswalkReview || [] : illustrativeCrosswalk;

  async function saveConnection(configValues, credentialValues) {
    const savedConfig = await localApi.saveConfig(configValues);
    setConfig(savedConfig);
    const provided = [credentialValues.partnerId, credentialValues.clientId, credentialValues.clientSecret].filter((value) => String(value || "").trim()).length;
    if (provided && provided !== 3) throw new Error("Enter Partner / Agency ID, Client ID, and Client Secret together, or leave all three blank to keep the active session credentials.");
    if (provided === 3) {
      const savedSession = await localApi.saveCredentials(credentialValues);
      setSession(savedSession);
    } else if (!session.configured) {
      throw new Error("Session credentials are required for the first live pull.");
    }
    setToast("Connection settings saved. Credentials remain in memory only; they are checked when the live pull starts.");
  }

  async function pullLiveData(values) {
    const started = await localApi.startSync(values);
    setSyncJob(started);
    setToast("Read-only Axon pull started. The Device API may take time because requests are paced.");
    let current = started;
    while (["queued", "running", "cancel-requested"].includes(current.status)) {
      await sleep(800);
      current = await localApi.syncStatus(started.jobId);
      setSyncJob(current);
    }
    if (current.status === "failed") throw new Error(current.error || "The live Axon pull failed.");
    if (current.status === "canceled") {
      setToast("Axon pull stopped safely after the active request. The prior dashboard snapshot was preserved.");
      return;
    }
    const [dashboardData, sessionData] = await Promise.all([localApi.dashboard(), localApi.session()]);
    setLiveData(dashboardData); setSession(sessionData); setToast(dashboardData.mode === "filtered" ? "Filtered Axon result loaded. It is labeled separately and does not replace confirmed full-device metrics." : dashboardData.mode === "partial" ? "Partial Axon resources loaded. Run a full Devices refresh before using device metrics." : "Full Axon baseline loaded into the dashboard.");
  }

  async function cancelSync() {
    if (!syncJob?.jobId) return;
    try {
      const canceled = await localApi.cancelSync(syncJob.jobId);
      setSyncJob(canceled);
      setToast("Stop requested. The pull will end after the current read-only request completes.");
    } catch (error) { setToast(error.message); }
  }

  async function clearCredentials() {
    try {
      const cleared = await localApi.clearCredentials(); setSession(cleared); setToast("Session credentials cleared from memory.");
    } catch (error) { setToast(error.message); }
  }

  async function refreshGovernanceSummary() {
    try { setGovernanceSummary(await localApi.governanceSummary()); } catch (error) { setToast(error.message); }
  }

  async function shutdownApplication() {
    if (!window.confirm("Exit Geographic Operations and clear the active credential session?")) return;
    try {
      await localApi.shutdown();
      document.body.innerHTML = '<main style="font:16px system-ui;padding:3rem"><h1>Geographic Operations closed</h1><p>You can close this browser tab.</p></main>';
    } catch (error) {
      setToast(error.message);
    }
  }

  const pageContent = useMemo(() => {
    if (page === "dashboard") return <><PendingOverlayPanel data={liveData} /><Dashboard selectedTask={selectedTask} setSelectedTask={setSelectedTask} setPage={setPage} orgView={orgView} liveData={liveData} isLive={isLive} summary={summary} /></>;
    if (page === "crosswalk") return <CrosswalkPage setPage={setPage} showToast={setToast} rows={crosswalkRows} isLive={isLive} defaultReviewState="All states" backendAvailable={backendAvailable} onDirtyChange={setLocalWorkspaceDirty} />;
    if (page === "facilities") return <FacilitiesPage backendAvailable={backendAvailable} governanceSummary={governanceSummary} showToast={setToast} onDirtyChange={setLocalWorkspaceDirty} onSaved={refreshGovernanceSummary} />;
    if (page === "access" || page === "access-groups") return <UsersAccessPage rows={assignmentRows} isLive={isLive} backendAvailable={backendAvailable} governanceSummary={governanceSummary} showToast={setToast} onDirtyChange={setLocalWorkspaceDirty} onSaved={refreshGovernanceSummary} initialWorkspace={page === "access-groups" ? "group-master" : "users"} />;
    if (page === "inventory") return <InventoryWorkspace filters={inventoryFilters} setFilters={setInventoryFilters} component={component} setComponent={setComponent} isLive={isLive} liveData={liveData} demoRows={illustrativeInventory} showToast={setToast} />;
    if (page === "assignments") return <AssignmentWorkspace filters={assignmentFilters} setFilters={setAssignmentFilters} isLive={isLive} liveData={liveData} showToast={setToast} />;
    return <GenericPage page={page} setPage={setPage} showToast={setToast} isLive={isLive} liveData={liveData} summary={summary} component={component} orgView={orgView} setOrgView={setOrgView} onOpenConnection={() => setConnectionOpen(true)} onExit={shutdownApplication} />;
  }, [page, selectedTask, orgView, liveData, isLive, summary, crosswalkRows, inventoryRows, assignmentRows, component, backendAvailable, governanceSummary, inventoryFilters, assignmentFilters]);

  return <><a className="skip-link" href="#main-content">Skip to main content</a><div className={`app-shell ${navCollapsed ? "nav-collapsed" : ""}`}><Sidebar page={page} setPage={(next) => { if (["crosswalk", "facilities", "access", "access-groups"].includes(page) && localWorkspaceDirty && next !== page) { setToast("Save or reset unsaved local governance changes before leaving the workspace."); return; } setPage(next); }} exceptionCount={summary.inventoryExceptions} collapsed={navCollapsed} setCollapsed={setNavCollapsed} /><div className="app-workspace"><AppHeader page={page} component={component} setComponent={setComponent} orgView={orgView} setOrgView={setOrgView} isLive={isLive} dataMode={liveData.mode} session={session} backendAvailable={backendAvailable} onOpenConnection={() => setConnectionOpen(true)} /><SyncJobBanner job={syncJob} onOpen={() => setConnectionOpen(true)} onCancel={cancelSync} /><main id="main-content" className="page-content" tabIndex="-1">{pageContent}</main></div>{toast && <div className="toast" role="status"><CheckCircledIcon /><span>{toast}</span><button type="button" aria-label="Dismiss notification" onClick={() => setToast("")}><Cross2Icon /></button></div>}<ConnectionModal open={connectionOpen} backendAvailable={backendAvailable} config={config} session={session} syncJob={syncJob} onClose={() => setConnectionOpen(false)} onSave={saveConnection} onPull={pullLiveData} onClear={clearCredentials} /></div></>;
}
