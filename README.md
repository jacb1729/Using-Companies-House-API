# Companies House

In the first half of 2025 I began to be engaged in a battle with Rebel Energy, which I resolved through the energy ombudsman. It was an awful experience throughout. It turns out that my problem was the least of the issue at Rebel, and they were forced to cease trading when millions green energy subsidies paid to Rebel went missing.

Further annoying is that such a corrupt organisation would be so loud about it, antagonistic to their customers, with superlatively poor service; I strongly believe they were fraudulent by design. All this in mind, I am still bitter about Rebel Energy. I wanted to find some of the people who should be accountable, and check out what they're up to now.

Wonderfully, Companies House has an API that we can use to search for those responsible for such corruption. This is what I've started working on.

**Importantly** this isn't a legal promise (as far as I know) that the officers associated with Rebel energy are each responsible for its corruption, even those active in 2025. But it's ethically clear to me that those officers should be scrutanised. Furthermore, take this tool as a search aid, but I can't at any point promise that it'll be bug free of course, so any connections that you find should be verified before you use it.

## Set-up

Create a Companies House developer account and live application at the
[developer portal](https://developer.company-information.service.gov.uk/get-started).
The script requires Python 3.11 or newer and has no third-party dependencies.

Supply the key through the environment (recommended):

```bash
export COMPANIES_HOUSE_API_KEY="your_key_here"
```

Alternatively, use the existing local TOML format. The section name can be any
name unless `--section` is supplied:

```toml
[key_header]
key_name = "optional label"
api_key = "your_key_here"
```

Keep `credentials.toml` private and out of source control.

## Search company officers

Fetch a company profile and all of its officer appointments, then store them in
SQLite:

```bash
python3 search_officers_by_company_number.py 10767623
```

This creates `search_data_by_company_number.db` next to the script. Officer
records are stored in the `search_data_by_company_number` table, keyed by
`company_number` and `officer_id`. Re-running a company search updates its
existing officer rows instead of duplicating them.

Search in the other direction by supplying an officer ID:

```bash
python3 search_companies_by_officer_id.py 7h2Kw6ljUYFhPbCb846YADzk4ag
```

This finds every company appointment grouped under that Companies House officer
ID and upserts those appointments into the same table using the same
`company_number` and `officer_id` conflict key.

## Example - Where are Rebel's officers now
I confirmed manually that there is at least one Rebel Director who is, at the time of writing, an active director of a different company. I've contacted the company at which they are active. Take a look at `Where_are_rebel_officers_now.ipynb`.