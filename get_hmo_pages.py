"""List and save AgentHMO companies offering HMO management or lettings."""

import re
import time
from itertools import count
from pathlib import Path
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen
from numpy.random import poisson, randint

from random_word import RandomWords


ORIGIN = "https://www.agenthmo.co.uk"
DIRECTORY = f"{ORIGIN}/directory"
PAGES = Path(__file__).resolve().with_name("hmo_pages")

word_generator = RandomWords()


def scrape_agenthmo() -> list[str]:
    """Save and return every filtered company summary page."""
    companies: list[str] = []
    seen: set[str] = set()
    PAGES.mkdir(exist_ok=True)

    for page in count(1):
        query = urlencode(
            {"category": "hmo-management,hmo-lettings", "page": page}
        )
        request = Request(
            f"{DIRECTORY}?{query}",
            headers={"User-Agent": f"{word_generator.get_random_word()}/0.{randint(1)}"},
        )
        with urlopen(request, timeout=30) as response:
            html = response.read().decode("utf-8")

        paths = dict.fromkeys(
            re.findall(r'href=["\'](/directory/[^/"\'?#]+)', html)
        )
        new_companies = [
            urljoin(ORIGIN, path) for path in paths if path not in seen
        ]
        if not new_companies:
            return companies

        companies.extend(new_companies)
        seen.update(paths)

        for company in new_companies:
            output = PAGES / f"{company.rsplit('/', 1)[-1]}.html"
            if output.exists():
                continue
            request = Request(
                company,
                headers={"User-Agent": f"{word_generator.get_random_word()}/0.{randint(1)}"},
            )
            with urlopen(request, timeout=30) as response:
                output.write_bytes(response.read())
            time.sleep(0.5 + poisson(1))

        time.sleep(0.5 + poisson(1))


if __name__ == "__main__":
    print(*scrape_agenthmo(), sep="\n")
