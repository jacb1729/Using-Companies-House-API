"""Fetch an officer's company appointments and store them in SQLite."""

from __future__ import annotations

import argparse
import sqlite3
import urllib.parse
from typing import Any

from search_officers_by_company_number import (
    DATABASE_PATH,
    PAGE_SIZE,
    TABLE_NAME,
    CompaniesHouseError,
    ResponseShapeError,
    _api_get_json,
    _ensure_table,
    _load_api_configuration,
    search_officers_by_company_number,
)


def _validate_officer_id(officer_id: str) -> str:
    """Validate an opaque Companies House officer ID as one URL segment."""
    if not isinstance(officer_id, str):
        raise TypeError("officer_id must be a string")
    if not officer_id:
        raise ValueError("officer_id must not be empty")
    if officer_id != officer_id.strip():
        raise ValueError("officer_id must not contain surrounding whitespace")
    if any(character.isspace() or ord(character) < 32 for character in officer_id):
        raise ValueError("officer_id must not contain whitespace or control characters")
    if "/" in officer_id:
        raise ValueError("officer_id must be one URL path segment")
    return officer_id


def _company_number_from_appointment(appointment: dict[str, Any]) -> str:
    """Get the company number, falling back to the company resource link."""
    appointed_to = appointment.get("appointed_to")
    if isinstance(appointed_to, dict):
        company_number = appointed_to.get("company_number")
        if isinstance(company_number, str) and company_number:
            return company_number

    links = appointment.get("links")
    company_link = links.get("company") if isinstance(links, dict) else None
    if isinstance(company_link, str):
        path_parts = urllib.parse.urlsplit(company_link).path.split("/")
        if (
            len(path_parts) == 3
            and path_parts[0] == ""
            and path_parts[1] == "company"
            and path_parts[2]
        ):
            return path_parts[2]

    raise ResponseShapeError(
        "An officer appointment has no usable company number or company link."
    )


def _appointment_date(appointment: dict[str, Any]) -> str | None:
    """Return an exact appointment date or an explicit pre-1992 bound."""
    appointed_on = appointment.get("appointed_on")
    if isinstance(appointed_on, str):
        return appointed_on
    appointed_before = appointment.get("appointed_before")
    if isinstance(appointed_before, str):
        return f"before {appointed_before}"
    return None


def _appointment_rank(appointment: dict[str, Any]) -> tuple[int, str]:
    """Prefer a current appointment, then the most recently appointed one."""
    resigned_on = appointment.get("officer_resigned_on")
    is_unresigned = not isinstance(resigned_on, str)
    appointed_on = appointment.get("officer_appointed_on")
    sortable_date = appointed_on if isinstance(appointed_on, str) else ""
    return int(is_unresigned), sortable_date


def _merge_company_appointment(
    companies: dict[str, dict[str, Any]],
    appointment: dict[str, Any],
) -> None:
    """Keep one deterministic row per officer/company database key."""
    company_number = appointment["company_number"]
    existing = companies.get(company_number)
    if existing is None or _appointment_rank(appointment) > _appointment_rank(
        existing
    ):
        companies[company_number] = appointment


def _enrich_unresigned_appointment(
    company_number: str,
    officer_id: str,
    role: str,
    appointed_on: str | None,
) -> tuple[str, str, str]:
    """Return authoritative company fields and the matching appointment status."""
    company_payload = search_officers_by_company_number(company_number)
    matching_officers = [
        officer
        for officer in company_payload["officers"]
        if officer.get("officer_id") == officer_id
        and officer.get("officer_resigned_on") is None
    ]

    if not matching_officers:
        officer_status = "unknown"
    else:
        exact_matches = [
            officer
            for officer in matching_officers
            if officer.get("officer_role") == role
            and officer.get("officer_appointed_on") == appointed_on
        ]
        selected = exact_matches[0] if exact_matches else matching_officers[0]
        officer_status = selected.get("officer_status", "unknown")
        if not isinstance(officer_status, str) or not officer_status:
            officer_status = "unknown"

    return (
        company_payload["company_name"],
        company_payload["company_status"],
        officer_status,
    )


def _company_profile(
    origin: str,
    api_key: str,
    company_number: str,
) -> tuple[str, str]:
    """Fetch company name and status when an appointment omits them."""
    encoded_company_number = urllib.parse.quote(company_number, safe="")
    profile = _api_get_json(
        origin,
        api_key,
        f"/company/{encoded_company_number}",
    )
    company_name = profile.get("company_name")
    company_status = profile.get("company_status")
    if not isinstance(company_name, str) or not company_name:
        raise ResponseShapeError("The company profile has no company_name.")
    if not isinstance(company_status, str) or not company_status:
        raise ResponseShapeError("The company profile has no company_status.")
    return company_name, company_status


def search_companies_by_officer_id(officer_id: str) -> dict[str, Any]:
    """Get every company appointment grouped under a Companies House officer ID."""
    officer_id = _validate_officer_id(officer_id)
    api_key, origin = _load_api_configuration()
    encoded_officer_id = urllib.parse.quote(officer_id, safe="")

    raw_appointments: list[dict[str, Any]] = []
    offset = 0
    total_results: int | None = None
    officer_name: str | None = None

    while True:
        page = _api_get_json(
            origin,
            api_key,
            f"/officers/{encoded_officer_id}/appointments",
            {"items_per_page": PAGE_SIZE, "start_index": offset},
        )
        items = page.get("items")
        if not isinstance(items, list) or not all(
            isinstance(item, dict) for item in items
        ):
            raise ResponseShapeError(
                "The officer appointment list has an invalid items array."
            )

        page_total = page.get("total_results")
        page_start = page.get("start_index")
        if not isinstance(page_total, int) or page_total < 0:
            raise ResponseShapeError(
                "The officer appointment list has an invalid total_results."
            )
        if not isinstance(page_start, int) or page_start < 0:
            raise ResponseShapeError(
                "The officer appointment list has an invalid start_index."
            )
        if total_results is None:
            total_results = page_total
            page_name = page.get("name")
            if not isinstance(page_name, str) or not page_name:
                raise ResponseShapeError(
                    "The officer appointment list has no officer name."
                )
            officer_name = page_name
        elif page_total != total_results:
            raise ResponseShapeError(
                "The appointment-list total changed while pages were retrieved."
            )

        raw_appointments.extend(items)
        next_offset = page_start + len(items)
        if next_offset >= page_total:
            break
        if not items or next_offset <= offset:
            raise ResponseShapeError(
                "Officer-appointment pagination stopped making progress."
            )
        offset = next_offset

    if total_results is None or officer_name is None:
        raise ResponseShapeError(
            "Companies House returned no officer-appointment page."
        )
    if len(raw_appointments) != total_results:
        raise ResponseShapeError(
            "Retrieved appointments do not match total_results."
        )

    companies: dict[str, dict[str, Any]] = {}
    profile_cache: dict[str, tuple[str, str]] = {}
    enrichment_cache: dict[
        tuple[str, str, str | None],
        tuple[str, str, str],
    ] = {}

    for raw_appointment in raw_appointments:
        company_number = _company_number_from_appointment(raw_appointment)
        appointed_to = raw_appointment.get("appointed_to")
        company_name = (
            appointed_to.get("company_name")
            if isinstance(appointed_to, dict)
            else None
        )
        company_status = (
            appointed_to.get("company_status")
            if isinstance(appointed_to, dict)
            else None
        )

        name = raw_appointment.get("name")
        if not isinstance(name, str) or not name:
            name = officer_name
        role = raw_appointment.get("officer_role")
        if not isinstance(role, str) or not role:
            raise ResponseShapeError(
                "An officer appointment has no officer_role."
            )
        appointed_on = _appointment_date(raw_appointment)
        resigned_on = raw_appointment.get("resigned_on")
        if not isinstance(resigned_on, str):
            resigned_on = None

        if resigned_on is None:
            enrichment_key = (company_number, role, appointed_on)
            if enrichment_key not in enrichment_cache:
                enrichment_cache[enrichment_key] = (
                    _enrich_unresigned_appointment(
                        company_number,
                        officer_id,
                        role,
                        appointed_on,
                    )
                )
            company_name, company_status, officer_status = enrichment_cache[
                enrichment_key
            ]
        else:
            officer_status = "resigned"
            if (
                not isinstance(company_name, str)
                or not company_name
                or not isinstance(company_status, str)
                or not company_status
            ):
                if company_number not in profile_cache:
                    profile_cache[company_number] = _company_profile(
                        origin,
                        api_key,
                        company_number,
                    )
                company_name, company_status = profile_cache[company_number]

        if not isinstance(company_name, str) or not company_name:
            raise ResponseShapeError(
                "An officer appointment has no usable company name."
            )
        if not isinstance(company_status, str) or not company_status:
            raise ResponseShapeError(
                "An officer appointment has no usable company status."
            )

        _merge_company_appointment(
            companies,
            {
                "company_number": company_number,
                "company_name": company_name,
                "company_status": company_status,
                "officer_id": officer_id,
                "office_name": name,
                "officer_role": role,
                "officer_appointed_on": appointed_on,
                "officer_status": officer_status,
                "officer_resigned_on": resigned_on,
            },
        )

    return {
        "officer_id": officer_id,
        "office_name": officer_name,
        "companies": list(companies.values()),
    }


def store_data_from_search_by_officer_id(
    payload: dict[str, Any],
    conn: sqlite3.Connection,
) -> int:
    """Upsert one row per unique officer/company combination."""
    _ensure_table(conn)

    officer_id = payload.get("officer_id")
    companies = payload.get("companies")
    if not isinstance(officer_id, str) or not officer_id:
        raise ResponseShapeError("The payload has no valid officer_id.")
    if not isinstance(companies, list):
        raise ResponseShapeError("The payload has no companies list.")

    rows = []
    seen_keys: set[tuple[str, str]] = set()
    for company in companies:
        if not isinstance(company, dict):
            raise ResponseShapeError("The payload contains an invalid company.")

        company_number = company.get("company_number")
        company_name = company.get("company_name")
        company_status = company.get("company_status")
        row_officer_id = company.get("officer_id")
        office_name = company.get("office_name")
        officer_role = company.get("officer_role")
        officer_status = company.get("officer_status")
        required_values = (
            company_number,
            company_name,
            company_status,
            row_officer_id,
            office_name,
            officer_role,
            officer_status,
        )
        if not all(
            isinstance(value, str) and value for value in required_values
        ):
            raise ResponseShapeError(
                "A company appointment is missing a required database value."
            )
        if row_officer_id != officer_id:
            raise ResponseShapeError(
                "A company appointment contains a different officer_id."
            )

        key = (company_number, row_officer_id)
        if key in seen_keys:
            raise ResponseShapeError(
                "The payload contains a duplicate company/officer key."
            )
        seen_keys.add(key)
        rows.append(
            (
                company_number,
                company_name,
                company_status,
                row_officer_id,
                office_name,
                officer_role,
                company.get("officer_appointed_on"),
                officer_status,
                company.get("officer_resigned_on"),
            )
        )

    conn.executemany(
        f"""
        INSERT INTO {TABLE_NAME} (
            company_number,
            company_name,
            company_status,
            officer_id,
            office_name,
            officer_role,
            officer_appointed_on,
            officer_status,
            officer_resigned_on
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(company_number, officer_id) DO UPDATE SET
            company_name = excluded.company_name,
            company_status = excluded.company_status,
            office_name = excluded.office_name,
            officer_role = excluded.officer_role,
            officer_appointed_on = excluded.officer_appointed_on,
            officer_status = excluded.officer_status,
            officer_resigned_on = excluded.officer_resigned_on
        """,
        rows,
    )
    return len(rows)


def main(officer_id: str) -> int:
    """Fetch and store every company appointment for one officer ID."""
    payload = search_companies_by_officer_id(officer_id)
    with sqlite3.connect(DATABASE_PATH) as conn:
        stored_count = store_data_from_search_by_officer_id(payload, conn)

    print(
        f"Stored {stored_count} company appointment records for "
        f"{payload['office_name']} ({payload['officer_id']}) in "
        f"{DATABASE_PATH.name}."
    )
    return stored_count


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch all Companies House company appointments for an officer ID "
            "and store them in SQLite."
        )
    )
    parser.add_argument("officer_id", help="Companies House officer ID")
    return parser.parse_args()


if __name__ == "__main__":
    arguments = _parse_args()
    try:
        main(arguments.officer_id)
    except (CompaniesHouseError, ValueError, sqlite3.Error) as exc:
        raise SystemExit(f"Error: {exc}") from exc
