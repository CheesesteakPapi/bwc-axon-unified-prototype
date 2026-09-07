import { useMemo, useState } from "react";

const fields = [["role","Role"],["groupName","Group"],["location","Location"],["personnelAor","Personnel AOR"],["jobCategory","Job category"],["supervisorEmail","Supervisor email"],["supervisorUpn","Supervisor UPN"]];

export function PeopleReview({ run, onlyExceptions, drafts, setDrafts, selected, setSelected, groupOptions, GroupPicker, disabled }) {
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(0);
  const [currentId, setCurrentId] = useState("");
  const [status, setStatus] = useState("all");
  const matches = useMemo(() => run.rows.filter(row => (!onlyExceptions || row.validationState === "Blocked" || row.warnings?.length) &&
    (status === "all" || (status === "blocked" ? row.validationState === "Blocked" : status === "warnings" ? !!row.warnings?.length : row.validationState !== "Blocked")) &&
    [row.email,row.firstName,row.lastName,row.role,...(row.blockers || []),...(row.warnings || [])].some(v => String(v || "").toLowerCase().includes(search.toLowerCase()))), [run.rows, onlyExceptions, search, status]);
  const actualPage = Math.min(page, Math.max(0, Math.ceil(matches.length / 25) - 1));
  const visible = matches.slice(actualPage * 25, actualPage * 25 + 25);
  const row = visible.find(item => item.rowId === currentId) || visible[0];
  function update(rowId, field, value) {
    const original = run.rows.find(item => item.rowId === rowId);
    setDrafts(current => {
      const changes = { ...current[rowId] };
      if (value === (original[field] || "")) delete changes[field]; else changes[field] = value;
      const next = { ...current };
      if (Object.keys(changes).length) next[rowId] = changes; else delete next[rowId];
      return next;
    });
  }
  return <div className="people-review">
    <label className="people-search"><span>Find a person</span><input type="search" value={search} onChange={e => {setSearch(e.target.value);setPage(0);setSelected(new Set());}} placeholder="Name, email, role, or issue" /></label>
    <p className="muted">{matches.length} matching people · {selected.size} selected · Identity stays read-only</p>
    <div className="bulk-selection">
      <label>Review filter<select aria-label="User review filter" value={status} onChange={e=>{setStatus(e.target.value);setPage(0);setSelected(new Set());}}><option value="all">All in this view</option><option value="blocked">Blocked</option><option value="warnings">With warnings</option><option value="ready">Ready for import</option></select></label>
      <button type="button" className="secondary" disabled={disabled || !visible.length} onClick={()=>setSelected(new Set(visible.map(r=>r.rowId)))}>Select this page ({visible.length})</button>
      <button type="button" className="secondary" disabled={disabled || !matches.length} onClick={()=>setSelected(new Set(matches.map(r=>r.rowId)))}>Select all matching people ({matches.length})</button>
      <button type="button" className="secondary" disabled={disabled || !selected.size} onClick={()=>setSelected(new Set())}>Clear selection</button>
      <span>All matching includes other pages. Selection remains explicit.</span>
    </div>
    <div className="people-review-layout"><section className="people-list" aria-label="People to review">
      {visible.map(item => <div key={item.rowId} className={row?.rowId === item.rowId ? "person-row active" : "person-row"}>
        <input type="checkbox" disabled={disabled} aria-label={`Select ${item.email}`} checked={selected.has(item.rowId)} onChange={e => setSelected(current => {const next = new Set(current);if(e.target.checked) next.add(item.rowId);else next.delete(item.rowId);return next;})} />
        <button type="button" onClick={() => setCurrentId(item.rowId)} aria-pressed={row?.rowId === item.rowId}><strong>{item.firstName} {item.lastName}</strong><span>{item.email}</span><small>{drafts[item.rowId] ? "Unsaved changes" : item.validationState === "Blocked" ? "Blocked — review required" : item.warnings?.length ? "Ready · optional warnings" : "Ready"} · {item.existingAccount ? "Existing account" : "Proposed creation"}</small></button>
      </div>)}
      {!visible.length && <p>No people match this view.</p>}
      <div className="people-pagination"><button type="button" className="secondary" disabled={!actualPage} onClick={() => setPage(actualPage-1)}>Previous</button><span>{actualPage+1} / {Math.max(1,Math.ceil(matches.length/25))}</span><button type="button" className="secondary" disabled={(actualPage+1)*25 >= matches.length} onClick={() => setPage(actualPage+1)}>Next</button></div>
    </section><section className="person-editor" aria-label="Selected person assignments">{row && <>
      <h3>{row.firstName} {row.lastName}</h3><p>{row.email}</p>
      <div className="person-state"><strong>{row.validationState === "Blocked" ? "Action required" : "Ready for user import"}</strong><span>Proposed status: Active · Directory status: {row.directoryAccountStatus || "Unknown"}</span></div>
      {row.blockers?.map(v => <p className="blocker" key={v}>{v}</p>)}
      {!!row.warnings?.length && <details><summary>Optional mapping warnings ({row.warnings.length})</summary>{row.warnings.map(v => <p className="warning-note" key={v}>{v}</p>)}</details>}
      <details className="identity-details"><summary>Source identity and provenance</summary><dl>{[["Email",row.email],["UPN",row.upn],["External ID",row.externalId],["Badge",row.badgeNumber],["Username",row.username],["Component",row.component],["Directory location",row.directoryLocation],["Job title",row.jobTitle]].map(([k,v]) => <div key={k}><dt>{k}</dt><dd>{v || "Not supplied"}</dd></div>)}</dl><p>Identity corrections require returning to enrichment. Device location never changes personnel organization.</p></details>
      <fieldset disabled={disabled} className="assignment-fields"><legend>Proposed assignments</legend>{fields.map(([key,label]) => <div className="assignment-field" key={key}>
        {key === "groupName" ? <><span className="field-label">Group (optional)</span><GroupPicker row={row} draft={drafts[row.rowId]} update={update} options={groupOptions} /></> :
          <label><span>{label}{key !== "role" ? " (optional)" : ""}</span><input list={key === "role" ? "approved-roles" : undefined} aria-label={`${key} for ${row.email}`} value={drafts[row.rowId]?.[key] ?? row[key] ?? ""} onChange={e => update(row.rowId,key,e.target.value)} /></label>}
        {row.differences?.filter(d => d.field.toLowerCase().replaceAll("_","") === key.toLowerCase()).map(d => <small key={d.field}>Current Axon: {d.current || "blank"} → proposed: {drafts[row.rowId]?.[key] ?? d.proposed ?? "blank"}</small>)}
      </div>)}</fieldset>
      {!!row.differences?.length && <details><summary>All current vs proposed Axon values</summary><dl>{row.differences.map(d => <div key={d.field}><dt>{d.field}</dt><dd>{d.current || "blank"} → {d.proposed || "blank"}</dd></div>)}</dl></details>}
    </>}</section></div>
  </div>;
}
