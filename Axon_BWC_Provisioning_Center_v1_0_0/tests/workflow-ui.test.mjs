import test from "node:test";
import assert from "node:assert/strict";
import { parseClipboard, stepForRun, approvalCurrent, submissionCopy } from "../src/workflowUi.js";

test("Excel paste accepts headers, BOM, CRLF, quoted group and optional group", () => {
  assert.deepEqual(parseClipboard('\uFEFFEmail\tRole\tGroup Name\r\na@example.test\tPrototype User\t"Test, Group"\r\nb@example.test\tPrototype User\t'), [
    {Email:"a@example.test",Role:"Prototype User","Group Name":"Test, Group"},
    {Email:"b@example.test",Role:"Prototype User","Group Name":""},
  ]);
});
test("CSV supports reordered recognized headers and ignores unrelated fields", () => {
  assert.deepEqual(parseClipboard('Ignored,Axon Role,Work Email,Group\nx,Prototype User,a@example.test,"Test, Group"'), [
    {Email:"a@example.test",Role:"Prototype User","Group Name":"Test, Group"}
  ]);
});
test("clipboard text is never evaluated and malformed input is rejected", () => {
  assert.equal(parseClipboard('a@example.test,=TEST(),')[0].Role,"=TEST()");
  assert.throws(()=>parseClipboard('"unfinished'),/unclosed quote/);
  assert.throws(()=>parseClipboard("a,b,c,d"),/columns/);
});
test("clipboard run limit accepts 1500 and rejects 1501 globally", () => {
  const rows = Array.from({length:1500},(_,i)=>`test${i}@example.test\tPrototype User`);
  assert.equal(parseClipboard(rows.join("\n")).length,1500);
  assert.throws(()=>parseClipboard([...rows,"extra@example.test\tPrototype User"].join("\n")),/1,500/);
});
test("workflow routes reflect saved state without inventing completed steps", () => {
  assert.equal(stepForRun(null),0);assert.equal(stepForRun({status:"Draft"}),0);
  assert.equal(stepForRun({status:"Needs Review"}),1);assert.equal(stepForRun({status:"Ready for Preview"}),2);
  assert.equal(stepForRun({status:"Awaiting Submission"}),3);assert.equal(stepForRun({status:"Monitoring"}),4);
});
const approved = () => ({runId:"test-run",revision:3,validation:{valid:true},generation:{userHash:"u",groupHash:"g"},activeSnapshotIds:{Users:"test-snapshot"},approval:{approvedAt:"test-time",runId:"test-run",revision:3,userHash:"u",groupHash:"g",snapshotIds:{Users:"test-snapshot"}},chunks:[]});
test("approval requires matching revision, content, snapshots and valid rows", () => {
  assert.equal(approvalCurrent(approved()),true);
  for(const change of [{revision:4},{generation:{userHash:"other",groupHash:"g"}},{activeSnapshotIds:{}},{validation:{valid:false}},{approval:{}}]) assert.equal(approvalCurrent({...approved(),...change}),false);
});
test("Submit never claims an unapproved preview is approved", () => {
  assert.match(submissionCopy({chunks:[]})[0],/required/);
  assert.equal(submissionCopy(approved())[1],"Nothing has been submitted to Axon yet.");
});
test("snapshot key ordering does not invalidate equivalent approval", () => {
  const run = approved();
  run.activeSnapshotIds = {Users:"u",Groups:"g"};
  run.approval.snapshotIds = {Groups:"g",Users:"u"};
  assert.equal(approvalCurrent(run),true);
});
test("submission history overrides the nothing-submitted notice", () => {
  for(const chunk of [{axonJobId:"TEST-JOB"},{status:"submitted"},{status:"ambiguous"}])
    assert.match(submissionCopy({...approved(),chunks:[chunk]})[0],/submission history/);
});
