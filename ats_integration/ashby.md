# Ashby Public Job Retrieval

## When To Use

Use this connector when the company careers page is on:

```text
https://jobs.ashbyhq.com/{company_slug}
```

The `company_slug` is the path segment after `jobs.ashbyhq.com`.

## Listing Endpoint

```http
GET https://api.ashbyhq.com/posting-api/job-board/{company_slug}
```

Optional compensation parameter:

```http
GET https://api.ashbyhq.com/posting-api/job-board/{company_slug}?includeCompensation=true
```

## Example

```bash
curl 'https://api.ashbyhq.com/posting-api/job-board/ashby?includeCompensation=true'
```

## Response Shape

The response is JSON and usually contains:

```json
{
  "apiVersion": "...",
  "jobs": [
    {
      "id": "7458d4e9-da2e-47bd-98cb-adfda43d42b2",
      "title": "Engineering Manager, EU",
      "location": "Remote - European Union",
      "department": "Engineering",
      "team": "Engineering",
      "employmentType": "FullTime",
      "jobUrl": "https://jobs.ashbyhq.com/...",
      "descriptionHtml": "..."
    }
  ]
}
```

## Detail Retrieval

The listing response usually includes enough detail for extraction. If a description or metadata field is missing, fetch the public `jobUrl` and parse the page as a fallback.

## Fields To Normalize

- `id` -> `job_id`
- `title` -> `job_title`
- `department` or `team` -> `team`
- `location` -> `location`
- `employmentType` -> `employment_type`
- `descriptionHtml` -> `description`
- `jobUrl` -> `job_url`
- compensation fields, if returned -> `compensation`

## Notes

- No authentication is required for public job-board retrieval.
- Filter out unlisted jobs if the response includes visibility flags such as `isListed`.
- Store the raw JSON response because Ashby schemas can evolve.
