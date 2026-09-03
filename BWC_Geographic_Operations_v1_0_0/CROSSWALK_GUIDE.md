# Crosswalk and Governance Table Guide

Seven local CSVs are editable in the app. `device_status_map.csv` remains file-only until exact tenant `status2` values are observed. These files support reviewed relationships among Office Locations, physical Facilities, Device Homes, Axon Groups, command hierarchy, users, and reporting states.

## Core rules

- Preserve every existing Site ID value; the new facility model relabels it **Office Location ID**.
- Never infer an Axon Group ID, External Group ID, Device Home ID, Parent Group ID, or tenant membership.
- Use Axon Groups and reviewed command hierarchy for organizational mapping. Do not infer a site from a User record.
- Keep Group tiers and site relationships separate. A Group can span offices or have no site relationship.
- Record network environment at Office Presence level, not as a property of the whole facility.
- Keep `Region / AOR` to the AOR name only. Office-type prefixes belong in Office Name.
- Confidence rates evidence strength; it is not approval.
- Preserve exact observed source values and document normalization or exceptions in review fields.
- In-app saves reject values beginning with `=`, `+`, `-`, or `@` after trimming.

## Common decision fields

### Mapping Method

| Value family | Use |
|---|---|
| `Not assessed` | No comparison performed. |
| `Observed ID` | A directly observed Axon identifier supports the record. |
| `Exact name` | Exact source name plus governing context agree. |
| `Normalized name` | A reviewed normalized key compares name variants. |
| `Command hierarchy review` | A reviewed command relationship supports the decision. |
| `Authoritative facility source` | An approved facility record establishes the physical location. |
| `Geocoded address` | Address and coordinates were reviewed. |
| `Manual exception` | An authorized exception is required and documented. |

The interface limits each table to its applicable values.

### Confidence

| Value | Meaning |
|---|---|
| `Not rated` | Evidence not assessed. |
| `Low` | Incomplete or ambiguous. |
| `Medium` | Several fields align but confirmation remains. |
| `High` | Directly observed identifiers and governing context agree; approval is still separate. |

### Review Notes

Use one short factual statement:

`<basis>; <ambiguity or exception>; <next review>.`

Do not place credentials, tokens, sensitive personal data, or unsupported conclusions in notes.

## Backward-compatible tables

### Device Home crosswalk

One row per existing Office Location. Office/geography fields are locked. Enter the exact observed Device Home name, reviewed normalized key, status, method, confidence, and notes. A `Mapped` row requires the observed name, normalized key, reviewed method, rated confidence, and notes.

### Legacy Axon Group crosswalk

One row per existing Office Location for compatibility. Office/geography fields are locked. Enter exact observed Group identifiers/name and review fields. Use the Tiered Group Master plus relationship table when the relationship is not one-to-one.

### Non-site Group register

Use for Groups that are not defensibly tied one-to-one to an Office Location. Controlled classifications are `Command`, `Role-related`, `Training`, `Enterprise`, `Administrative`, and `Other non-site`. `Registered non-site` requires an exact Group ID/name, classification, command level, reporting treatment, and notes.

## Facility Master

`facility_master_starter.csv` begins header-only so no physical location is invented.

| Field | Review rule |
|---|---|
| Facility ID | Required and unique locally governed physical-location key. |
| Facility Name | Required reviewed name. |
| Address / City / State | Physical location evidence; do not derive from office label alone. |
| Latitude / Longitude | Supply as a valid pair only. |
| Shared Facility | Pending review, No, Yes - ICE components, Yes - external organization, or Yes - mixed. |
| Host Organization | Required when occupancy is Externally hosted. |
| Ownership / Occupancy Type | Pending review, ICE-owned, ICE-leased, GSA-controlled, Hosted by another federal agency, State / local government facility, Commercial / shared facility, or Other. |
| Geocoding Status | Not geocoded, Candidate, Validated, or Withheld. |
| Validation Status | Draft, Needs review, Validated, or Inactive. |
| Mapping Method / Confidence / Review Notes | Required evidence for Validated. |

## Office Presence register

`office_presence_starter.csv` contains 481 preserved Office Location IDs. Locked fields are Office Location ID, Component, Region / AOR, Office Name, City, State, and Site Code / DCO.

| Editable field | Review rule |
|---|---|
| Facility ID | Must already exist in Facility Master when populated. |
| Presence Type | Pending classification, Primary office, Satellite office, Shared operational presence, Temporary presence, or Other. |
| Network Environment | Unknown / pending validation, ICE-managed network, Host-agency network, Mixed network environment, Limited ICE connectivity, or No operational network. |
| Network Scope | Unknown / pending validation, Facility-wide, Office / suite, Shared service, Limited / intermittent, or Not applicable. |
| Operational Status | Needs validation, Planned, Active, Inactive, or Temporary. |
| Facility Link Status | Unlinked, Candidate, Needs review, or Linked. |
| Mapping Method / Confidence / Review Notes | `Linked` requires a reviewed method, rated confidence, and notes. |

Multiple Office Locations may reference the same Facility ID.

## Tiered Group Master

`axon_group_master_starter.csv` begins header-only. Create a row only for an exact observed Group ID and Group Name.

| Field | Purpose |
|---|---|
| Group Purpose | User assignment, Organizational area, Command, Training, Enterprise, Administrative, or Other. |
| Group Tier | Primary, Secondary, Organizational area, Additional, or Not applicable. |
| Parent Group ID | Existing local Group ID; cannot reference itself. |
| Command Hierarchy Level | Enterprise, Component, Region / AOR, Field office, Suboffice, Function, or Not applicable. |
| Organizational Lens | One of the four separate lenses, Cross-component, or Not applicable. |
| Site Relationship | Pending review, Office presence, Facility-wide, Site-linked, or Non-site. |
| Mapping Status | Unclassified, Needs review, or Classified. |

`Classified` requires purpose, tier, command level, site relationship, rated confidence, and notes.

## Site-to-Group relationships

`site_group_relationship_starter.csv` begins header-only and supports many-to-many relationships.

- Office Location ID and Axon Group ID are required and must already exist locally.
- Facility ID is optional but must exist when populated.
- Office Location ID + Axon Group ID + Relationship Type must be unique.
- `Mapped` requires reviewed method, rated confidence, and notes.

Use this table rather than duplicating or overwriting master rows when one Group serves multiple offices or one office has multiple Groups.

## User role and membership interpretation

Only one role/profile value belongs in the user role field. Multiple access scopes belong in Group memberships. Users may have more than one Group and more than one device.

The current live Users pull does not expose the tiered membership fields used by the illustrative view. Blank live membership fields and `Not observed` are deliberate; do not infer them.

## Device status map

Add only exact observed `status2` values to `device_status_map.csv` through the governed file-review process. Map each raw value separately to Assigned, Unassigned, In Stock, Lost, Relinquished, Other, or Unmapped. Do not derive a raw state from owner presence or assignment.

## Review sequence

1. Refresh approved read-only source extracts.
2. Verify preserved Office Location IDs and exact observed Axon IDs/names.
3. Create reviewed physical Facility rows before linking Office Presences.
4. Record facility, network, Group tier, parent, and many-to-many relationships separately.
5. Enter mapping method, confidence, and factual decision basis.
6. Route ambiguous records to Candidate / Needs review rather than forcing a result.
7. Obtain owner approval before final status changes.
8. Re-run unique-key, reference-integrity, required-field, controlled-value, encoding, and prohibited-prefix checks before distribution.
