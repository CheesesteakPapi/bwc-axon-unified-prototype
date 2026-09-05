# V3.2.0 implementation specification

Direction: Task Home plus guided operator tasks, continuing the three reviewed concepts. White canvas, navy text, blue actions, fine gray separators; no decorative gradients or new dependency framework.

Concept references are the local 03-task-home and 01-guided-tasks images in the dated UI research output, intentionally outside the publishable repository.

Tokens: background #ffffff; text #071b38; secondary #52657a; accent #0057b8; separator #ccd6df. Segoe UI/system fonts. Body 16px, controls 15px, task titles 23px, main titles 36px. Spacing 8/16/24/32/48px. Buttons 44px minimum height with 4px corners and visible focus.

Primary component families: horizontal task navigation, open task rows, contextual continuation rail, guided steps, searchable record list with selected-person detail, labeled assignment controls, revision-bound approval summary and collapsible administrative setup.

Functional adaptations to concepts: the two independently authenticated Python apps remain separate. Geographic People opens saved users/assignments; account creation uses the existing Provisioning launcher, explained in Help, not an invented cross-process link. No leadership-only privacy promise is made for existing operational exports. Saved data and continuation content use actual state, never concept example metrics.

Provisioning: protect unsaved edits before navigation/approval/submission/export; use actual displayed step; concise selected-user editor with pagination; Excel/CSV clipboard parsing; explicit no-approval and already-submitted states; retain backend authority.

Geographic: Task Home becomes default; preserve all existing pages under primary or secondary navigation; replace 13 competing mapping tabs with grouped task selection and descriptions. Personnel mapping remains optional. Existing governed workbench is retained for detailed editing.

Verification: synthetic state only; automated unit/backend/build checks, browser interaction and responsive checks, and direct image comparison. No tenant writes. No signing or Windows acceptance claim.
