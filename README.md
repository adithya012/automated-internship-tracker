# India Internship Tracker

An open-source, automatically updated list of IT internship opportunities in India and eligible remote locations.

**Updates:** GitHub Actions runs every six hours. The workflow fetches public listings, filters internships, removes duplicates, drops listings older than 30 days when a posting date is available, and updates this README.

<!-- JOBS:START -->
## Latest internship listings

> Last refreshed: **2026-10-24 04:46 UTC** · **0 listings** · Automatically updated every six hours.

Listings are collected from public sources. Verify eligibility and deadlines on the original application page.

No matching internships were returned by the configured sources in this run.

### Software Engineering

_No matching listings currently available._

### AI & Machine Learning

_No matching listings currently available._

### Data Science & Analytics

_No matching listings currently available._

### Web Development

_No matching listings currently available._

### Other IT Internships

_No matching listings currently available._

### Sources and attribution

- [Remotive](https://remotive.com/remote-jobs) — remote job listings; see the [API terms](https://remotive.com/remote-jobs/api).
- [Arbeitnow](https://www.arbeitnow.com/) — public job-board API.
- Greenhouse and Lever listings link to the original employer job pages.

_Listings with known posting dates older than 30 days are removed. Listings with unknown dates are retained._

<!-- JOBS:END -->

## Categories

Listings are grouped into:
- Software Engineering
- AI & Machine Learning
- Data Science & Analytics
- Web Development
- Other IT Internships

## Sources

The collector supports:
- **Remotive** public remote-jobs API
- **Arbeitnow** public job-board API
- **Greenhouse** public job-board endpoints for configured employers
- **Lever** public postings endpoints for configured employers

Coverage depends on source availability and the employer boards configured in `config/boards.json`. There is no single free API that covers every internship in India.

## Quick start

1. Fork or create a repository from these files.
2. In GitHub, open **Settings → Actions → General → Workflow permissions**.
3. Select **Read and write permissions** and save.
4. Open **Actions → Update Internship Listings → Run workflow**.
5. Check the workflow log and the updated README.

To run locally:

```bash
python -m pip install -r requirements.txt
python scripts/fetch_internships.py
```

Python 3.11 or later is recommended.

## Configure company career boards

Edit `config/boards.json` to add company board identifiers.

- **Greenhouse:** add the employer's board token (the identifier used in its Greenhouse job board URL).
- **Lever:** add the employer's site identifier (the identifier used in its Lever postings URL).

Example configuration:

```json
{
  "greenhouse_boards": ["example-board-token"],
  "lever_sites": ["example-company"]
}
```

Replace these examples with real employer identifiers. Do not assume that every company uses either platform.

## Cleanup and data quality

- Jobs with a known posting date older than 30 days are removed.
- Listings with unknown dates are retained rather than deleted.
- Duplicate detection uses normalized application URLs and company/title/location.
- If every source fails, the script exits without overwriting the existing README or cached data.
- If some sources fail, the script retains previously cached listings while processing successful sources.
- A listing disappearing from a source does not necessarily mean it has expired. Check the original application page before applying.

## Privacy and responsible use

This project uses public job-board endpoints and does not require a personal account or API key for the included public endpoints. Follow each provider's terms, attribution requirements, and rate limits. Do not bypass access controls or scrape sources that prohibit it.

## License

MIT License. The license covers this repository's code and documentation, not third-party job data or source websites' terms.
