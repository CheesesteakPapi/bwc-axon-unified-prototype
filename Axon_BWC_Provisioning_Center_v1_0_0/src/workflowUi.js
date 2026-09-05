export function stepForRun(run) {
  if (!run || ["Draft", "Enriching"].includes(run.status)) return 0;
  if (run.status === "Needs Review") return 1;
  if (["Ready for Preview", "Previewed"].includes(run.status)) return 2;
  if (run.status === "Awaiting Submission") return 3;
  return 4;
}

export function approvalCurrent(run) {
  const a = run?.approval;
  const snapshotKey = ids => JSON.stringify(Object.entries(ids || {}).sort(([a], [b]) => a.localeCompare(b)));
  return Boolean(a?.approvedAt && a.runId === run.runId && a.revision === run.revision &&
    a.userHash === run.generation?.userHash && a.groupHash === run.generation?.groupHash &&
    snapshotKey(a.snapshotIds) === snapshotKey(run.activeSnapshotIds) && run.validation?.valid);
}

export function submissionCopy(run) {
  if (run?.chunks?.some(c => c.axonJobId || ["submitted", "completed", "ambiguous"].includes(c.status)))
    return ["This run has submission history.", "Review Track Results before submitting another eligible chunk. Never retry an uncertain write."];
  if (approvalCurrent(run)) return ["Updates approved for submission.", "Nothing has been submitted to Axon yet."];
  return ["Preview approval is required.", "Return to Preview Changes, save any edits, and approve this revision. Nothing will be submitted from this page without approval."];
}

// Parse Excel TSV and CSV without evaluating cell contents. Validation remains server-side.
export function parseClipboard(text) {
  text = text.replace(/^\uFEFF/, "").replace(/\r\n/g, "\n").replace(/\r/g, "\n");
  const delimiter = text.includes("\t") ? "\t" : ",";
  const rows = []; let row = [], cell = "", quoted = false;
  for (let i = 0; i < text.length; i++) {
    const char = text[i];
    if (char === '"') {
      if (quoted && text[i + 1] === '"') { cell += '"'; i++; } else quoted = !quoted;
    } else if (!quoted && (char === delimiter || char === "\n")) {
      row.push(cell.trim()); cell = "";
      if (char === "\n") { if (row.some(Boolean)) rows.push(row); row = []; }
    } else cell += char;
  }
  if (quoted) throw new Error("The pasted list has an unclosed quote. Check the original cells and paste again.");
  row.push(cell.trim()); if (row.some(Boolean)) rows.push(row);
  if (rows.length > 1501) throw new Error("Paste no more than 1,500 users per run.");
  const aliases = { email: ["email", "email address", "work email"], role: ["role", "axon role"], group: ["group", "group name", "organizational group"] };
  const header = rows[0]?.map(c => c.toLowerCase()) || [];
  const indexes = Object.fromEntries(Object.entries(aliases).map(([k, names]) => [k, header.findIndex(h => names.includes(h))]));
  const hasHeader = indexes.email >= 0 && indexes.role >= 0;
  if (hasHeader) rows.shift();
  if (rows.length > 1500) throw new Error("Paste no more than 1,500 users per run.");
  if (!hasHeader && rows.some(r => r.length > 3)) throw new Error("Use Email, Role, and optional Group Name columns, or include recognized headers.");
  return rows.map(r => ({ Email: r[hasHeader ? indexes.email : 0] || "", Role: r[hasHeader ? indexes.role : 1] || "", "Group Name": r[hasHeader ? indexes.group : 2] || "" }));
}
