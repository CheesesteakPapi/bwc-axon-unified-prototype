import test from "node:test";
import assert from "node:assert/strict";
import { loadWorkspace, devicePullNeedsScope } from "../src/workspaceUi.js";

test("a hanging dashboard and failed summary do not disable editors", async () => {
  const seen = [], errors = [];
  const api = { health: async()=>true, session:async()=>({}), config:async()=>({}),
    dashboard:()=>new Promise(()=>{}), governanceSummary:async()=>{throw Error("fixture failure");} };
  const stop = loadWorkspace(api, {success:(name)=>seen.push(name), failure:(name)=>errors.push(name)});
  await new Promise(resolve=>setImmediate(resolve));
  assert.deepEqual(seen.sort(),["config","health","session"]);
  assert.deepEqual(errors,["governanceSummary"]);
  stop();
});

test("unmounted panels ignore late responses", async () => {
  let calls=0;
  const api=Object.fromEntries(["health","session","config","dashboard","governanceSummary"].map(name=>[name,async()=>({})]));
  const stop=loadWorkspace(api,{success:()=>calls++,failure:()=>calls++});
  stop();
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(calls,0);
});

test("unfiltered device pulls require explicit opt-in; model scopes allow comma lists", () => {
  assert.equal(devicePullNeedsScope(["Devices"],{},false),true);
  assert.equal(devicePullNeedsScope(["Devices"],{deviceModel:"  "},false),true);
  assert.equal(devicePullNeedsScope(["Devices"],{deviceModel:"Synthetic A,Synthetic B"},false),false);
  assert.equal(devicePullNeedsScope(["Devices"],{deviceStatus:"IN_STOCK"},false),false);
  assert.equal(devicePullNeedsScope(["Devices"],{deviceHomeId:"synthetic-home"},false),false);
  assert.equal(devicePullNeedsScope(["Devices"],{},true),false);
  assert.equal(devicePullNeedsScope(["Users"],{},false),false);
});
