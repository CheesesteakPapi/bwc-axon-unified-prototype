# Operator-centered UI/UX review

Reviewed baseline: main at d497dcc. Research branch: feature/ui-ux-enhancements.

## Outcome

The current interface exposes too much of the underlying data model. Nontechnical operators must interpret crosswalk terminology, choose among numerous administrative tables, and distinguish workflow state from screen navigation. Cosmetic restyling alone would not solve this.

The audience is primarily nontechnical operators. Provisioning Administrators need deeper configuration; Support needs provenance and diagnostics. These should be discoverable secondary views, not competing primary tasks. Navigation visibility is not an authorization control.

## Evidence and priority

| Priority | Finding | Evidence | Design response |
|---|---|---|---|
| High | Unsaved edits can be mistaken for approved values | Synthetic Preview test: changed Role, approval remained enabled | Require save/revalidation or explicit discard before approval |
| High | Submit claims approval prematurely | Opened Submit through step navigation before approval; approval notice still appeared | Derive notice and next action from approval/chunk state |
| High | Saved-data labels conflict | Saved snapshot header combined FULL BASELINE with synthetic-data fallback text | Separate snapshot freshness, source mode, and session connection |
| Medium | Highlighted step differs from displayed page | Submit heading appeared while Preview remained highlighted | Indicate current page and workflow milestones separately |
| Medium | Bulk-paste promise exceeds grid behavior | Intake has no multi-cell paste handler | Parse pasted rows and offer reviewed Role selections |
| Medium | Crosswalk navigation exposes 13 tabs | Browser inspection of Crosswalk Workspace | Organize around tasks with contextual descriptions and advanced setup |
| Medium | Reports misses saved-export capabilities | Reports requested a new pull while Inventory/Assignments could export saved snapshots | Reuse local snapshot export entry points |
| Medium | Preview is too wide and dense | At 640px, 1670px table inside 556px container | Summary columns plus selected-record detail; retain identity context |
| Medium | Accessibility inconsistency | Required change-reason input lacks explicit label; Provisioning has no skip link | Persistent labels, skip navigation, reliable focus and error summaries |

Submission still checks approval on the backend. These findings do not demonstrate an authorization bypass. No tenant writes were tested.

## Strengths to preserve

Optional Location/AOR, job-title mappings, and Group assignments do not block user import. Email and UPN remain distinct. Each user has one Axon Role and may have multiple devices. Axon Groups are not Entra memberships or evidence groups. Device geography does not determine personnel organization. Saved snapshots and pending changes remain separate, and final submission stays deliberate.

## Review limits

Source and synthetic browser review covered both applications and focused responsive/focus checks. It was not a formal accessibility certification, representative-user study, Windows acceptance, or live connector validation.
