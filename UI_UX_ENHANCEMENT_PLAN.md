# UI/UX concept research and next prototype

Status: V3.2.0 implements the recommended Task Home plus Guided Tasks direction following the request to proceed. The record-review workbench remains available for frequent reviewers. See QA_V3_2_0.md for actual verification and remaining acceptance.

## Design recommendation

Use a task-oriented home with Guided Tasks for occasional operators and a Review Workbench for frequent reviewers. This combination is the implemented direction for the next testing candidate. First ask whether operators understand the task and next action; do not use visual novelty as the success measure.

The Frontend App Builder and Imagegen skills were used in concept-review mode. Concepts are static synthetic wireframes, not working screens. The concepts were used as visual references for native React components; browser interactions and responsive layouts are checked before handoff. Do not replace the running application with a screenshot.

| Direction | Purpose | Tradeoff |
|---|---|---|
| Guided Tasks | One location-matching decision at a time with optional fields and next-step guidance | Clearest for occasional users; slower for repetitive bulk work |
| Review Workbench | Compact list beside a selected-record editor | Efficient repeat review; more information visible at once |
| Task Home | Start with Add people, Find devices, Review matches, or Open reports | Best orientation; needs a task screen behind each entry |

## Plain-language organization

Primary destinations: Home, People, Devices, Locations, Reports. Setup & rules remains a secondary entry, with descriptions of who uses it. Use Axon-specific terms where needed, explaining them rather than silently changing their meaning.

| Existing heading | Proposed task label | Context |
|---|---|---|
| Review queue | Matches needing review | Setup & rules |
| Approved Axon Role catalog | Allowed Axon roles | People rules |
| Personnel Location-to-AOR | Personnel location to area | People rules |
| Exact job-title categories | Job title categories | People rules |
| Component/AOR/Job Group rules | Recommended Axon Groups | People rules |
| Directory attribute mapping | Directory field setup | Advanced setup |
| Device Home table | Device Home to site | Locations |
| Axon Group table | Group organization matches | Group setup |
| Non-site Group register | Groups without a site | Group setup |
| Facility Master | Physical sites | Locations |
| Office Presence register | Offices at each site | Locations |
| Tiered Group Master | Axon Groups and hierarchy | Group setup |
| Site-to-Group relationships | Groups linked to sites | Locations |

These are presentation labels, not schema changes. Keep personnel locations, physical facilities, Device Homes, and non-site Groups distinct. Retain all underlying tables and review history.

## Current design-system research

- [USWDS complex-form guidance](https://designsystem.digital.gov/patterns/complete-a-complex-form/progress-easily/) supports meaningful steps, progressive disclosure, contextual help, and actionable error messages. Apply it to provisioning and optional mapping review.
- [Fluent 2 inline drawers](https://fluent2.microsoft.design/components/web/react/core/drawer/usage) keep a record and its detail visible together. Use inline detail on wider screens and an accessible dedicated detail screen on narrow screens; protect unsaved edits.
- Use shared design tokens and component families across both apps: navigation, actions, field labels, record summaries, confirmation summaries, and freshness indicators. Specify accessible focus/error states, not just normal-state styling.

These are current established patterns, not evidence that a decorative style is the most popular or that adoption guarantees usability. Avoid glass effects, nested cards, icon-only navigation, and decorative dashboards when they add effort.

## Prototype acceptance

Test with five representative nontechnical operators using synthetic data. Proposed success targets: at least four can find the correct task within 30 seconds and complete an account-preview or optional-location-review task without help; all five can explain whether anything was saved, approved, or submitted. Record these as future test targets, not achieved results.

Test paste/upload, optional mapping left blank, reviewed role selection, unsaved-change recovery, existing-account comparison, clear final submission, device drilldown, and saved export. Include keyboard-only, explicit field labels, current-step announcement, 200% zoom, narrow-screen reflow, empty/stale/error states, and a 1500-row run without rendering every editable field at once.

No integration implementation, new Axon write, Power BI publishing, or authorization change is part of visual concept selection. The historical Axon integration material is requirements and experimentation, not an existing connector. Separate reporting-process research can inform Reports without expanding the operator workflow.
