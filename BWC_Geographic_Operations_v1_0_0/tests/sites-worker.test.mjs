import assert from "node:assert/strict";
import { access, readFile } from "node:fs/promises";
import test from "node:test";

test("emits the standalone client entry point", async () => {
  const index = new URL("../dist/client/index.html", import.meta.url);
  await access(index);
  const html = await readFile(index, "utf8");
  assert.match(html, /<script[^>]+type="module"/);
  assert.doesNotMatch(html, /\.openai|cloudflare/i);
});
