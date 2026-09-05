# Feature enhancement verification — 2026-09-04

This supplements the completed V3.1 correction QA at `ad45d05`.

- Geographic backend suite: 39 tests passed (33 existing plus six new). Production UI build and standalone asset check passed. Final browser reload confirmed updated filter labels and no browser console errors. Publication boundary and whitespace checks passed.

- Six new backend integration tests passed using an isolated 605-device synthetic workspace. They cover paging/search past row 500; combined filters; all-matching CSV export after restart; full-versus-filtered scope; missing Devices; stale export revision; concurrent governance change; formula-safe UTF-8 CSV; and HTTP session enforcement.
- Interactive checks in the app browser confirmed six simultaneous selection filters plus review flags (101 matching devices), page 2 of 3, export confirmation for all 101 matches, search for record 604, filters preserved across Dashboard navigation, and empty-result/reset behavior.
- At 768-pixel viewport width, document width remained 768 pixels, the filter grid used two columns, and Tab moved focus from Model to Disposition. This is a focused responsive/keyboard check, not a complete accessibility evaluation.
- The optional standalone Playwright script could not launch Chromium in the restricted macOS shell (Mach service permission denied). The same interaction sequence was checked using the available app browser. Do not report that standalone script as a passing automated browser suite.

## Repeatable checks

From the Geographic Operations component:

```text
python3 -m unittest discover -s tests -q
npm run build
npm run test:ui
python3 -m tests.serve_inventory_fixture
```

The last command prints a temporary loopback launch URL for a synthetic dataset. Open it for manual checks, or pass it to `node tests/inventory-browser.mjs "<URL>"` with a separately installed development Playwright runtime. `BWC_PLAYWRIGHT_MODULE` and `BWC_TEST_BROWSER` can specify existing developer runtime paths. Stop the fixture with Ctrl-C when finished; it cleans up its temporary workspace. Playwright is not required to run the distributed app.

## Assignment increment

- Geographic backend suite: 48 tests passed (39 prior plus nine assignment tests). Tests use temporary synthetic workspaces, not agency records.
- Production UI build, standalone asset test, publication-boundary scan, and whitespace checks passed for the assignment increment.
- Added coverage for all count buckets and records past row 500; exact User ID/serial joins; missing/duplicate identity; independent Users/Devices availability; valid empty snapshots; filtered scope/full precedence; full matching export after restart; both snapshot provenance records; formula-safe UTF-8 without BOM; stale/concurrent revisions; and authenticated HTTP routes.
- Interactive app-browser checks used 605 synthetic users and 906 devices. Combined Supervisor and three-or-more filters produced 151 matches. Page 2 exported all 151 matches, and navigation to Inventory and back retained filters and page.
- A selected user's detail listed exactly three serials, including one Lost and two Assigned devices. Closing details restored keyboard focus to that user's button. Searching for user 604 returned one user with zero devices and the appropriate full-baseline explanation.
- At a 768-pixel viewport the document remained 768 pixels wide and filters used two columns. No console errors were observed. These focused checks are not Windows Narrator or complete accessibility acceptance.
- Repeat interactive assignment checks with `python3 -m tests.serve_assignment_fixture`; use its temporary loopback URL and stop with Ctrl-C for cleanup.

## Limits

No live tenant calls, native build/signing, new distribution ZIP, or receiving-machine acceptance is claimed. Dashboard preview tables retain their existing limits; dedicated Inventory and Device Assignments pages cover all saved records. Their CSVs cover all matches; zero matches produce headers only. Filters persist during navigation in the current browser session, not across application restarts. Governed role-based count expectations and the record-level exception queue remain future work.
