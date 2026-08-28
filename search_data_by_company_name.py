"""Find companies by name, then store their officers in SQLite."""

from __future__ import annotations

import argparse
import re
import sqlite3
from typing import Any

from search_officers_by_company_number import (
    DATABASE_PATH,
    CompaniesHouseError,
    ResponseShapeError,
    _api_get_json,
    _load_api_configuration,
    search_officers_by_company_number,
    store_data_from_search_by_company_number,
)


PROMPT_ON_MULTIPLE_MATCHES = False
PROMPT_TO_CHANGE_NAME_ON_NO_MATCHES = False
SEARCH_RESULT_LIMIT = 20
FALLBACK_RESULT_LIMIT = 3


def _normalized_company_name(company_name: str) -> str:
    """Normalize punctuation and a trailing legal suffix for comparison."""
    words = re.findall(r"[a-z0-9]+", company_name.casefold().replace("&", " and "))
    if words and words[-1] in {"limited", "ltd", "llp", "plc"}:
        words.pop()
    return " ".join(words)


def _search_items(
    page: dict[str, Any],
    name_field: str,
) -> list[dict[str, Any]]:
    """Validate search items and give each one the usual title field."""
    items = page.get("items", [])
    if not isinstance(items, list) or not all(
        isinstance(item, dict) for item in items
    ):
        raise ResponseShapeError("The company search has an invalid items array.")

    matches = []
    for item in items:
        company_name = item.get(name_field)
        company_number = item.get("company_number")
        if not isinstance(company_name, str) or not isinstance(
            company_number, str
        ):
            raise ResponseShapeError(
                "A company-search result has no name or company number."
            )
        matches.append({**item, "title": company_name})
    return matches


def _unique_matches(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep the first result for each opaque company number."""
    unique = {}
    for item in matches:
        unique.setdefault(item["company_number"], item)
    return list(unique.values())


def _search_company_matches(company_name: str) -> list[dict[str, Any]]:
    """Return exact, ranked, or advanced company matches in that order."""
    if not isinstance(company_name, str) or not company_name.strip():
        raise ValueError("company_name must be a non-empty string")

    api_key, origin = _load_api_configuration()
    page = _api_get_json(
        origin,
        api_key,
        "/search/companies",
        {
            "q": company_name.strip(),
            "items_per_page": SEARCH_RESULT_LIMIT,
            "start_index": 0,
        },
    )
    matches = _search_items(page, "title")

    normalized_search = _normalized_company_name(company_name)
    exact_matches = [
        match
        for match in matches
        if _normalized_company_name(match["title"]) == normalized_search
    ]
    if exact_matches:
        return _unique_matches(exact_matches)
    if matches:
        return _unique_matches(matches[:FALLBACK_RESULT_LIMIT])

    advanced_page = _api_get_json(
        origin,
        api_key,
        "/advanced-search/companies",
        {
            "company_name_includes": company_name.strip(),
            "size": FALLBACK_RESULT_LIMIT,
            "start_index": 0,
        },
        empty_on_not_found=True,
    )
    return _unique_matches(
        _search_items(advanced_page, "company_name")[:FALLBACK_RESULT_LIMIT]
    )


def _choose_matches(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Prompt for particular results, or return every result."""
    if len(matches) < 2 or not PROMPT_ON_MULTIPLE_MATCHES:
        return matches

    print("Multiple Companies House matches found:")
    for index, match in enumerate(matches, 1):
        status = match.get("company_status", "unknown status")
        print(
            f"  {index}. {match['title']} "
            f"({match['company_number']}, {status})"
        )

    while True:
        answer = input(
            "Choose numbers separated by commas, type 'all', "
            "or press Enter to skip: "
        ).strip()
        if not answer:
            return []
        if answer.casefold() == "all":
            return matches
        try:
            indexes = list(dict.fromkeys(int(value) for value in answer.split(",")))
        except ValueError:
            print("Enter result numbers separated by commas.")
            continue
        if indexes and all(1 <= index <= len(matches) for index in indexes):
            return [matches[index - 1] for index in indexes]
        print(f"Choose numbers from 1 to {len(matches)}.")


def search_data_by_company_name(company_name: str) -> list[dict[str, str]]:
    """Find selected companies by name and store their officer data."""
    if not isinstance(company_name, str) or not company_name.strip():
        raise ValueError("company_name must be a non-empty string")
    search_name = company_name.strip()

    while True:
        matches = _search_company_matches(search_name)
        if matches or not PROMPT_TO_CHANGE_NAME_ON_NO_MATCHES:
            break
        replacement = input(
            f"No matches found for {search_name!r}. "
            "Enter another name, or press Enter to skip: "
        ).strip()
        if not replacement:
            break
        search_name = replacement

    selected = _choose_matches(matches)
    stored_companies: list[dict[str, str]] = []
    with sqlite3.connect(DATABASE_PATH) as conn:
        for match in selected:
            payload = search_officers_by_company_number(match["company_number"])
            store_data_from_search_by_company_number(payload, conn)
            stored_companies.append(
                {
                    "company_name": payload["company_name"],
                    "company_number": payload["company_number"],
                }
            )

    return stored_companies


def main(company_name: str) -> list[dict[str, str]]:
    """Search, store, and report the selected companies."""
    companies = search_data_by_company_name(company_name)
    for company in companies:
        print(f"{company['company_number']}\t{company['company_name']}")
    return companies


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Find companies by name and store their officers in SQLite."
    )
    parser.add_argument("company_name", help="Company name to search")
    return parser.parse_args()


if __name__ == "__main__":
    arguments = _parse_args()
    try:
        main(arguments.company_name)
    except (CompaniesHouseError, ValueError, sqlite3.Error) as exc:
        raise SystemExit(f"Error: {exc}") from exc
