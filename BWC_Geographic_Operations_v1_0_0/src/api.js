const LOCAL_HEADERS = { "Content-Type": "application/json", "X-BWC-Local-UI": "1" };

async function request(path, options = {}) {
  const response = await fetch(path, {
    cache: "no-store",
    ...options,
    headers: options.method && options.method !== "GET" ? { ...LOCAL_HEADERS, ...(options.headers || {}) } : options.headers,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error || `Local request failed (${response.status}).`);
  return payload;
}

export const localApi = {
  health: () => request("/api/health"),
  session: () => request("/api/session"),
  config: () => request("/api/config"),
  dashboard: () => request("/api/live/dashboard"),
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
  crosswalkExportUrl: (key) => `/api/crosswalks/${encodeURIComponent(key)}/export`,
};
