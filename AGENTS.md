# Companies House Public Data API guide

This file is the durable project reference for agents working with the Companies
House Public Data API. Read it before browsing the API documentation again.

It was checked on 2026-07-26 against the official reference, its top-level
Swagger 2.0 document, all 15 component specifications referenced by that
document, the official authentication and developer-guidelines pages, and a
read-only live response from the company-officers endpoint.

## Project safety rules

- Never print, log, commit, or return an API key.
- Prefer `COMPANIES_HOUSE_API_KEY`. The local `credentials.toml` is a fallback
  only and must remain private.
- Treat a company number as an opaque string. Preserve leading zeroes and
  jurisdiction prefixes such as `SC`, `NI`, `OC`, and `SO`.
- Use HTTPS only.
- The Public Data API is read-only. The canonical origin is
  `https://api.company-information.service.gov.uk`.
- Use links returned by the API instead of reconstructing paths where practical.
  Returned links are normally relative paths on the canonical origin.
- IDs are opaque strings. Do not case-fold, trim, hash, or otherwise transform
  them.
- Parse additively: ignore unknown response members and tolerate missing optional
  members. A 2026-07-26 live officer-list response included `inactive_count`,
  which is not in the current published `officerList` resource schema.
- Do not infer an item-level active/inactive status merely from the absence of
  `resigned_on`. See the status limitation and aggregate-count fallback below.

## REST and authentication model

All 34 operations in the top-level Public Data API specification are `GET`
operations returning JSON.

Send the API key as the HTTP Basic username with an empty password:

```http
GET /company/00000006/officers HTTP/1.1
Host: api.company-information.service.gov.uk
Accept: application/json
Authorization: Basic base64("<API_KEY>:")
```

Equivalent curl syntax:

```bash
curl --fail --silent --show-error \
  --user "${COMPANIES_HOUSE_API_KEY}:" \
  --header "Accept: application/json" \
  "https://api.company-information.service.gov.uk/company/00000006/officers"
```

The generated Swagger file describes a header named `api_key` and lists HTTP as
a scheme, but the official authentication page specifies HTTP Basic. In this
project use HTTPS plus HTTP Basic.

The default published rate limit is 600 requests per five-minute period. A
client that receives `429 Too Many Requests` should stop and retry with bounded
backoff after the limit window. Retry transient network errors and `5xx`
responses conservatively because `GET` is idempotent. Do not automatically
retry malformed requests (`400`), invalid credentials (`401`), or missing
resources (`404`).

Common response conventions:

- Dates are ISO calendar dates: `YYYY-MM-DD`.
- List resources normally contain `items`, `items_per_page`, `start_index`, and
  `total_results`.
- Pagination is zero-based offset pagination. Keep requesting with
  `start_index = previous start_index + len(previous items)` until the next
  index is at least `total_results`. Stop defensively if a non-final page has no
  items.
- Use the returned page length and metadata, not an assumed server maximum.
- Many detail and list resources return an `ETag` header or `etag` member.
- Enumerated values are stable machine values. Store the raw value; map it to a
  display label separately.
- A structured validation/service error may contain
  `errors[].{error,error_values,location,location_type,type}`. Error type is
  `ch:validation` or `ch:service`; location type is `json-path` or
  `query-parameter`.

## Canonical public endpoint index

The top-level Swagger `paths` object is authoritative for the public surface.
Some component files also contain transaction/filing operations that are not
linked from this Public Data API reference; do not infer that those operations
belong to this API.

### Company and address

- `GET /company/{companyNumber}` — company profile. This is the main link hub
  and includes identity, type/status, dates, addresses, accounts, confirmation
  statement, SIC codes, previous names, and links to related resources.
- `GET /company/{companyNumber}/registered-office-address` — current registered
  office address.

Both require only the company-number path value.

### Search

- `GET /search` — combined search. Required query: `q`. Optional:
  `items_per_page`, `start_index`.
- `GET /search/companies` — company search. Required: `q`. Optional:
  `items_per_page`, `start_index`, `restrictions`.
- `GET /search/officers` — officer search. Required: `q`. Optional:
  `items_per_page`, `start_index`.
- `GET /search/disqualified-officers` — disqualified-officer search. Required:
  `q`. Optional: `items_per_page`, `start_index`.
- `GET /advanced-search/companies` — advanced company search. Optional filters:
  `company_name_includes`, `company_name_excludes`, `company_status`,
  `company_subtype`, `company_type`, `dissolved_from`, `dissolved_to`,
  `incorporated_from`, `incorporated_to`, `location`, `sic_codes`, `size`,
  `start_index`.
- `GET /alphabetical-search/companies` — alphabetical company search. Required:
  `q`. Optional: `search_above`, `search_below`, `size`.
- `GET /dissolved-search/companies` — dissolved company search. Required: `q`,
  `search_type`. Optional: `search_above`, `search_below`, `size`,
  `start_index`.

Search responses are discovery records, not substitutes for authoritative detail
resources. Follow their links or company numbers to the appropriate detail
endpoint.

### Officers and officer appointments

- `GET /company/{company_number}/officers` — all officer appointment records for
  one company. Optional: `items_per_page`, `start_index`, `order_by`,
  `register_view`, `register_type`.
- `GET /company/{company_number}/appointments/{appointment_id}` — one company
  officer appointment.
- `GET /officers/{officer_id}/appointments` — all appointments grouped under one
  Companies House officer ID. Optional: `filter=active`, `items_per_page`,
  `start_index`.

Officer-list `order_by` values are `appointed_on`, `resigned_on`, and `surname`.
When `register_view=true`, `register_type` can be `directors`, `secretaries`, or
`llp_members`. Do not use register view for a complete history because, when the
relevant register is held at Companies House, it returns only active officers.

### Registers

- `GET /company/{company_number}/registers` — company-register metadata, such as
  where relevant registers are held and links to their resources.

### Charges

- `GET /company/{company_number}/charges` — charge list. Optional:
  `items_per_page`, `start_index`.
- `GET /company/{company_number}/charges/{charge_id}` — one charge.

### Filing history

- `GET /company/{company_number}/filing-history` — filing list. Optional:
  `category`, `items_per_page`, `start_index`.
- `GET /company/{company_number}/filing-history/{transaction_id}` — one filing
  history item.

### Insolvency and exemptions

- `GET /company/{company_number}/insolvency` — insolvency cases and associated
  dates/practitioners.
- `GET /company/{company_number}/exemptions` — company exemption information.

### Officer disqualifications

- `GET /disqualified-officers/natural/{officer_id}` — natural-person
  disqualification details.
- `GET /disqualified-officers/corporate/{officer_id}` — corporate-officer
  disqualification details.

Disqualified-officer IDs are from the disqualified-officer search resource. Do
not assume they equal IDs from ordinary officer appointment links.

### UK establishments

- `GET /company/{company_number}/uk-establishments` — UK establishments
  associated with a company.

### Persons with significant control (PSC)

- `GET /company/{company_number}/persons-with-significant-control` — PSC list.
  The component spec lists `items_per_page`, `start_index`, and `register_view`
  as query parameters.
- `GET /company/{company_number}/persons-with-significant-control/individual/{notification_id}`
- `GET /company/{company_number}/persons-with-significant-control/individual-beneficial-owner/{notification_id}`
- `GET /company/{company_number}/persons-with-significant-control/corporate-entity/{notification_id}`
- `GET /company/{company_number}/persons-with-significant-control/corporate-entity-beneficial-owner/{notification_id}`
- `GET /company/{company_number}/persons-with-significant-control/legal-person/{notification_id}`
- `GET /company/{company_number}/persons-with-significant-control/legal-person-beneficial-owner/{notification_id}`
- `GET /company/{company_number}/persons-with-significant-control/super-secure/{super_secure_id}`
- `GET /company/{company_number}/persons-with-significant-control/super-secure-beneficial-owner/{super_secure_id}`
- `GET /company/{company_number}/persons-with-significant-control-statements` —
  statement list. The component spec lists `items_per_page`, `start_index`, and
  `register_view`.
- `GET /company/{company_number}/persons-with-significant-control-statements/{statement_id}`
- `GET /company/{company_number}/persons-with-significant-control/{psc_id}/notifications`
  — notifications for a PSC. Optional: `filter=active`, `items_per_page`,
  `start_index`.

PSC records are polymorphic. Use `kind` and the resource URL to select the
correct detail shape. PSC fields commonly include name/name elements, address,
notification/cessation dates, nature-of-control enums, identification,
nationality/residence, links, and identity-verification details. Super-secure
records intentionally expose a restricted shape.

## Required company-officers tool contract

### Goal and unit of data

Input: one company number.

Output: every officer appointment for that company, including:

- officer name;
- Companies House IDs;
- the appointment's active-from date or bound;
- officer role;
- appointment status, including an explicit `unknown` when the API cannot
  support a more precise item-level value;
- resignation date when resigned.

The endpoint returns appointments, not a clean, deduplicated set of real-world
people. One person can hold multiple roles and therefore have multiple records.
Use one output row per appointment. If a consumer needs people grouped together,
group by `officer_id` and keep a nested appointment array; never deduplicate by
name.

### Request

```http
GET https://api.company-information.service.gov.uk/company/{company_number}/officers?items_per_page={n}&start_index={offset}
```

Do not set `register_view=true`, because the required result includes resigned
appointments. Fetch every page.

Path-encode the company number as one segment. Validation should reject an empty
value and obvious whitespace/control characters but should not coerce the number
to an integer.

### Source fields and normalization

For every `items[]` member:

| Required output | API source | Rule |
| --- | --- | --- |
| `name` | `name` | Required by the schema. Preserve the returned spelling and ordering. |
| `officer_id` | `links.officer.appointments` | Extract the opaque segment from `/officers/{officer_id}/appointments`; also retain/follow the link itself when useful. |
| `appointment_id` | `links.self` | Extract the opaque segment from `/company/{company_number}/appointments/{appointment_id}`. |
| `person_number` | `person_number` | Optional unique person identifier used by specified Companies House bulk products; return `null` when absent. |
| `active_from` | `appointed_on` | Exact ISO date when present. |
| `active_from` fallback | `appointed_before` | Only for pre-1992 appointments. Represent this as a bound (`before`) rather than inventing an exact date. |
| `role` | `officer_role` | Preserve the raw enum. |
| `resigned_on` | `resigned_on` | Optional ISO date; otherwise `null`. |
| `status` | `resigned_on` plus list counts | `resigned` is exact when `resigned_on` is present. For other records, apply the aggregate-count rule below; do not blindly call them active. |

The company-officer resource does not publish an item-level `status` field.
`active_count` and `resigned_count` are documented list totals. Live responses
also contain the undocumented list total `inactive_count`. A dissolved or
otherwise inactive company can therefore have unresigned appointments counted
as inactive. Company status and appointment status are related context but are
not interchangeable; dissolution does not mean an officer resigned.

Status normalization must happen after all pages are fetched:

1. Any item with `resigned_on` is `resigned`; this is exact.
2. Let `unresigned` be all items without `resigned_on`.
3. If `active_count == len(unresigned)` and `inactive_count` is absent or zero,
   label every unresigned item `active`.
4. If `inactive_count == len(unresigned)` and `active_count == 0`, label every
   unresigned item `inactive`.
5. Otherwise label unresigned items `unknown`. Aggregate counts cannot identify
   which individual item belongs to which bucket if both buckets are populated,
   counts are inconsistent, or some results are missing.

Expose `status_source` as `resigned_on`, `aggregate_counts`, or `unavailable` if
the consumer needs the provenance. Never convert `unknown` to `active` merely
for a two-value output contract.

For `corporate-managing-officer` and `managing-officer`, the API documents
`appointed_on` as the date Companies House was notified about the officer and
`resigned_on` as the date Companies House was notified of cessation. Preserve
those fields but do not relabel them as the underlying real-world event dates.

Recommended normalized shape:

```json
{
  "company_id": "00000006",
  "officers": [
    {
      "name": "EXAMPLE, Alex",
      "officer_id": "opaque-officer-id",
      "appointment_id": "opaque-appointment-id",
      "person_number": "optional-person-number-or-null",
      "active_from": "2020-01-31",
      "active_from_precision": "exact",
      "role": "director",
      "status": "resigned",
      "status_source": "resigned_on",
      "resigned_on": "2024-06-30"
    }
  ]
}
```

Allowed `active_from_precision` values:

- `exact` when `appointed_on` exists;
- `before` when only `appointed_before` exists;
- `unknown` when neither exists.

For `before`, put the returned `appointed_before` value in `active_from`. Dates
and both ID link objects are optional in real data even where a published schema
marks links as required. Return `null` plus a structured warning for a malformed
record instead of dropping the officer.

### Officer role values

The published company-officer resource currently lists:

- `cic-manager`
- `corporate-director`
- `corporate-llp-designated-member`
- `corporate-llp-member`
- `corporate-manager-of-an-eeig`
- `corporate-managing-officer`
- `corporate-member-of-a-management-organ`
- `corporate-member-of-a-supervisory-organ`
- `corporate-member-of-an-administrative-organ`
- `corporate-nominee-director`
- `corporate-nominee-secretary`
- `corporate-secretary`
- `director`
- `general-partner-in-a-limited-partnership`
- `judicial-factor`
- `limited-partner-in-a-limited-partnership`
- `llp-designated-member`
- `llp-member`
- `manager-of-an-eeig`
- `managing-officer`
- `member-of-a-management-organ`
- `member-of-a-supervisory-organ`
- `member-of-an-administrative-organ`
- `nominee-director`
- `nominee-secretary`
- `person-authorised-to-accept`
- `person-authorised-to-represent`
- `person-authorised-to-represent-and-accept`
- `receiver-and-manager`
- `secretary`

Do not fail on a future unknown role. Pass it through as an opaque enum.

### ID semantics and limits

Expose all three IDs when available because they identify different things:

- `appointment_id` identifies one appointment resource for one company.
- `officer_id` identifies the Companies House officer-appointment grouping
  addressed by `/officers/{officer_id}/appointments`.
- `person_number` is an optional person identifier shared with specified bulk
  products.

Do not claim that `officer_id` proves a globally unique natural person. Companies
House data can split the same real-world person across multiple officer IDs, and
names are not identifiers. Conversely, do not merge IDs merely because names or
birth month/year match.

Prefer following the link supplied in `links.officer.appointments`. If an ID is
needed separately, parse the URL path structurally and require the exact
`/officers/{id}/appointments` shape. Likewise parse `links.self` structurally for
the appointment ID. Do not parse IDs by fixed length or character set.

### Optional enrichment

No enrichment request is needed to satisfy the required tool. The company
officers list already provides the requested fields.

Use these only for explicit additional requirements:

- `GET links.officer.appointments` to list that officer ID's appointments at
  other companies. Its list-level `name`, `date_of_birth`, and
  `is_corporate_officer` describe the grouping; each item contains
  `appointed_to`, role, dates, and company link.
- `GET links.self` to retrieve the individual appointment resource.

Following the officer-appointments link does not produce a missing
`appointment_id` for each item: its item links point to the company, whereas the
company-officers resource supplies the appointment self link. Capture both IDs
from the company-officers response before any enrichment.

### Pagination algorithm

```text
offset = 0
records = []
repeat:
    GET /company/{company_number}/officers
        ?items_per_page={configured_page_size}
        &start_index={offset}
    require a JSON object and an items array
    append normalized items
    next_offset = response.start_index + len(response.items)
    stop if next_offset >= response.total_results
    fail defensively if len(response.items) == 0 or next_offset <= offset
    offset = next_offset
```

Counts such as `active_count`, `resigned_count`, and the additive
`inactive_count` are metadata, not pagination termination conditions. Retain
them for the post-pagination status rule.

### Acceptance checks

An implementation is complete only when it:

1. Preserves the company number as a string.
2. Uses HTTPS and API-key Basic authentication without logging the key.
3. Retrieves every page with ordinary list view.
4. Returns one record per appointment.
5. Returns `name`, raw `officer_role`, status with provenance, and nullable
   `resigned_on`; it never treats every unresigned record as automatically
   active.
6. Handles `appointed_on`, pre-1992 `appointed_before`, and missing dates.
7. Extracts both `officer_id` and `appointment_id` from their respective links
   and includes optional `person_number`.
8. Does not merge officers by name or claim that an officer ID proves real-world
   identity.
9. Tolerates unknown fields and enum values.
10. Handles `400`, `401`, `404`, `429`, network failures, and `5xx` without
    leaking credentials.

## Documentation sources

- Public Data API reference:
  https://developer-specs.company-information.service.gov.uk/companies-house-public-data-api/reference
- Top-level Swagger 2.0 document:
  https://developer-specs.company-information.service.gov.uk/api.ch.gov.uk-specifications/swagger-2.0/spec/swagger.json
- Company officers endpoint:
  https://developer-specs.company-information.service.gov.uk/companies-house-public-data-api/reference/officers/list
- Company officer list resource:
  https://developer-specs.company-information.service.gov.uk/companies-house-public-data-api/resources/officerlist?v=latest
- Individual company officer appointment:
  https://developer-specs.company-information.service.gov.uk/companies-house-public-data-api/reference/officers/get-a-company-officer-appointment
- Officer appointments endpoint:
  https://developer-specs.company-information.service.gov.uk/companies-house-public-data-api/reference/officer-appointments/list
- Officer appointment list resource:
  https://developer-specs.company-information.service.gov.uk/companies-house-public-data-api/resources/appointmentlist?v=latest
- Authentication:
  https://developer.company-information.service.gov.uk/authentication
- Developer guidelines and rate limit:
  https://developer.company-information.service.gov.uk/developer-guidelines/
- Enumeration mappings:
  https://github.com/companieshouse/api-enumerations

Browse again only when implementing a resource not summarized adequately here,
when a live response contradicts this guide, or when freshness matters because
the API specification has changed since the verification date.
