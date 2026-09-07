// Each panel is independent: a slow dashboard must never disable local editors.
export function loadWorkspace(api, handlers) {
  let active = true;
  for (const name of ["health", "session", "config", "dashboard", "governanceSummary"]) {
    Promise.resolve().then(() => api[name]()).then(
      value => { if (active) handlers.success(name, value); },
      error => { if (active) handlers.failure(name, error); },
    );
  }
  return () => { active = false; };
}

export function devicePullNeedsScope(resources, filters, allowFull) {
  return resources.includes("Devices") && !allowFull &&
    ![filters.deviceModel, filters.deviceStatus, filters.deviceHomeId].some(v => String(v || "").trim());
}

export function effectiveDeviceScope(mode, filters) {
  if (mode === "full") return {deviceModel:"",deviceStatus:"",deviceHomeId:""};
  if (mode === "tracked") return {deviceModel:filters.deviceModel || "",deviceStatus:"",deviceHomeId:""};
  return {...filters};
}
