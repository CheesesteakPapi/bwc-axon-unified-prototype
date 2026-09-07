const LOCAL_HEADERS = { "Content-Type": "application/json", "X-BWC-Local-UI": "1" };

async function request(path, options = {}) {
  const controller = new AbortController();
  let timedOut = false;
  const readOnly = !options.method || options.method === "GET";
  const timer = readOnly ? setTimeout(() => { timedOut = true; controller.abort(); }, 30000) : null;
  const abort = () => controller.abort();
  options.signal?.addEventListener("abort", abort, { once: true });
  if (options.signal?.aborted) controller.abort();
  try {
    const response = await fetch(path, {
    cache: "no-store",
    ...options,
    signal: controller.signal,
    headers: options.method && options.method !== "GET" ? { ...LOCAL_HEADERS, ...(options.headers || {}) } : options.headers,
  });
  if (!(response.headers.get("Content-Type") || "").includes("application/json"))
    throw new Error("The local service returned a web page instead of data. Restart with the Python launcher and use its opened URL.");
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || `Local request failed (${response.status}).`);
  return payload;
  } catch (error) {
    if (timedOut) throw new Error("Local data did not load within 30 seconds. Retry this panel; existing saved data has not been changed.");
    throw error;
  } finally {
    clearTimeout(timer);
    options.signal?.removeEventListener("abort", abort);
  }
}

async function downloadSavedView(path, query) {
  const response = await fetch(`${path}?${new URLSearchParams(query)}`, { cache: "no-store" });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.error || "Export failed. Reload saved data and try again.");
  }
  const filename = response.headers.get("Content-Disposition")?.match(/filename="([^"]+)"/)?.[1] || "BWC_review.csv";
  return { blob: await response.blob(), filename };
}

export const localApi = {
  supportDiagnostics: () => request("/api/support/diagnostics"),
  createRelationship: values => request("/api/review/relationships", {method:"POST", body:JSON.stringify(values)}),
  health: () => request("/api/health"),
  session: () => request("/api/session"),
  config: () => request("/api/config"),
  dashboard: () => request("/api/live/dashboard"),
  revision: () => request("/api/workspace/revision"),
  reviewTargets: (key, sourceKey) => request(`/api/review/targets?${new URLSearchParams({key, sourceKey})}`),
  inventory: (query, signal) => request(`/api/inventory?${new URLSearchParams(query)}`, { signal }),
  assignments: (query, signal) => request(`/api/assignments?${new URLSearchParams(query)}`, { signal }),
  assignmentDevices: (query, signal) => request(`/api/assignments/devices?${new URLSearchParams(query)}`, { signal }),
  exportAssignments: (query) => downloadSavedView("/api/assignments/export", query),
  exportInventory: async (query) => {
    const response = await fetch(`/api/inventory/export?${new URLSearchParams(query)}`, { cache: "no-store" });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.error || "Inventory export failed. Reload saved data and try again.");
    }
    const filename = response.headers.get("Content-Disposition")?.match(/filename="([^"]+)"/)?.[1] || "BWC_inventory.csv";
    return { blob: await response.blob(), filename };
  },
  governanceSummary: () => request("/api/governance/summary"),
  saveConfig: (values) => request("/api/config", { method: "POST", body: JSON.stringify(values) }),
  saveCredentials: (values) => request("/api/session/credentials", { method: "POST", body: JSON.stringify(values) }),
  clearCredentials: () => request("/api/session/credentials", { method: "DELETE", body: "{}" }),
  shutdown: () => request("/api/app/shutdown", { method: "POST", body: "{}" }),
  startSync: (values) => request("/api/live/sync", { method: "POST", body: JSON.stringify(values) }),
  syncStatus: (jobId) => request(`/api/live/sync/${encodeURIComponent(jobId)}`),
  cancelSync: (jobId) => request(`/api/live/sync/${encodeURIComponent(jobId)}/cancel`, { method: "POST", body: "{}" }),
  exportUrl: (resource) => `/api/live/export/${encodeURIComponent(resource)}`,
  crosswalk: (key, { page = 1, pageSize = 25, search = "" } = {}) => {
    const query = new URLSearchParams({ page: String(page), pageSize: String(pageSize) });
    if (search.trim()) query.set("search", search.trim());
    return request(`/api/crosswalks/${encodeURIComponent(key)}?${query.toString()}`);
  },
  saveCrosswalkRow: (key, rowNumber, changes, expected) => request(`/api/crosswalks/${encodeURIComponent(key)}/rows/${encodeURIComponent(rowNumber)}`, {
    method: "POST",
    body: JSON.stringify({ changes, expected }),
  }),
  addCrosswalkRow: (key, values) => request(`/api/crosswalks/${encodeURIComponent(key)}/rows`, {
    method: "POST",
    body: JSON.stringify({ values }),
  }),
  bulkCrosswalk: (key, values) => request(`/api/crosswalks/${encodeURIComponent(key)}/bulk`, {method:"POST", body:JSON.stringify(values)}),
  crosswalkExportUrl: (key) => `/api/crosswalks/${encodeURIComponent(key)}/export`,
};
