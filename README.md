# Using Companies House (on the hunt for corruption)

TLDR: Here are tools by which to connect actors to risk of association, through the officer-company relationship. The tools collect and use company and actor association data from Companies House (UK). So far I've looked at selected convicted companies and HMO management companies as examples.

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
python search_officers_by_company_number.py 10767623
```

This creates `search_data_by_company_number.db` next to the script. Officer
records are stored in the `search_data_by_company_number` table, keyed by
`company_number` and `officer_id`. Re-running a company search updates its
existing officer rows instead of duplicating them.

You can search by company name if necessary too (`search_data_by_company_name.py`).

Search in the other direction by supplying an officer ID:

```bash
python search_companies_by_officer_id.py 7h2Kw6ljUYFhPbCb846YADzk4ag
```

This finds every company appointment grouped under that Companies House officer
ID and upserts those appointments into the same table using the same
`company_number` and `officer_id` conflict key.

## Example - Where are Rebel's officers now

In the first half of 2025 I began to be engaged in a battle with Rebel Energy, which I resolved through the energy ombudsman. It was an awful experience throughout. It turns out that my problem was the least of the issue at Rebel, and they were forced to cease trading when millions green energy subsidies paid to Rebel went missing.

Further annoying is that such a corrupt organisation would be so loud about it, antagonistic to their customers, with superlatively poor service; I strongly believe they were fraudulent by design. All this in mind, I am still bitter about Rebel Energy. I wanted to find some of the people who should be accountable, and check out what they're up to now.

Wonderfully, Companies House has an API that we can use to search for those responsible for such corruption. This is what I've started working on.

**Importantly** this isn't a legal promise (as far as I know) that the officers associated with Rebel energy are each responsible for its corruption, even those active in 2025. But it's ethically clear to me that those officers should be scrutanised. Furthermore, take this tool as a search aid, but I can't at any point promise that it'll be bug free of course, so any connections that you find should be verified before you use it.

I confirmed manually that there is at least one Rebel Director who is, at the time of writing, an active director of a different company. I've contacted the company at which they are active. Take a look at `Where_are_rebel_officers_now.ipynb`.

The same code can, of course, be used if you know the name of a company that has wronged you before and also turned out to be (by your judgement) fraudulent.

I was interested to see how this same tech could be applied to more aggregious cases of known money laundering fronts. Naturally, this criminal activity is quieter by design, with very small networks of connection between listed directors per case of laundering.

## Example - HMO company networks

Companies which manage or let HMOs are particularly exposed to enabling illegal practice, due to the prevelance of unlicenced HMOs, as well as associated criminal activity. This is a sector which I believe is typically negligent, and in places criminal, so it's worth knowing who is active here. We also have a hope of knowing how officers are active, based on the example of Howsy

Before I knew about the red flags of unlicenced HMOs, I lived in a cramped flat in Whitechapel, operated by Howsy, before they were acquired by Dexters (through "accelerated sale", i.e. due to mismanagement). There were issues with rats, mould, and fire safety. As with Rebel, Howsy threatened to sue me, this time for the rent I'd withheld in protest, citing evidence that the property was not fit for occupation, and through local housing officers I was able to get them to immediately cancel my let and refund me much of my rent (hypothetical or paid).

Howsy's officers are active at tens of companies. How typical is this?

I scraped a source of HMO Management/Licencing company names, used this to pull companies which match each name