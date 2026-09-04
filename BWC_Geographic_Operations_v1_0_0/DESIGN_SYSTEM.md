# BWC Geographic Operations Design System

Version: v0.3.0
Primary environment: standalone local macOS and Windows 11 prototype
Status: maintained implementation guidance, not a formal accessibility-conformance statement

## Design intent

The interface uses a light, compact enterprise system that follows familiar desktop conventions. Segoe UI is the primary typeface with platform fallbacks; clear hierarchy, visible system state, restrained color, and task-oriented actions take precedence over decoration.

The design must always preserve these product distinctions:

- **ILLUSTRATIVE** versus **LIVE SNAPSHOT** data.
- Axon API facts versus governed crosswalk decisions.
- Complete digitization versus provisional boundary validation.
- OCIO, HSI Domestic, ERO, and HSI International as separate organizational lenses.
- Read-only Axon operations versus editable local crosswalk files and local exports.
- Physical Facilities versus component Office Locations and Office Presences.
- One user role versus multiple tiered Axon Group relationships.

## Typography

The implemented font stack is:

```css
font-family: "Segoe UI", Inter, Arial, sans-serif;
```

Use sentence case for titles, field labels, actions, and explanatory content. Reserve uppercase with increased tracking for short eyebrow labels, navigation group labels, and compact status labels.

| Role | Typical size | Typical weight | Use |
|---|---:|---:|---|
| Micro/status | 9–10 px | 700–800 | Data-mode labels, timestamps, compact metadata |
| Caption | 11–12 px | 600–700 | Field labels, provenance, helper text, legends |
| Body/control | 13–15 px | 400–650 | Instructions, navigation, buttons, table cells |
| Section heading | 16–18 px | 600–700 | Panels and task groups |
| Feature heading | 21–25 px | 600–700 | Modal and report titles |
| Page title/metric | 27–29 px | 600–700 | Primary page heading and headline values |

Do not use small type as the only means of exposing risk, validation state, or an error. Keep essential state in concise body text as well.

## Color tokens

These tokens are implemented in `src/styles.css` and are the canonical v0.3.0 palette.

| Token | Value | Primary role |
|---|---|---|
| Base text | `#10213A` | Default text on white |
| Canvas | `#FFFFFF` | Application, card, and control surface |
| `--navy-950` | `#071B38` | Page titles, strongest text |
| `--navy-900` | `#0A2C59` | Strong secondary text |
| `--navy-800` | `#0A4E9B` | Primary action fill |
| `--blue-700` | `#075AB8` | Links, selected state, information accent |
| `--blue-100` | `#EAF2FB` | Selected/information background |
| `--blue-50` | `#F4F8FD` | Subtle information surface |
| `--slate-800` | `#263A55` | Body and control text |
| `--slate-600` | `#586A81` | Secondary text and metadata |
| `--slate-300` | `#C8D4E2` | Input and control borders |
| `--slate-200` | `#DCE5EF` | Panel and table dividers |
| `--slate-100` | `#EDF2F7` | Neutral status surface |
| `--slate-50` | `#F7F9FC` | Toolbar and hover surface |
| `--green-700` | `#15783A` | Success/live text |
| `--green-100` | `#EAF5E8` | Success/live background |
| `--amber-700` | `#B85B00` | Warning/illustrative text |
| `--amber-600` | `#D97706` | Warning emphasis |
| `--amber-100` | `#FFF3DB` | Warning/illustrative background |
| `--red-700` | `#B42318` | Critical/error text |
| `--red-600` | `#D1192E` | Critical emphasis and badges |
| `--red-100` | `#FFF0F0` | Critical/error background |

Use token pairs as a system: dark semantic text on the related pale background, plus a word, icon, border, or heading that communicates the same state. Never use green, amber, red, blue, a map fill, or marker color as the sole indicator.

The visible keyboard-focus treatment is a 3 px blue outline with a 2 px offset. Keep focus visually distinct from hover and selection. Confirm contrast whenever a foreground/background combination changes; the token list alone is not a contrast certification.

## Spacing, density, and shape

The interface uses a practical 2 px-derived spacing rhythm. Reuse the implemented values rather than introducing isolated measurements.

| Scale | Values | Typical use |
|---|---|---|
| Tight | 4, 6, 8 px | Icon/text gaps, compact status content |
| Control | 10, 12, 14 px | Control padding, toolbar gaps, card rows |
| Section | 16, 18, 20 px | Panel padding and section separation |
| Page | 22, 24, 26, 28 px | Modal and page gutters |

Recurring layout rules:

- 14 px is the normal dashboard grid and panel gap.
- 16–18 px is the common card interior.
- 24–26 px is the desktop page gutter.
- Borders are 1 px slate by default; critical task surfaces may use a semantic accent border.
- Small controls use 4–5 px corner radii; cards use 6–7 px; modals use about 9 px; status pills use a full radius.
- Keep dense operational tables aligned and scannable. Allow horizontal scrolling at narrower widths instead of compressing columns beyond recognition.

Responsive breakpoints in the implementation are 1250 px, 1100 px, and 600 px. Desktop operation is primary; narrower layouts must retain the same data-state and boundary warnings.

## Accessible interaction targets

Use 44 by 44 CSS pixels as the default minimum target for buttons, icon controls, markers, and other direct interactions. Larger implemented controls include 50 px navigation rows and 56 px connection/filter controls. Standard form fields and buttons are approximately 41–44 px high; when a control is below 44 px, provide adequate spacing and review the exception rather than allowing crowded adjacent targets.

Required interaction behavior:

- Every icon-only control has an accessible name.
- The active navigation item exposes current-page state.
- A disclosure trigger exposes expanded state and identifies the controlled panel.
- Popovers and dialogs have a visible heading or accessible name and a keyboard dismissal path.
- Visible focus remains present for buttons, links, inputs, selects, text areas, table-row actions, and map controls.
- Hover never reveals the only route to an action or the only explanation of state.
- Disabled and busy states use text or status semantics in addition to opacity or animation.
- Animation is functional and brief. A spinning progress glyph is accompanied by readable status text.
- Honor `prefers-reduced-motion: reduce` by suppressing nonessential animation and transition duration.

Do not claim keyboard, screen-reader, WCAG, Section 508, or PDF accessibility conformance without a separate test record.

## Components and state language

### Navigation

Navigation is grouped by operational purpose. Dashboard, Map, Crosswalks, Facilities, Users & Access, Inventory, Device Assignments, Reports, and Provenance remain distinct workflows. Use `aria-current="page"` for the active item and keep the active bar, background, weight, and label together.

### Data-mode labels

- **ILLUSTRATIVE:** example data or visual reference; never present it as tenant data.
- **LIVE SNAPSHOT:** current-session API rows; include the refresh timestamp and resource counts.

Live Axon fields can be tenant facts while a geographic relationship remains provisional. Show both states when they coexist.

### Status and alerts

Use red for critical/error, amber for warning/illustrative, green for success/live, and blue for information/provisional review. Always pair the color with explicit language and, where practical, an icon or structural border.

### Tables and forms

- Give each field a visible label.
- Use real table headers for tabular data.
- Preserve raw Axon status separately from reviewed reporting state.
- Use progress elements with accessible labels for disposition summaries.
- Do not make a pointer-only table row the sole means of opening or selecting a record; keep keyboard access in review scope.

### Editable Crosswalk Workspace

- Present Review queue, Device Home table, legacy Axon Group table, and Non-site Group register as named tabs with an associated tab panel.
- Use the same governed editor pattern for Facility Master, Office Presence, Tiered Group Master, and Site-to-Group relationships.
- Use a visible table caption. Mark locked Office Location and geography columns with a named lock icon; give every editable input, select, and text area a row-specific accessible name.
- Show the unsaved-row count in text so dirty-row styling is supplementary. Keep per-row **Save** and **Reset** actions keyboard reachable.
- While a row has a draft, block workspace search, reload, pagination, tab switching, and the workspace **Back** action; warn before browser close or reload. Operators should save or reset before using other navigation.
- Announce loading, errors, save confirmation, backup creation, and conflicts through readable status or alert text. A conflict must tell the operator to reset the draft and reload rather than silently overwriting a newer value.
- Keep the shared-workspace notice visible: governed saves commit only an allowlisted SQLite dataset, then attempt the CSV review/export projection and timestamped backup, and never write to Axon. If projection refresh fails, retain the committed SQLite change and show a clear warning.
- Allow row creation only in the Non-site Group register, Facility Master, Tiered Group Master, and Site-to-Group relationship table. Office Location, Device Home, and legacy office-based Group rows are preserved and cannot be created in the UI.
- Search applies to the whole selected shared-workspace table, pagination shows 25 rows at a time, and **Export full CSV** generates the entire current CSV projection from authoritative SQLite rather than exporting the visible page or an older disk projection.
- Preserve the default 44 by 44 CSS-pixel interaction target for tab, pagination, export, Save, Reset, and new-row controls; retain visible focus and text labels at narrow layouts.

### Facilities workspace

- Lead with summary cards for reviewed Facilities, preserved Office Locations, unlinked offices, network review, co-location, and external hosting.
- Keep the copy-first model notice visible so the operator understands that Office Location IDs remain stable and Facility IDs are created only from reviewed evidence.
- Keep Facility Master and Office Presence as separate tabs. Never combine a building and an office into one ambiguous record.
- At narrow widths, stack summary cards and use a labeled expandable navigation menu. Governance editors use a record list plus detail form rather than a document-width spreadsheet. Remaining analytical tables stay inside their own horizontal-scroll region.

### Users & Access workspace

- Display exactly one role column per user and separate columns for primary, secondary, organizational-area, and additional Group relationships.
- Keep assigned-device count and model summary available without implying a site assignment.
- Clearly label illustrative memberships and live memberships that were not observed; blank values must not look like loading failures.
- Keep User access review, Tiered Group Master, and Site-to-Group relationships as separate named tabs.
- Pair the table with a selected-user detail region at desktop widths and stack it below the table on narrow layouts.

## Organizational map lenses

| UI label | Packaged asset | Intended semantic scope |
|---|---|---|
| OCIO Areas | `/assets/synthetic-coverage-map.svg` | Synthetic placeholder; configure a governed local layer |
| HSI Domestic AORs | `/assets/synthetic-coverage-map.svg` | Synthetic placeholder; configure a governed local layer |
| ERO Field Office AORs | `/assets/synthetic-coverage-map.svg` | Synthetic placeholder; configure a governed local layer |
| HSI International | `/assets/synthetic-coverage-map.svg` | Synthetic placeholder; configure a governed local layer |

### Required semantics

- The selected lens controls the image, alternative text, source/reference label, marker mode, and legend.
- The four lenses are never combined into one hierarchy or used to infer equivalent levels across organizations.
- Physical BWC sites do not change identity when the lens changes.
- Domestic reference views retain meaningful treatment for Alaska, Hawaii, Puerto Rico, the U.S. Virgin Islands, and Guam.
- A lens-specific description identifies the image as illustrative.
- A visible validation label remains **Provisional** until authoritative approval.
- “Boundary digitization: Complete” means only that the visual tracing task is complete. It does not mean the boundary is validated, authoritative, current, or approved.
- Markers must have accessible names and keyboard-operable actions. A legend explains marker symbols in text.
- Map information needed for a decision is repeated in surrounding text, task lists, tables, or provenance; the image is never the sole evidence.

### Prohibited interpretations

Do not use visual proximity, overlap, fill color, label placement, a generated asset, or a normalized name to establish:

- Official jurisdiction or area of responsibility.
- Command ownership or reporting hierarchy.
- A physical Site ID.
- An immutable Axon Device Home ID.
- Approval of a Device Home-to-site or Group-to-site mapping.
- Tenant configuration or current operational coverage.

Those decisions require authoritative source validation and the governed crosswalk.

## Chart accessibility

Canvas content is not independently accessible. When the trend chart is drawn on a canvas:

- Mark the canvas itself as hidden from assistive technology.
- Place a concise chart summary in an associated figure caption.
- Include the same month/value series in an accessible table.
- Keep values available in text so interpretation does not depend on line shape or color.
- If the chart changes to live data, update the summary and table from the same data array used to draw the canvas.

Disposition bars use native progress elements with accessible labels and adjacent visible values.

## Exports and print

**Reports > Preview PDF report** composes the stated scope, metrics, selected map lens, priority review, calculation, and provenance into one print view. On macOS choose **PDF > Save as PDF**; on Windows 11 choose **Microsoft Print to PDF**. Review the print preview before saving.

Microsoft Print to PDF output is a convenient visual brief, not a guarantee of tagged or otherwise fully accessible PDF structure. Keep CSV available for structured data and preserve visible provenance and illustrative/provisional labels in print.

## Review checklist for visual changes

- The Segoe UI stack and canonical tokens remain intact.
- State is communicated by text/icon/structure, not color alone.
- Focus is visible and interactive targets are adequately sized and separated.
- Current-page, expanded, dialog, progress, alert, and live-status semantics remain accurate.
- Each organizational selection changes to the correct independent lens and does not change Site identity.
- Each map has lens-specific alternative text, legend, source/reference context, and provisional validation language.
- The canvas chart has a synchronized text/table equivalent.
- Illustrative and live content remain unmistakably labeled on screen and in print.
- CSV and Microsoft Print to PDF paths remain available.
- No accessibility or authoritative-boundary claim is added without evidence.
