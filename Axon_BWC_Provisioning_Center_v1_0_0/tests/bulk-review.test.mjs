import test from "node:test";
import assert from "node:assert/strict";
import {previewBulkUsers} from "../src/bulkReview.js";
const run = {runId:"synthetic-run",revision:3,rows:Array.from({length:1500},(_,i)=>({rowId:String(i),email:`test${i}@example.test`,role:i === 0 ? "Supervisor" : "User",groupName:"Old",groupExternalId:"old"}))};
test("bulk preview covers 1500 selected users, omits no-ops and preserves source",()=>{
 const before=JSON.stringify(run);
 const result=previewBulkUsers(run,new Set(run.rows.map(r=>r.rowId)),{Role:"Supervisor"},[]);
 assert.equal(result.selectedCount,1500); assert.equal(result.changedCount,1499); assert.equal(result.unchangedCount,1);
 assert.equal(result.revision,3); assert.equal(result.edits.at(-1).rowId,"1499");
 assert.equal(JSON.stringify(run),before);
});
test("bulk Group selection resolves exact external ID and supports deliberate clearing",()=>{
 const selected=new Set(["1"]);
 const groups=[{externalId:"g1",name:"Same name"},{externalId:"g2",name:"Same name"}];
 assert.deepEqual(previewBulkUsers(run,selected,{Group:"g2"},groups).edits[0].changes,{groupName:"Same name",groupExternalId:"g2"});
 assert.deepEqual(previewBulkUsers(run,selected,{Group:""},groups).edits[0].changes,{groupName:"",groupExternalId:""});
 assert.throws(()=>previewBulkUsers(run,selected,{Group:"unknown"},groups),/exact Group/);
});
test("bulk identity edits and stale selections are rejected",()=>{
 assert.throws(()=>previewBulkUsers(run,new Set(["1"]),{Email:"other@example.test"},[]),/Identity/);
 assert.throws(()=>previewBulkUsers(run,new Set(["missing"]),{Role:"User"},[]),/selected people changed/);
 assert.throws(()=>previewBulkUsers(run,new Set(),{Role:"User"},[]),/Select/);
});
