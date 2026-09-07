export const BULK_USER_FIELDS = {Role:"role",Group:"groupName",Location:"location","Personnel AOR":"personnelAor","Job category":"jobCategory","Supervisor email":"supervisorEmail","Supervisor UPN":"supervisorUpn"};

export function previewBulkUsers(run, selected, common, groups) {
  if (!selected.size) throw Error("Select at least one person.");
  const changes = {};
  for (const [label,value] of Object.entries(common)) {
    const field = BULK_USER_FIELDS[label];
    if (!field) throw Error("Identity fields cannot be changed in bulk.");
    if (field === "groupName") {
      const matches = groups.filter(g=>g.externalId === value);
      if (value && matches.length !== 1) throw Error("Select one exact Group or leave the Group blank.");
      changes.groupName = matches[0]?.name || "";
      changes.groupExternalId = value || "";
    } else { changes[field] = value; }
  }
  const rows = run.rows.filter(row=>selected.has(row.rowId));
  if (rows.length !== selected.size) throw Error("The selected people changed. Reselect and preview.");
  const edits = [], preview = [];
  for (const row of rows) {
    const actual = Object.fromEntries(Object.entries(changes).filter(([f,v])=>(row[f] || "") !== v));
    if (!Object.keys(actual).length) continue;
    edits.push({rowId:row.rowId,changes:actual});
    preview.push({label:row.email,differences:Object.entries(actual).map(([field,after])=>({field,before:row[field] || "",after}))});
  }
  return {runId:run.runId,revision:run.revision,edits,preview,selectedCount:rows.length,changedCount:edits.length,unchangedCount:rows.length-edits.length};
}
