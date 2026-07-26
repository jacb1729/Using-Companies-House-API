"""Fetch a company's officers from Companies House and store them in SQLite."""

from __future__ import annotations

import argparse
import base64
import json
import os
import sqlite3
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


API_ORIGIN = "https://api.company-information.service.gov.uk"
DATABASE_PATH = Path(__file__).resolve().with_name(
    "search_data_by_company_number.db"
)
TABLE_NAME = "search_data_by_company_number"
CREDENTIALS_PATH = Path(__file__).resolve().with_name("credentials.toml")
PAGE_SIZE = 100
EXPECTED_COLUMNS = (
    "company_number",
    "company_name",
    "company_status",
    "officer_id",
    "office_name",
    "officer_role",
    "officer_appointed_on",
    "officer_status",
    "officer_resigned_on",
)


class CompaniesHouseError(RuntimeError):
    """Raised when Companies House cannot return a usable response."""


class ResponseShapeError(CompaniesHouseError):
    """Raised when an API response is missing data required by this tool."""


def _load_api_configuration() -> tuple[str, str]:
    """Return the API key and API origin without exposing the key."""
    environment_key = os.environ.get("COMPANIES_HOUSE_API_KEY")
    environment_origin = os.environ.get("COMPANIES_HOUSE_BASE_URL")
    if environment_key:
        configured_origin = environment_origin or API_ORIGIN
        origin = configured_origin.rstrip("/")
        parsed_origin = urllib.parse.urlsplit(origin)
        if parsed_origin.scheme != "https" or not parsed_origin.netloc:
            raise CompaniesHouseError(
                "The Companies House base URL must be an absolute HTTPS URL."
            )
        return environment_key, origin

    try:
        with CREDENTIALS_PATH.open("rb") as credentials_file:
            credentials = tomllib.load(credentials_file)
    except FileNotFoundError as exc:
        raise CompaniesHouseError(
            "No API key found. Set COMPANIES_HOUSE_API_KEY or create "
            f"{CREDENTIALS_PATH.name}."
        ) from exc
    except tomllib.TOMLDecodeError as exc:
        raise CompaniesHouseError(
            f"{CREDENTIALS_PATH.name} is not valid TOML."
        ) from exc

    requested_section = os.environ.get("COMPANIES_HOUSE_CREDENTIALS_SECTION")
    if requested_section:
        section = credentials.get(requested_section)
        if not isinstance(section, dict) or not section.get("api_key"):
            raise CompaniesHouseError(
                "COMPANIES_HOUSE_CREDENTIALS_SECTION does not identify a "
                "section containing api_key."
            )
    else:
        section = next(
            (
                value
                for value in credentials.values()
                if isinstance(value, dict) and value.get("api_key")
            ),
            None,
        )
        if section is None:
            raise CompaniesHouseError(
                f"{CREDENTIALS_PATH.name} has no section containing api_key."
            )

    api_key = section["api_key"]
    if not isinstance(api_key, str) or not api_key:
        raise CompaniesHouseError("The configured Companies House API key is empty.")

    configured_origin = (
        environment_origin or section.get("base_url") or API_ORIGIN
    )
    if not isinstance(configured_origin, str):
        raise CompaniesHouseError("The configured Companies House base URL is invalid.")
    origin = configured_origin.rstrip("/")
    parsed_origin = urllib.parse.urlsplit(origin)
    if parsed_origin.scheme != "https" or not parsed_origin.netloc:
        raise CompaniesHouseError(
            "The Companies House base URL must be an absolute HTTPS URL."
        )

    return api_key, origin


def _validate_company_number(company_number: str) -> str:
    """Validate without converting an opaque company number to an integer."""
    if not isinstance(company_number, str):
        raise TypeError("company_number must be a string")
    if not company_number:
        raise ValueError("company_number must not be empty")
    if company_number != company_number.strip():
        raise ValueError("company_number must not contain surrounding whitespace")
    if any(character.isspace() or ord(character) < 32 for character in company_number):
        raise ValueError("company_number must not contain whitespace or control characters")
    if "/" in company_number:
        raise ValueError("company_number must be one URL path segment")
    return company_number


def _api_get_json(
    origin: str,
    api_key: str,
    path: str,
    query: dict[str, int | str] | None = None,
) -> dict[str, Any]:
    """Issue an authenticated GET and return a JSON object."""
    encoded_query = urllib.parse.urlencode(query or {})
    url = f"{origin}{path}"
    if encoded_query:
        url = f"{url}?{encoded_query}"

    authorization = base64.b64encode(f"{api_key}:".encode("utf-8")).decode("ascii")
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "Authorization": f"Basic {authorization}",
            "User-Agent": "companies-house-company-officer-search/1.0",
        },
        method="GET",
    )

    retry_delays = (0.5, 1.0)
    for attempt in range(len(retry_delays) + 1):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.load(response)
            if not isinstance(payload, dict):
                raise ResponseShapeError(
                    f"Companies House returned a non-object response for {path}."
                )
            return payload
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                retry_after = exc.headers.get("Retry-After")
                try:
                    retry_seconds = float(retry_after) if retry_after else None
                except ValueError:
                    retry_seconds = None
                if (
                    attempt < len(retry_delays)
                    and retry_seconds is not None
                    and 0 <= retry_seconds <= 30
                ):
                    time.sleep(retry_seconds)
                    continue
                raise CompaniesHouseError(
                    "Companies House rate limit reached (HTTP 429). Retry later."
                ) from exc
            if 500 <= exc.code < 600 and attempt < len(retry_delays):
                time.sleep(retry_delays[attempt])
                continue
            descriptions = {
                400: "bad request",
                401: "unauthorised; check the API key",
                404: "resource not found",
            }
            description = descriptions.get(exc.code, "request failed")
            raise CompaniesHouseError(
                f"Companies House {description} (HTTP {exc.code}) for {path}."
            ) from exc
        except urllib.error.URLError as exc:
            if attempt < len(retry_delays):
                time.sleep(retry_delays[attempt])
                continue
            raise CompaniesHouseError(
                f"Could not reach Companies House for {path}: {exc.reason}"
            ) from exc
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ResponseShapeError(
                f"Companies House returned invalid JSON for {path}."
            ) from exc

    raise AssertionError("unreachable")


def _extract_officer_id(officer: dict[str, Any]) -> str:
    """Extract the opaque officer ID from its documented appointments link."""
    links = officer.get("links")
    if not isinstance(links, dict):
        raise ResponseShapeError("An officer record has no links object.")
    officer_links = links.get("officer")
    if not isinstance(officer_links, dict):
        raise ResponseShapeError("An officer record has no officer links object.")
    appointments_link = officer_links.get("appointments")
    if not isinstance(appointments_link, str):
        raise ResponseShapeError(
            "An officer record has no officer appointments link."
        )

    path_parts = urllib.parse.urlsplit(appointments_link).path.split("/")
    if (
        len(path_parts) != 4
        or path_parts[0] != ""
        or path_parts[1] != "officers"
        or not path_parts[2]
        or path_parts[3] != "appointments"
    ):
        raise ResponseShapeError(
            "An officer appointments link has an unexpected URL shape."
        )
    return path_parts[2]


def _status_for_unresigned_officers(
    unresigned_count: int,
    active_count: Any,
    inactive_count: Any,
) -> str:
    """Use list totals only when they classify all unresigned appointments."""
    if not isinstance(active_count, int):
        return "unknown"
    if inactive_count is None:
        inactive_count = 0
    if not isinstance(inactive_count, int):
        return "unknown"
    if active_count == unresigned_count and inactive_count == 0:
        return "active"
    if inactive_count == unresigned_count and active_count == 0:
        return "inactive"
    return "unknown"


def search_officers_by_company_number(company_number: str) -> dict[str, Any]:
    """Get a company profile and every officer appointment for the company."""
    company_number = _validate_company_number(company_number)
    api_key, origin = _load_api_configuration()
    encoded_company_number = urllib.parse.quote(company_number, safe="")

    profile = _api_get_json(
        origin,
        api_key,
        f"/company/{encoded_company_number}",
    )
    company_name = profile.get("company_name")
    company_status = profile.get("company_status")
    canonical_company_number = profile.get("company_number", company_number)
    if not isinstance(company_name, str) or not company_name:
        raise ResponseShapeError("The company profile has no company_name.")
    if not isinstance(company_status, str) or not company_status:
        raise ResponseShapeError("The company profile has no company_status.")
    if not isinstance(canonical_company_number, str):
        raise ResponseShapeError("The company profile has an invalid company_number.")

    raw_officers: list[dict[str, Any]] = []
    offset = 0
    total_results: int | None = None
    active_count: int | None = None
    inactive_count: int | None = None

    while True:
        page = _api_get_json(
            origin,
            api_key,
            f"/company/{encoded_company_number}/officers",
            {"items_per_page": PAGE_SIZE, "start_index": offset},
        )
        items = page.get("items")
        if not isinstance(items, list) or not all(
            isinstance(item, dict) for item in items
        ):
            raise ResponseShapeError("The officer list has an invalid items array.")

        page_total = page.get("total_results")
        page_start = page.get("start_index")
        if not isinstance(page_total, int) or page_total < 0:
            raise ResponseShapeError("The officer list has an invalid total_results.")
        if not isinstance(page_start, int) or page_start < 0:
            raise ResponseShapeError("The officer list has an invalid start_index.")
        if total_results is None:
            total_results = page_total
            active_count = page.get("active_count")
            inactive_count = page.get("inactive_count")
        elif page_total != total_results:
            raise ResponseShapeError(
                "The officer-list total changed while pages were being retrieved."
            )

        raw_officers.extend(items)
        next_offset = page_start + len(items)
        if next_offset >= page_total:
            break
        if not items or next_offset <= offset:
            raise ResponseShapeError(
                "Officer-list pagination stopped making progress."
            )
        offset = next_offset

    unresigned_count = sum(
        not isinstance(officer.get("resigned_on"), str)
        for officer in raw_officers
    )
    unresigned_status = _status_for_unresigned_officers(
        unresigned_count,
        active_count,
        inactive_count,
    )

    officers = []
    for officer in raw_officers:
        name = officer.get("name")
        role = officer.get("officer_role")
        if not isinstance(name, str) or not name:
            raise ResponseShapeError("An officer record has no name.")
        if not isinstance(role, str) or not role:
            raise ResponseShapeError("An officer record has no officer_role.")

        resigned_on = officer.get("resigned_on")
        if not isinstance(resigned_on, str):
            resigned_on = None

        appointed_on = officer.get("appointed_on")
        if not isinstance(appointed_on, str):
            appointed_before = officer.get("appointed_before")
            appointed_on = (
                f"before {appointed_before}"
                if isinstance(appointed_before, str)
                else None
            )

        officers.append(
            {
                "officer_id": _extract_officer_id(officer),
                "office_name": name,
                "officer_role": role,
                "officer_appointed_on": appointed_on,
                "officer_status": (
                    "resigned" if resigned_on is not None else unresigned_status
                ),
                "officer_resigned_on": resigned_on,
            }
        )

    if total_results is None:
        raise ResponseShapeError("Companies House returned no officer-list page.")
    if len(officers) != total_results:
        raise ResponseShapeError(
            "The number of retrieved officers does not match total_results."
        )

    return {
        "company_number": canonical_company_number,
        "company_name": company_name,
        "company_status": company_status,
        "officers": officers,
    }


def _ensure_table(conn: sqlite3.Connection) -> None:
    """Create the destination table and reject an incompatible existing table."""
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
            company_number TEXT NOT NULL,
            company_name TEXT NOT NULL,
            company_status TEXT NOT NULL,
            officer_id TEXT NOT NULL,
            office_name TEXT NOT NULL,
            officer_role TEXT NOT NULL,
            officer_appointed_on TEXT,
            officer_status TEXT NOT NULL,
            officer_resigned_on TEXT,
            PRIMARY KEY (company_number, officer_id)
        )
        """
    )
    actual_columns = tuple(
        row[1]
        for row in conn.execute(f"PRAGMA table_info({TABLE_NAME})").fetchall()
    )
    if actual_columns != EXPECTED_COLUMNS:
        raise sqlite3.DatabaseError(
            f"Table {TABLE_NAME} has columns {actual_columns!r}; expected "
            f"{EXPECTED_COLUMNS!r}."
        )


def store_data_from_search_by_company_number(
    payload: dict[str, Any],
    conn: sqlite3.Connection,
) -> int:
    """Insert or update all officer rows and return the number stored."""
    _ensure_table(conn)

    company_number = payload.get("company_number")
    company_name = payload.get("company_name")
    company_status = payload.get("company_status")
    officers = payload.get("officers")
    if not all(
        isinstance(value, str) and value
        for value in (company_number, company_name, company_status)
    ):
        raise ResponseShapeError("The payload has invalid company fields.")
    if not isinstance(officers, list):
        raise ResponseShapeError("The payload has no officers list.")

    rows = []
    for officer in officers:
        if not isinstance(officer, dict):
            raise ResponseShapeError("The payload contains an invalid officer.")
        officer_id = officer.get("officer_id")
        office_name = officer.get("office_name")
        officer_role = officer.get("officer_role")
        officer_status = officer.get("officer_status")
        if not all(
            isinstance(value, str) and value
            for value in (
                officer_id,
                office_name,
                officer_role,
                officer_status,
            )
        ):
            raise ResponseShapeError(
                "An officer is missing a value required by the database."
            )
        rows.append(
            (
                company_number,
                company_name,
                company_status,
                officer_id,
                office_name,
                officer_role,
                officer.get("officer_appointed_on"),
                officer_status,
                officer.get("officer_resigned_on"),
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


def main(company_number: str) -> int:
    """Fetch and store one company's officers."""
    payload = search_officers_by_company_number(company_number)
    with sqlite3.connect(DATABASE_PATH) as conn:
        stored_count = store_data_from_search_by_company_number(payload, conn)

    print(
        f"Stored {stored_count} officer records for "
        f"{payload['company_number']} ({payload['company_name']}, "
        f"status: {payload['company_status']}) in {DATABASE_PATH.name}."
    )
    return stored_count


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch all Companies House officers for a company number and "
            "store them in SQLite."
        )
    )
    parser.add_argument("company_number", help="Companies House company number")
    return parser.parse_args()


if __name__ == "__main__":
    arguments = _parse_args()
    try:
        main(arguments.company_number)
    except (CompaniesHouseError, ValueError, sqlite3.Error) as exc:
        raise SystemExit(f"Error: {exc}") from exc
