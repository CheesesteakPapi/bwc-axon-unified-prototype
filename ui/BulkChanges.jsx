import { useEffect, useRef, useState } from "react";

export function BulkChanges({ count, fields, options = {}, signature, disabled, onPreview, onApply, onDirtyChange }) {
  const [field, setField] = useState(""), [value, setValue] = useState("");
  const [changes, setChanges] = useState({}), [reason, setReason] = useState("");
  const [preview, setPreview] = useState(null), [busy, setBusy] = useState(false);
  const [error, setError] = useState(""), [page, setPage] = useState(0);
  const currentDraft = useRef("");
  currentDraft.current = JSON.stringify([signature, changes, reason]);
  useEffect(() => { setPreview(null); setPage(0); }, [signature]);
  useEffect(() => { onDirtyChange?.(Object.keys(changes).length > 0); }, [changes, onDirtyChange]);
  useEffect(() => () => onDirtyChange?.(false), [onDirtyChange]);
  const selectedField = fields.includes(field) ? field : fields[0] || "";
  const choices = options[selectedField];
  async function review() {
    if (!count || !reason.trim() || !Object.keys(changes).length) {
      setError("Select records, add at least one field, and enter a shared reason."); return;
    }
    setBusy(true); setError("");
    const requestDraft = currentDraft.current;
    try {
      const result = await onPreview(changes, reason.trim());
      if (requestDraft !== currentDraft.current) throw Error("Selection or changes changed. Preview again.");
      setPreview(result); setPage(0);
    }
    catch (e) { setError(e.message); setPreview(null); }
    finally { setBusy(false); }
  }
  async function apply() {
    setBusy(true); setError("");
    try { await onApply(changes, reason.trim(), preview); setChanges({}); setPreview(null); setReason(""); }
    catch(e) { setError(e.message); setPreview(null); }
    finally { setBusy(false); }
  }
  const items = preview?.preview || [];
  const shown = items.slice(page * 25, page * 25 + 25);
  return <details className="bulk-changes"><summary>Bulk update {count} selected records</summary>
    <p>Choose shared fields, preview all affected records, then confirm once. Source identities stay unchanged.</p>
    <fieldset disabled={disabled || busy}><legend>Shared changes</legend>
      <label>Field<select aria-label="Bulk field" value={selectedField} onChange={e=>{setField(e.target.value);setValue("");setPreview(null);}}>{fields.map(f=><option key={f}>{f}</option>)}</select></label>
      <label>New value{choices ? <select aria-label="Bulk new value" value={value} onChange={e=>{setValue(e.target.value);setPreview(null);}}><option value="">Blank / clear (if allowed)</option>{choices.map(o=><option key={typeof o === "string" ? o : o.value} value={typeof o === "string" ? o : o.value}>{typeof o === "string" ? o : o.label}</option>)}</select> : <input aria-label="Bulk new value" value={value} onChange={e=>{setValue(e.target.value);setPreview(null);}}/>}</label>
      <button type="button" disabled={!selectedField} onClick={()=>{setChanges(c=>({...c,[selectedField]:value}));setPreview(null);}}>Add shared field</button>
      <ul>{Object.entries(changes).map(([f,v])=><li key={f}>{f}: {options[f]?.find?.(o=>o.value === v)?.label || v || "(blank)"} <button type="button" aria-label={`Remove ${f} change`} onClick={()=>{setChanges(c=>{const n={...c};delete n[f];return n;});setPreview(null);}}>Remove</button></li>)}</ul>
      <label>Shared change reason<textarea aria-label="Bulk change reason" value={reason} onChange={e=>{setReason(e.target.value);setPreview(null);}}/></label>
      <button type="button" disabled={!count || !reason.trim() || !Object.keys(changes).length} onClick={review}>Preview bulk changes</button>
      <button type="button" onClick={()=>{setChanges({});setPreview(null);setReason("");setError("");}}>Discard bulk draft</button>
    </fieldset>
    {busy && <p role="status">Validating or saving the selected records…</p>}
    {error && <p role="alert">{error}</p>}
    {preview && <section aria-label="Bulk change preview"><p>{preview.selectedCount} selected · {preview.changedCount} changed · {preview.unchangedCount} unchanged. Nothing saved yet.</p>
      <div className="bulk-preview-table"><table><thead><tr><th>Record</th><th>Field</th><th>Before</th><th>After</th></tr></thead><tbody>{shown.flatMap((row,i)=>row.differences.map(d=><tr key={`${i}:${d.field}`}><td>{row.label}</td><td>{d.field}</td><td>{d.before || "(blank)"}</td><td>{d.after || "(blank)"}</td></tr>))}</tbody></table></div>
      <button type="button" disabled={!page || busy} onClick={()=>setPage(p=>p-1)}>Previous preview page</button>
      <span> Page {page+1} of {Math.max(1,Math.ceil(items.length/25))} </span>
      <button type="button" disabled={(page+1)*25 >= items.length || busy} onClick={()=>setPage(p=>p+1)}>Next preview page</button>
      <p><button className="bulk-confirm" type="button" disabled={disabled || busy || !preview.changedCount} onClick={apply}>Confirm {preview.changedCount} record updates</button></p>
    </section>}
  </details>;
}
