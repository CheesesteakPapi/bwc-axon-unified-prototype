## Change summary

Describe the user-visible or technical change.

## Required checks

- [ ] I ran `python scripts/check_publish_safety.py`.
- [ ] I did not add credentials, tenant identifiers, operational data, snapshots, workbooks, working crosswalks, maps, screenshots, logs, databases, or exports.
- [ ] I used only synthetic fixtures under `governance_starters/`.
- [ ] I ran the affected Python and UI tests.
- [ ] Axon write behavior remains explicitly operator-confirmed and is never retried automatically after an ambiguous result.
- [ ] Evidence Groups remain unused; `EVIDENCE_GROUP_EXT_ID` is blank compatibility only.
