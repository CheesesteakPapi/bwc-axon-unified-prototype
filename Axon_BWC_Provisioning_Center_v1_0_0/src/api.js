const LOCAL_HEADER = { "X-Axon-Local-UI": "1" };

async function request(path, options = {}) {
  const response = await fetch(path, {
    cache: "no-store",
    ...options,
    headers: {
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...(options.method && options.method !== "GET" ? LOCAL_HEADER : {}),
      ...(options.headers || {}),
    },
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(payload.error || `Local request failed (${response.status}).`);
    error.status = response.status;
    throw error;
  }
  return payload;
}

function bytesToBase64(bytes) {
  let binary = "";
  const chunkSize = 0x8000;
  for (let offset = 0; offset < bytes.length; offset += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + chunkSize));
  }
  return btoa(binary);
}

async function uploadFile(file) {
  return request("/api/files", {
    method: "POST",
    body: JSON.stringify({ name: file.name, contentBase64: bytesToBase64(new Uint8Array(await file.arrayBuffer())) }),
  });
}

export const localApi = {
  supportDiagnostics: () => request("/api/support/diagnostics"),
  health: () => request("/api/health"),
  session: () => request("/api/session"),
  config: () => request("/api/config"),
  workspace: () => request("/api/workspace/status"),
  groupOptions: () => request("/api/catalogs/groups"),
  roleOptions: () => request("/api/catalogs/roles"),
  startRefresh: (values) => request("/api/workspace/refresh", { method: "POST", body: JSON.stringify(values) }),
  refreshStatus: (jobId) => request(`/api/workspace/refresh/${encodeURIComponent(jobId)}`),
  cancelRefresh: (jobId) => request(`/api/workspace/refresh/${encodeURIComponent(jobId)}/cancel`, { method: "POST", body: "{}" }),
  latestRun: () => request("/api/runs/latest"),
  getRun: (runId) => request(`/api/runs/${encodeURIComponent(runId)}`),
  saveConfig: (values) => request("/api/config", { method: "POST", body: JSON.stringify(values) }),
  saveCredentials: (values) => request("/api/session/credentials", { method: "POST", body: JSON.stringify(values) }),
  clearCredentials: () => request("/api/session/credentials", { method: "DELETE", body: "{}" }),
  uploadFile,
  detectIntake: (fileHandle) => request("/api/runs/intake/detect", { method: "POST", body: JSON.stringify({ fileHandle }) }),
  createRun: (values) => request("/api/runs", { method: "POST", body: JSON.stringify(values) }),
  editRun: (runId, values) => request(`/api/runs/${encodeURIComponent(runId)}/edit`, { method: "POST", body: JSON.stringify(values) }),
  approveRun: (runId, values) => request(`/api/runs/${encodeURIComponent(runId)}/approve`, { method: "POST", body: JSON.stringify(values) }),
  submitNext: (runId, values) => request(`/api/runs/${encodeURIComponent(runId)}/submit-next`, { method: "POST", body: JSON.stringify(values) }),
  trackRun: (runId, expectedRevision) => request(`/api/runs/${encodeURIComponent(runId)}/track`, { method: "POST", body: JSON.stringify({ expectedRevision }) }),
  exportRun: (runId, expectedRevision) => request(`/api/runs/${encodeURIComponent(runId)}/export`, { method: "POST", body: JSON.stringify({ expectedRevision }) }),
  shutdown: () => request("/api/app/shutdown", { method: "POST", body: "{}" }),
};
