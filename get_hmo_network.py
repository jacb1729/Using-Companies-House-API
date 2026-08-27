"""Match saved HMO pages to companies and expand their officer networks."""

from __future__ import annotations

import argparse
import re
import sqlite3
from pathlib import Path

from search_companies_by_officer_id import (
    search_companies_by_officer_id,
    store_data_from_search_by_officer_id,
)
from search_data_by_company_name import search_data_by_company_name
from search_officers_by_company_number import CompaniesHouseError, DATABASE_PATH


SCRIPT_DIRECTORY = Path(__file__).resolve().parent
HMO_PAGES = SCRIPT_DIRECTORY / "hmo_pages"
HMO_DATABASE_PATH = SCRIPT_DIRECTORY / "hmo_companies.db"


def _ensure_hmo_tables(hmo_conn: sqlite3.Connection) -> None:
    """Create the HMO pipeline's checkpoint and result tables."""
    hmo_conn.execute(
        """
        CREATE TABLE IF NOT EXISTS hmo_companies (
            company_name TEXT NOT NULL,
            company_number TEXT NOT NULL,
            filename TEXT NOT NULL,
            PRIMARY KEY (filename, company_number)
        )
        """
    )
    hmo_conn.execute(
        """
        CREATE TABLE IF NOT EXISTS processed_pages (
            filename TEXT PRIMARY KEY,
            match_count INTEGER NOT NULL
        )
        """
    )
    hmo_conn.execute(
        """
        INSERT OR IGNORE INTO processed_pages (filename, match_count)
        SELECT filename, COUNT(*)
        FROM hmo_companies
        GROUP BY filename
        """
    )


def query_all_hmo_pages() -> tuple[int, int]:
    """Match each unprocessed saved page and store its Companies House company."""
    if not HMO_PAGES.is_dir():
        raise FileNotFoundError(f"HMO page directory not found: {HMO_PAGES}")

    page_files = sorted(HMO_PAGES.glob("*.html"))
    processed_count = 0

    with sqlite3.connect(HMO_DATABASE_PATH) as hmo_conn:
        _ensure_hmo_tables(hmo_conn)
        processed_files = {
            row[0]
            for row in hmo_conn.execute("SELECT filename FROM processed_pages")
        }

        for index, page_file in enumerate(page_files, 1):
            if page_file.name in processed_files:
                print(f"{index}/{len(page_files)}: skipping {page_file.stem}")
                continue

            page_name = re.sub(r"-\d+$", "", page_file.stem)
            search_name = page_name.replace("-", " ")
            print(f"{index}/{len(page_files)}: {search_name}")
            matches = search_data_by_company_name(search_name)

            hmo_conn.executemany(
                """
                INSERT INTO hmo_companies (
                    company_name, company_number, filename
                ) VALUES (?, ?, ?)
                ON CONFLICT(filename, company_number) DO UPDATE SET
                    company_name = excluded.company_name
                """,
                [
                    (
                        match["company_name"],
                        match["company_number"],
                        page_file.name,
                    )
                    for match in matches
                ],
            )
            hmo_conn.execute(
                """
                INSERT INTO processed_pages (filename, match_count)
                VALUES (?, ?)
                ON CONFLICT(filename) DO UPDATE SET
                    match_count = excluded.match_count
                """,
                (page_file.name, len(matches)),
            )
            hmo_conn.commit()
            processed_count += 1

        matched_company_count = hmo_conn.execute(
            "SELECT COUNT(*) FROM hmo_companies"
        ).fetchone()[0]

    return processed_count, matched_company_count


def expand_all_hmo_officer_networks() -> int:
    """Store every company associated with each matched HMO officer."""
    with (
        sqlite3.connect(HMO_DATABASE_PATH) as hmo_conn,
        sqlite3.connect(DATABASE_PATH) as company_conn,
    ):
        _ensure_hmo_tables(hmo_conn)
        hmo_conn.execute(
            """
            CREATE TABLE IF NOT EXISTS expanded_officers (
                officer_id TEXT PRIMARY KEY
            )
            """
        )
        expanded_officer_ids = {
            row[0]
            for row in hmo_conn.execute(
                "SELECT officer_id FROM expanded_officers"
            )
        }
        company_numbers = [
            row[0]
            for row in hmo_conn.execute(
                """
                SELECT DISTINCT company_number
                FROM hmo_companies
                ORDER BY company_number
                """
            )
        ]

        officer_ids = {
            row[0]
            for company_number in company_numbers
            for row in company_conn.execute(
                """
                SELECT DISTINCT officer_id
                FROM search_data_by_company_number
                WHERE company_number = ?
                """,
                (company_number,),
            )
        }

        pending_officer_ids = sorted(officer_ids - expanded_officer_ids)
        for index, officer_id in enumerate(pending_officer_ids, 1):
            print(f"{index}/{len(pending_officer_ids)}: {officer_id}")
            officer_payload = search_companies_by_officer_id(officer_id)
            store_data_from_search_by_officer_id(officer_payload, company_conn)
            company_conn.commit()
            hmo_conn.execute(
                "INSERT INTO expanded_officers (officer_id) VALUES (?)",
                (officer_id,),
            )
            hmo_conn.commit()

    return len(pending_officer_ids)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Match saved HMO pages to Companies House records, then expand "
            "the network through every matched company's officers."
        )
    )
    parser.add_argument(
        "--phase",
        choices=("all", "match", "expand"),
        default="all",
        help="Pipeline phase to run (default: all)",
    )
    return parser.parse_args()


def main(phase: str = "all") -> None:
    """Run the requested pipeline phase or the complete pipeline."""
    if phase in {"all", "match"}:
        processed_count, matched_company_count = query_all_hmo_pages()
        print(
            f"Match phase complete: processed {processed_count} new pages; "
            f"stored {matched_company_count} matched company records."
        )

    if phase in {"all", "expand"}:
        expanded_count = expand_all_hmo_officer_networks()
        print(
            f"Expansion phase complete: expanded {expanded_count} new officers."
        )


if __name__ == "__main__":
    arguments = _parse_args()
    try:
        main(arguments.phase)
    except (CompaniesHouseError, FileNotFoundError, ValueError, sqlite3.Error) as exc:
        raise SystemExit(f"Error: {exc}") from exc
