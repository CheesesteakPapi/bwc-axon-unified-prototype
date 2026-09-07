import test from "node:test";
import assert from "node:assert/strict";
import { build } from "esbuild";
import { createElement } from "react";
import { renderToString } from "react-dom/server";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);

async function loadComponent(path) {
  const result = await build({
    entryPoints: [path], bundle: true, write: false, format: "cjs", platform: "node",
    jsx: "automatic", external: ["react", "react/*"], loader: { ".css": "empty" },
  });
  const module = { exports: {} };
  new Function("require", "module", "exports", result.outputFiles[0].text)(require, module, module.exports);
  return module.exports;
}

test("Provisioning entry module renders and synchronization errors remain actionable", { timeout: 15000 }, async () => {
  const { App } = await loadComponent(new URL("../src/App.jsx", import.meta.url).pathname);
  assert.match(renderToString(createElement(App)), /BWC Operations/);
  const { SyncHealth } = await loadComponent(new URL("../../ui/SyncHealth.jsx", import.meta.url).pathname);
  const failed = renderToString(createElement(SyncHealth, { error: true, checkedAt: "", onRetry() {}, loadDiagnostics() {} }));
  assert.match(failed, /Automatic synchronization unavailable/);
  assert.match(failed, /Retry local connection/);
  assert.match(failed, /Saved data is retained/);
});
