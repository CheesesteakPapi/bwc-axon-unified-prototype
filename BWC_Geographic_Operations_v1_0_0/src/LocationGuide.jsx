import { useEffect, useState } from "react";
import { localApi } from "./api.js";

export function LocationGuide({ onDirtyChange, showToast }) {
  const [data,setData] = useState(null), [page,setPage] = useState(1), [search,setSearch] = useState(""), [query,setQuery] = useState("");
  const [record,setRecord] = useState(null), [draft,setDraft] = useState({}), [step,setStep] = useState(0), [error,setError] = useState(""), [busy,setBusy] = useState(false);
  const dirty = Object.keys(draft).length > 0;
  useEffect(() => { onDirtyChange(dirty); return () => onDirtyChange(false); }, [dirty,onDirtyChange]);
  useEffect(() => {
    let active = true; setBusy(true);
    localApi.crosswalk("personnel-aor",{page,pageSize:25,search:query}).then(result => { if(active) setData(result); }).catch(e => {if(active) setError(e.message);}).finally(() => {if(active) setBusy(false);});
    return () => {active=false;};
  }, [page,query]);
  useEffect(() => {
    const warn = e => {if(dirty){e.preventDefault();e.returnValue="";}};
    window.addEventListener("beforeunload",warn);return () => window.removeEventListener("beforeunload",warn);
  }, [dirty]);
  function value(field) { return draft[field] ?? record?.values[field] ?? ""; }
  function change(field,v) { setDraft(current => {const next={...current};if(v === (record.values[field] || "")) delete next[field];else next[field]=v;return next;}); }
  async function save() {
    if(!value("Personnel AOR").trim() || !value("Review Notes").trim() || !value("Reviewer").trim()) {setError("Enter an area, reviewer, and reason before saving a reviewed match. You may leave the location unmatched instead.");return;}
    setBusy(true);setError("");
    try {
      await localApi.saveCrosswalkRow("personnel-aor",record.rowNumber,{...draft,"Review Status":"Approved","Reviewed At UTC":new Date().toISOString()},record.values);
      setDraft({});setStep(0);setRecord(null);
      showToast("Personnel location match approved and saved to the shared workspace. Axon was not changed.");
      try { setData(await localApi.crosswalk("personnel-aor",{page,pageSize:25,search:query})); }
      catch { setError("The match was saved, but the list could not reload. Refresh this page before another edit."); }
    } catch(e){setError(e.message);} finally{setBusy(false);}
  }
  function leave() { if(dirty && !window.confirm("Discard these unsaved edits and leave this location unchanged?")) return;setDraft({});setRecord(null);setStep(0); }
  return <section className="location-guide">
    <nav aria-label="Location matching steps">{["Choose a location","Confirm the area","Review and save"].map((text,i) => <span key={text} aria-current={step === i ? "step" : undefined}><b>{i+1}</b>{text}</span>)}</nav>
    <div className="location-guide-main"><h2>Review location matches</h2><p>Connect a personnel location to its area of responsibility. This does not block account creation.</p>
      {error && <p role="alert" className="inline-alert">{error}</p>}
      {step === 0 ? <><form className="guide-search" onSubmit={e => {e.preventDefault();setPage(1);setQuery(search);}}><label>Find a directory location<input value={search} onChange={e=>setSearch(e.target.value)} /></label><button className="secondary-button" disabled={busy}>Search</button></form>
        <div className="guide-locations">{data?.rows.map(row=><button key={row.rowNumber} disabled={busy} onClick={()=>{setRecord(row);setStep(1);setError("");}}><strong>{row.values["Directory Location"] || "Unnamed location"}</strong><span>{row.values.Component || "No component"} · {row.values["Review Status"] || "Needs review"}</span></button>)}</div>
        {!busy && !data?.rows.length && <p>No locations found. Enrichment adds observed locations for review, or use the table editor to add a rule.</p>}
        <div className="guide-actions"><button className="secondary-button" disabled={busy || page<=1} onClick={()=>setPage(page-1)}>Previous</button><span>Page {page} of {data?.totalPages || 1}</span><button className="secondary-button" disabled={busy || page >= (data?.totalPages || 1)} onClick={()=>setPage(page+1)}>Next</button></div>
      </> : <><label>Directory location<input value={record.values["Directory Location"] || ""} readOnly /></label><label>Component<input value={record.values.Component || ""} readOnly /></label>
        {step === 1 ? <><label>Area of responsibility<input list="personnel-area-options" value={value("Personnel AOR")} onChange={e=>change("Personnel AOR",e.target.value)} /></label><datalist id="personnel-area-options">{(data?.fieldOptions?.["Personnel AOR"] || []).map(v=><option key={v} value={v}/>)}</datalist>
          <label>Effective personnel location<input value={value("Effective Location")} onChange={e=>change("Effective Location",e.target.value)} /></label>
          <label>Reason for this match<textarea rows="4" value={value("Review Notes")} onChange={e=>change("Review Notes",e.target.value)} /></label>
          <label>Reviewer<input value={value("Reviewer")} onChange={e=>change("Reviewer",e.target.value)} /></label>
          <details><summary>Source and review details</summary>{["Mapping Method","Confidence"].map(field=><label key={field}>{field}<select value={value(field)} onChange={e=>change(field,e.target.value)}><option value="">Select…</option>{[...new Set([value(field),...(data?.fieldOptions?.[field] || (field === "Confidence" ? ["Low","Medium","High"] : ["Exact name","Command hierarchy review","Manual exception"]))])].filter(Boolean).map(v=><option key={v}>{v}</option>)}</select></label>)}</details>
          <div className="guide-actions"><button className="secondary-button" onClick={leave}>Leave unmatched for now</button><button className="primary-button" onClick={()=>{if(!value("Personnel AOR").trim() || !value("Reviewer").trim() || !value("Review Notes").trim()){setError("Enter an area, reviewer, and reason, or leave unmatched for now.");return;}setError("");setStep(2);}}>Review match</button></div><p>Nothing has been saved yet.</p>
        </> : <><h3>Confirm your match</h3><dl>{["Effective Location","Personnel AOR","Mapping Method","Confidence","Reviewer","Review Notes"].map(field=><div key={field}><dt>{field}</dt><dd>{record.values[field] || "blank"} → {value(field) || "blank"}</dd></div>)}</dl><p>This marks the mapping Approved in the shared workspace. It does not submit anything to Axon.</p><div className="guide-actions"><button className="secondary-button" disabled={busy} onClick={()=>setStep(1)}>Back</button><button className="primary-button" disabled={busy} onClick={save}>{busy ? "Saving…" : "Save reviewed match"}</button></div></>}
      </>}
    </div><aside><h3>Why am I seeing this?</h3><p>Directory locations are collected during enrichment for optional review.</p><p>A reviewed match helps recommend an organizational Group. Device Home and device GPS do not determine personnel organization.</p><p>Leaving a location unmatched does not block user import.</p></aside>
  </section>;
}
