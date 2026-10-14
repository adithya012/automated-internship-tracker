# Contributing

Contributions that improve internship coverage, data quality, and documentation are welcome.

## Adding a company board

1. Confirm the employer publicly exposes a Greenhouse Job Board or Lever Postings endpoint.
2. Confirm the endpoint and its use comply with the employer/platform terms.
3. Add the board identifier to `config/boards.json`.
4. Run `python scripts/fetch_internships.py` locally and inspect the resulting README table.
5. Submit a pull request with a short explanation of the source.

Do not add credentials, scrape behind logins, bypass access controls, or commit personal data. Please verify that new sources permit automated access and respect their rate limits.
