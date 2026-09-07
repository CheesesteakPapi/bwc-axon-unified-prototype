import { useEffect, useState } from "react";
import { localApi } from "./api.js";

export function ReviewMappingEditor({ source, backendAvailable, onDirtyChange, onSaved, showToast }) {
  const [nonSite, setNonSite] = useState(source.relationshipType === "non-site");
  const key = source.sourceType === "Device Home" ? "device-homes" : nonSite ? "non-site-groups" : "axon-groups";
  const [data, setData] = useState(null), [target, setTarget] = useState(""), [draft, setDraft] = useState({});
  const [error,setError] = useState(""), [busy,setBusy] = useState(false), [reload,setReload] = useState(0);
  const dirty = Object.keys(draft).length > 0;
  useEffect(() => {
    if (!dirty) return;
    const warn = e => { e.preventDefault(); e.returnValue = ""; };
    window.addEventListener("beforeunload",warn);
    return () => window.removeEventListener("beforeunload",warn);
  }, [dirty]);
  useEffect(() => {onDirtyChange(dirty); return () => onDirtyChange(false);}, [dirty,onDirtyChange]);
  useEffect(() => {
    if (!backendAvailable) return;
    let active = true;
    setBusy(true); setError(""); setData(null); setTarget("");
    localApi.reviewTargets(key,source.normalizedKey).then(result => {
      if (!active) return;
      setData(result);
      if (result.matches.length === 1) setTarget(String(result.matches[0].rowNumber));
      if (result.matches.length > 1) setError("Duplicate exact matches require reconciliation. No record was automatically selected.");
    }).catch(e => {if(active) setError(e.message);}).finally(()=>{if(active) setBusy(false);});
    return () => {active=false;};
  }, [key,source.normalizedKey,backendAvailable,reload]);
  const newSite = target.startsWith("site:");
  const record = newSite ? null : data?.targets.find(row => String(row.rowNumber) === target);
  const identity = source.sourceType === "Device Home"
    ? {"Device Home Name (API)":source.sourceId,"Normalized Device Home Key":source.normalizedKey}
    : {"Axon Group ID":source.normalizedKey,[nonSite ? "Group Name" : "Axon Group Name"]:source.sourceId};
  if (source.externalGroupId) identity["External Group ID"] = source.externalGroupId;
  const fields = (data?.editableFields || []).filter(field => !["Device Home Name (API)","Normalized Device Home Key","Axon Group ID","External Group ID","Axon Group Name","Group Name"].includes(field));
  function value(field) {return draft[field] ?? record?.values[field] ?? "";}
  function change(field,v) {
    setDraft(current => {const next={...current};if(v === (record?.values[field] || "")) delete next[field]; else next[field]=v;return next;});
  }
  async function save(e) {
    e.preventDefault();
    if (!value("Review Notes").trim()) {setError("Document the basis for the decision in Review Notes.");return;}
    if (!record && target !== "new" && !newSite) {setError("Select the intended target before saving.");return;}
    setBusy(true);setError("");
    try {
      const result = newSite
        ? await localApi.createRelationship({key, targetRowNumber:Number(target.slice(5)), expectedRevision:data.revision, values:{...identity,...draft}})
        : target === "new"
        ? await localApi.addCrosswalkRow(key,{...identity,...draft})
        : await localApi.saveCrosswalkRow(key,record.rowNumber,{...identity,...draft},record.values);
      setDraft({});
      showToast(result.projectionWarning || "Review decision saved to the shared workspace. Axon was not changed.");
      setReload(v=>v+1);onSaved?.();
    } catch(e) {setError(e.message);} finally {setBusy(false);}
  }
  return <section className="inline-review-editor" aria-label="Edit selected review record">
    <h3>Edit this review</h3><p>Save here without leaving the review screen. Axon source identity is locked.</p>
    {!backendAvailable ? <p role="alert">Local editing is unavailable. Retry the local panels or reopen with the Python launcher.</p> : <>
      {source.sourceType === "Axon Group" && <label>Relationship type<select value={nonSite ? "non-site" : "site"} disabled={dirty || busy} onChange={e=>setNonSite(e.target.value==="non-site")}><option value="site">Site-related Group</option><option value="non-site">Non-site / command / administrative Group</option></select></label>}
      {error && <p role="alert">{error}</p>}
      {busy && <p role="status">Loading or saving local review data…</p>}
      {data && <form onSubmit={save}><fieldset disabled={busy}>
        <label>{nonSite ? "Group register record" : "Reviewed target site"}<select value={target} disabled={dirty} onChange={e=>{setTarget(e.target.value);setDraft({"Review Notes":""});}}>
          <option value="">Choose explicitly…</option>
          {data.targets.map(row=><option key={row.rowNumber} value={row.rowNumber}>{data.matches.length ? "Existing mapping: " : "Available site: "}{[row.values["Site ID"],row.values["Office Name"],row.values["Group Name"],row.values.Component,row.values["Region / AOR"]].filter(Boolean).join(" · ") || `Record ${row.rowNumber}`}</option>)}
          {!nonSite && !data.matches.length && <optgroup label="Create another relationship to an existing site">{(data.sites || []).map(row=><option key={row.rowNumber} value={`site:${row.rowNumber}`}>New relationship: {[row.values["Site ID"],row.values["Office Name"],row.values.Component,row.values["Region / AOR"]].filter(Boolean).join(" · ")}</option>)}</optgroup>}
          {nonSite && !data.matches.length && <option value="new">Create a non-site Group record</option>}
        </select></label>
        {!data.targets.length && !data.sites?.length && !nonSite && <p>No governed site is available yet. Add the physical site in Setup first; geography is never inferred.</p>}
        {(record || target === "new" || newSite) && <>
          {fields.map(field=><label key={field}>{field}{data.fieldOptions[field] ? <select value={value(field)} onChange={e=>change(field,e.target.value)}><option value="">Choose…</option>{[...new Set([value(field),...data.fieldOptions[field]].filter(Boolean))].map(v=><option key={v}>{v}</option>)}</select> : <textarea rows={field === "Review Notes" ? 3 : 1} value={value(field)} onChange={e=>change(field,e.target.value)}/>}</label>)}
          <button className="primary-button" disabled={!dirty} type="submit">Save review decision</button>
        </>}
        <button className="secondary-button" type="button" onClick={()=>{setDraft({});setReload(v=>v+1);}}>Reset / reload review</button>
      </fieldset></form>}
      {!data && !busy && <button className="secondary-button" type="button" onClick={()=>setReload(v=>v+1)}>Retry review record</button>}
    </>}
  </section>;
}
