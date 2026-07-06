# ATS Integration Notes

This folder documents how to retrieve public job-board data for access-rank-1 ATS platforms when we already know the company identifier used by the provider.

Access-rank-1 means the provider exposes a simple public structured source for jobs shown on its hosted careers site. These guides only cover public job data. Do not use private customer/admin APIs, copied cookies, or authenticated endpoints unless explicitly authorized.

## Rank-1 Guides

| Platform | Guide | Primary Input | Primary Data Source |
|---|---|---|---|
| Ashby | [ashby.md](ashby.md) | Ashby board slug | Public JSON Posting API |
| Greenhouse | [greenhouse.md](greenhouse.md) | Greenhouse board token | Public Job Board API |
| Lever | [lever.md](lever.md) | Lever site slug | Public postings JSON API |
| SmartRecruiters | [smartrecruiters.md](smartrecruiters.md) | Company identifier | Public postings API |
| Recruitee | [recruitee.md](recruitee.md) | Recruitee subdomain | Public offers API |
| Personio | [personio.md](personio.md) | Personio subdomain | Public XML feed |
| Teamtailor | [teamtailor.md](teamtailor.md) | Teamtailor subdomain | Public RSS feed |

## Common Retrieval Flow

1. Normalize the known company identifier for the ATS.
2. Fetch the listing endpoint.
3. Store the raw response with timestamp and source URL.
4. Extract job IDs, titles, locations, departments, descriptions, employment type, compensation, and public job URLs.
5. Fetch detail endpoints or pages only when the listing response is incomplete.
6. Normalize into the shared job schema used by the company intelligence pipeline.
