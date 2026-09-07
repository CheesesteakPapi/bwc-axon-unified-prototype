# ForgeFlow review — V3.2.1 source testing candidate

## Follow-up: crosswalk and user bulk review

The accepted focused design now supports batch review in both applications.
Crosswalk Review includes a table-mode switch; operators do not need to leave
Review to update existing mappings. User Review Exceptions and Preview Changes
share the same multi-field before/after pattern and explicit selection controls.
Selection is limited to 1,500 records and never inferred from a hidden page.
Individual source relationship creation remains separate from bulk decisions.

Verification after this addition: **135 tests passed** (26 root Python, 59
Geographic Python, 31 Provisioning Python, 5 Geographic UI, 14 Provisioning UI);
both builds passed. Synthetic browser checks saved a crosswalk batch with
appended rationale and a 30-user role revision across two preview pages.
The blocked filter returned zero for ready users, and changing search cleared
prior selection. Approval remained a separate action. No live submission occurred.

Confirmed safeguards: atomic batch validation, stale preview/revision rejection,
source identity protection, exact Group ID resolution, no-op reporting and old
approval invalidation. Remaining hypotheses: whether operators discover the
collapsed bulk panel unaided and whether 25-record preview pages are comfortable.
Validate those with representative operators; no new usability score is claimed.
The prior review below records the earlier 127-test checkpoint.

Date: 2026-09-06. Status: **testing**, local feature-branch changes only.
Method: ForgeFlow Build followed by Review; focused improvements to the existing
product, not a redesign or architecture replacement.

## Product intent and preserved strengths

Non-technical operators prepare users and review exceptions; provisioning
administrators approve and submit deliberate writes; operational/support staff
review saved devices, relationships, scope, freshness, and local health.

The shared per-user SQLite workspace remains authoritative. Atomic snapshot
activation, immutable submitted revisions, baseline/pending separation,
assignment-only inline edits, and separate approval/submission remain in place.
There are no microservices, external analytics, native build requirements, or
automatic Axon writes.

## Delivered slices

| Slice | Operator outcome | Implementation and evidence |
|---|---|---|
| Trustworthy state | A completed job is not mistaken for a confirmed change; long refreshes retain ownership; tenant data cannot silently mix; resource age is explicit | SharedWorkspace confirmation, heartbeat/fencing and tenant binding; selected-snapshot freshness in Geographic dashboard. Seven focused trustworthy-state tests plus existing atomic/cancellation regressions |
| Complete review | Saved decisions remain findable; another relationship can be created against an occupied site; full and filtered device pulls are explicit | Geographic review queue includes reviewed rows; inline relationship endpoint uses revision/identity validation and audit. Browser saved a synthetic relationship and found it under Reviewed; scope serialization has a dedicated UI test |
| Operator clarity | Routine work has a direct destination; advanced setup is collapsed; local synchronization failure and support details are visible | Dedicated Review navigation, shared SyncHealth and typography rules, payload-free bounded local diagnostics. Browser inspected both applications and approval handoff |

Location, AOR and job-title enrichment gaps remain optional warnings. Group
assignment may be blank. Non-site/command Groups are not forced onto a map.
Entra Email and UPN remain separate; proposed Status remains Active.

## ForgeFlow quality gates

| Gate | Result | Evidence and limitation |
|---|---|---|
| Product intent | PASS | Three authorized slices implemented without replacing the accepted architecture |
| UX and cognitive load | PASS for synthetic walkthrough | Created a site relationship inline; Reviewed filter retained it. Changed a personnel Location inline with a reason; revision advanced. Approval advanced to Submit while explicitly stating nothing was submitted |
| Visual credibility | PASS for inspected screens | Rendered Home, focused Review, Provisioning Preview/Submit and diagnostics in the in-app browser; desktop and approximately 768-pixel narrow layout inspected. Dense review tables scroll within their region |
| Accessibility/platform | NOT RUN for complete acceptance | Semantic controls and narrow layout inspected, but no full keyboard-only, screen-reader, 200% zoom, or Windows 11 acceptance session. Browser inspection on macOS is not Windows certification |
| Function/architecture | PASS automated | 25 root Python, 55 Geographic Python, 31 Provisioning Python; 5 Geographic UI, 11 Provisioning UI; 127 total. Both Vite builds pass |
| Data/privacy | PASS for scoped checks | Synthetic isolated workspaces only. Tenant mismatch/stale binding rejected; expired refresh cannot activate; missing snapshot fields do not confirm. Diagnostics test verifies bounded field allowlist |
| Measurement/operations | PASS for local diagnostics scope | In-browser diagnostics displayed request IDs/status/timing with no payloads. UI renders actionable synchronization failure. No claim of measured vendor latency or live throughput improvement |
| Release/enablement | PASS for local candidate only | README, API contract, data model, QA and master notes updated. Package tooling uses candidate version. No new ZIP, commit, push, or deployment made |
| Live integration/production acceptance | NOT RUN | No live Axon/Entra credentials, calls, writes, real personnel import, or agency endpoint acceptance used |

The first browser pass found a Provisioning module-scope JSX expression that
prevented startup despite a successful build. It was removed, the settings control
was placed inside its component, and browser startup was retested successfully.
A module-evaluation/render smoke test now guards that failure class. Initial
test-harness attempts using Vite SSR were replaced with an in-memory esbuild
render check; the final test passes.

## State and performance semantics

- Confirmation requires a completed matching user chunk and a full Users snapshot
  where Email and External ID identify one record and submitted observable values
  match. A missing Role, supervisor or other submitted field remains unverified,
  not assumed correct. Identity ambiguity also remains pending.
- Group job success is not evidence of Group membership from a Users snapshot.
- A heartbeat renews a resource lease during the worker's lifetime. Snapshot
  activation checks its unique token and expiry transactionally. Failure, canceled
  work, and obsolete workers preserve the prior active baseline.
- Device scopes do not merge. Full inventory ignores model/status/Home inputs;
  tracked-model mode excludes custom status/Home constraints; custom filtered mode
  uses its entered filters. A filtered refresh cannot replace a full baseline.
- Resource timestamps describe successful snapshot activation, not the local
  revision poll. The most recent resource activity does not make older resources
  fresh.
- Local diagnostics retain at most 200 request summaries until process exit.
  They are authenticated, have no URL/body/identity fields, and are not uploaded.
  These are HTTP request timings, not an Axon API phase-performance trace.
- Confirmation now indexes snapshot identities and caches completed chunk rows
  per run revision. This avoids repeated full-list scans; no throughput benchmark
  or vendor-side delta-refresh capability is implied.

## Safe testing and upgrade

1. Keep the prior source/package unchanged. Close **both** applications before
   changing the runtime version. Do not run old and new refresh workers together.
2. Back up the closed per-user runtime/shared workspace using approved local
   storage. Do not put the database, its sidecars, credentials or exports in Git.
3. Launch this source candidate through the existing per-user Python launchers.
   The additive lease-token column is created transactionally; existing data is
   retained. The bound tenant is not guessed for legacy data.
4. In connection settings, enter the intended tenant. If prompted, verify that the
   existing data belongs to it before checking the one-time confirmation and
   saving. Use Reload settings after a revision conflict. A different tenant
   requires a separate workspace, not an override of the existing binding.
5. Start with saved data and synthetic/approved test runs. Confirm freshness and
   scope, edit a review record, then verify approval is separate from submission.
   Do not submit live changes merely to validate this candidate.
6. If testing fails, close both applications and preserve the failed workspace for
   approved support review. A rollback should use the preserved pre-upgrade
   workspace with its matching previous source version; do not assume old code
   enforces the new tenant/lease safeguards. Never overwrite newer operational
   work without reconciliation and operator approval.

The browser previews created during this work use disposable synthetic fixtures,
not the operator's operational database. Their launch tokens are intentionally
omitted from this report.

## Three highest-value next checks

These are recommendations, not newly authorized implementation or release work.

| Priority | Next improvement/check | Benefit, effort and dependencies | Verify success |
|---|---|---|---|
| 1 | Controlled Windows and tenant acceptance | Highest assurance for actual operators; medium validation effort, requires approved test accounts/tenant and a standard-user Windows machine | No false confirmations; no cross-tenant refresh; editing invalidates approval; cancellation/long pull keeps baseline; launch without elevation |
| 2 | Phase-level refresh diagnostics | Distinguishes network/page pacing from normalization and database work; small-to-medium focused change, needs an approved privacy-safe event schema | Reproduce a slow pull and identify its phase without exposing records, URLs, IDs or credentials; compare scoped pulls on the same approved dataset |
| 3 | Operator usability/accessibility session | Tests whether the simpler review entry actually reduces assistance; small research effort, depends on representative operators and assistive-input testing | Operators independently find a record, save a relationship, distinguish Pending/Confirmed and approve without accidentally submitting; keyboard/zoom issues recorded and corrected |

Confirmed remaining limits: no live throughput measurements, no complete Windows
or accessibility acceptance, and no Axon incremental-change contract. Hypothesis:
collapsing advanced navigation and separating Review reduces cognitive load; this
needs operator observation, not a self-assigned usability score. No rewrite or
microservice migration is recommended.
