# Facility, Office Presence, Role, and Group Model — V2.3.5

This package-level guide governs both the shared working CSVs edited by the local UI and the corresponding workbook snapshot sheets.

## Purpose

This release separates physical location, organizational presence, access role, and Axon Group membership. That separation supports co-located components, facilities hosted by another agency, non-ICE-networked offices, tiered Groups, and Groups that have no direct site relationship.

## Core relationships

```text
Facility 1 ----< Office Presence >---- 1 Office Location
                           |
                           `----< Office-to-Group Relationship >---- 1 Axon Group

User 1 ---- 1 Role
User 1 ----< Group memberships (primary, secondary, organizational-area, additional)
User 1 ----< Devices
```

The diagram describes the data model, not tenant facts. Actual IDs and relationships require observed and reviewed evidence.

## Why Facility and Office Location are separate

- A **Facility** is the physical building, campus, or host site.
- An **Office Location** is an ERO, HSI, OCIO, OPR, or other component office.
- An **Office Presence** records that an office operates at a facility and captures its presence type, network environment, operational state, and evidence.

One facility may host several Office Locations. This supports co-location without merging components or organizational lenses. It also allows two offices in one building to have different network or operational conditions.

## Preserved keys

The 481 existing Site IDs are preserved unchanged and relabeled **Office Location ID** in the new table. They remain the stable office keys. The Facility Master starts empty so the prototype does not create physical Facility IDs from office labels, proximity, city matches, or organizational maps.

## Facility review fields

| Field | Purpose |
|---|---|
| Facility ID | Locally governed physical-location key; required and unique. |
| Facility Name / address / coordinates | Reviewed physical identity and geocoding context. |
| Shared Facility | Whether more than one component/organization is confirmed at the facility. |
| Host Organization | ICE, another agency, commercial landlord, or other reviewed host. Required for externally hosted status. |
| Ownership / Occupancy Type | Pending review, ICE-owned, ICE-leased, GSA-controlled, hosted by another federal agency, state/local government facility, commercial/shared facility, or other. |
| Geocoding Status | Not geocoded, Candidate, Validated, or Withheld. |
| Validation Status | Draft, Needs review, Validated, or Inactive. |
| Mapping Method / Confidence / Review Notes | Factual basis, evidence strength, ambiguity, and next review. |

## Office Presence review fields

| Field | Purpose |
|---|---|
| Office Location ID | Preserved office key; locked. |
| Facility ID | Reviewed link to Facility Master. |
| Presence Type | Pending classification, Primary office, Satellite office, Shared operational presence, Temporary presence, or Other. |
| Network Environment | Unknown/pending validation, ICE-managed, host-agency, mixed, limited ICE connectivity, or no operational network. |
| Network Scope | Unknown/pending validation, Facility-wide, Office / suite, Shared service, Limited / intermittent, or Not applicable. |
| Operational Status | Needs validation, Planned, Active, Inactive, or Temporary. |
| Facility Link Status | Unlinked, candidate, needs review, or linked. |
| Mapping Method / Confidence / Review Notes | Evidence and decision basis. |

A `Linked` row requires an existing Facility ID plus reviewed mapping method, confidence, and notes.

## User roles and Group tiers

Each user has one role/profile field. Missing or multi-value role text is an exception. Multiple permissions or organizational associations belong in Group memberships rather than a second role value.

Group tiers are:

- **Primary:** the user's main operating Group.
- **Secondary:** a secondary operating or functional Group.
- **Organizational area:** component region, AOR, field office, or other governed organizational area.
- **Additional:** other approved membership such as training, function, or special program.
- **Not applicable:** the Group is not a user-membership tier.

## Tiered Group Master

The master records exact observed Group IDs and names before classification. It can then record purpose, tier, Parent Group ID, command hierarchy level, organizational lens, component, area, site relationship, active status, mapping status, confidence, and review notes.

Parent Group ID must already exist in the local master, cannot point to the same Group, and does not itself prove an Axon tenant hierarchy. A `Classified` Group requires a reviewed purpose, tier, command level, site relationship, confidence, and notes.

## Many-to-many site relationships

Use `site_group_relationship_starter.csv` when:

- one Group applies to several Office Locations;
- one Office Location has several Groups;
- a Group is facility-wide rather than component-office-specific;
- the same Group has different relationships across locations; or
- the relationship needs an explicit method, confidence, status, and review note.

The combination of Office Location ID, Axon Group ID, and Relationship Type must be unique. Referenced Office Location, Facility, and Group IDs must exist in their respective local tables.

## Groups with no direct site relationship

Do not force a site assignment. Use the Non-site Group register or set the Tiered Group Master's Site Relationship to `Non-site`. Classifications include Command, Role-related, Training, Enterprise, Administrative, and Other non-site.

## Current live-data limitation

The current Users pull supplies one role/profile field and device ownership context, but the tiered membership fields shown in the illustrative access view are not observed in the current live contract. Live primary, secondary, organizational-area, and additional membership fields therefore remain blank and are labeled **Not observed**. A later implementation may populate them only from an approved observed source.

## Approval boundary

`Validated`, `Linked`, `Classified`, and `Mapped` mean the required evidence fields have been completed in the local workflow. They do not replace agency approval, tenant administration, records governance, security review, or an authoritative facilities/geospatial source.
