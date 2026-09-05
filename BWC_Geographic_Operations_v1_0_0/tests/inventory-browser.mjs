// Optional browser acceptance: start tests.serve_inventory_fixture, then pass its URL.
// Install Playwright separately for development or set BWC_PLAYWRIGHT_MODULE to its module.
import assert from "node:assert/strict";
import path from "node:path";
import { mkdir } from "node:fs/promises";
const { chromium } = await import(process.env.BWC_PLAYWRIGHT_MODULE || "playwright");
const launchUrl = process.argv[2];
if (!launchUrl || new URL(launchUrl).hostname !== "127.0.0.1") throw new Error("Provide the loopback synthetic fixture launch URL.");
const browser = await chromium.launch({ headless: true, executablePath: process.env.BWC_TEST_BROWSER || undefined });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, acceptDownloads: true });
const errors = [];
page.on("pageerror", (error) => errors.push(error.message));
const waitText = (text) => page.getByText(text, { exact: false }).first().waitFor();
try {
  await page.goto(launchUrl);
  await page.getByText("FULL BASELINE", { exact: true }).first().waitFor();
  await page.getByRole("button", { name: "Inventory", exact: true }).click();
  await waitText("605 matches of 605 saved devices");
  await page.getByLabel("Model", { exact: true }).selectOption("Body 4");
  await page.getByLabel("Disposition", { exact: true }).selectOption("Lost");
  await page.getByLabel("Assignment state", { exact: true }).selectOption("Assigned");
  await page.getByLabel("Device Home", { exact: true }).selectOption("Example Home Alpha");
  await page.getByLabel("Component", { exact: true }).selectOption("TEST");
  await page.getByLabel("Mapped AOR", { exact: true }).selectOption("Area Alpha");
  await page.getByLabel("Review flags only", { exact: true }).check();
  await waitText("101 matches of 605 saved devices");
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await waitText("Page 2 of 3");
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export matching CSV", exact: true }).click();
  const download = await downloadPromise;
  const stream = await download.createReadStream();
  let csv = "";
  for await (const chunk of stream) csv += chunk.toString("utf8");
  assert.equal(csv.trimEnd().split("\r\n").length, 102, "export must include all 101 matches, not just page 2");
  assert.match(csv, /TEST-SERIAL-0600/);
  assert.match(csv, /Devices Snapshot ID/);
  assert.match(download.suggestedFilename(), /^BWC_inventory_full_R\d+_\d+T\d+Z\.csv$/);
  await page.getByRole("button", { name: "Reset filters", exact: true }).click();
  await page.getByLabel("Search inventory", { exact: true }).fill("test-serial-0604");
  await waitText("1 matches of 605 saved devices");
  await page.getByRole("button", { name: "Dashboard", exact: true }).click();
  await page.getByRole("button", { name: "Inventory", exact: true }).click();
  assert.equal(await page.getByLabel("Search inventory").inputValue(), "test-serial-0604");
  await waitText("1 matches of 605 saved devices");
  await page.getByLabel("Search inventory").fill("no-synthetic-device-matches");
  await waitText("No devices match. Remove a filter");
  await page.getByRole("button", { name: "Reset filters", exact: true }).click();
  await waitText("605 matches of 605 saved devices");
  if (process.argv[3]) {
    await mkdir(process.argv[3], { recursive: true });
    await page.screenshot({ path: path.join(process.argv[3], "inventory-desktop.png"), fullPage: true });
  }
  await page.setViewportSize({ width: 768, height: 1024 });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true, "tablet view must contain table overflow");
  await page.getByLabel("Model", { exact: true }).focus();
  assert.equal(await page.getByLabel("Model", { exact: true }).evaluate((element) => element === document.activeElement), true);
  if (process.argv[3]) await page.screenshot({ path: path.join(process.argv[3], "inventory-tablet.png"), fullPage: true });
  assert.deepEqual(errors, []);
  console.log("PASS: combined filters, full-scope paging/export, navigation persistence, empty state, tablet overflow, and keyboard focus.");
} finally { await browser.close(); }
