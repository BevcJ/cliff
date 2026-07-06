# Lever Public Job Retrieval

## When To Use

Use this connector when the company careers page is on:

```text
https://jobs.lever.co/{site_slug}
```

The `site_slug` is the path segment after `jobs.lever.co`.

## Listing Endpoint

```http
GET https://api.lever.co/v0/postings/{site_slug}?mode=json
```

For EU-hosted tenants, try:

```http
GET https://api.eu.lever.co/v0/postings/{site_slug}?mode=json
```

## Example

```bash
curl 'https://api.lever.co/v0/postings/leverdemo?mode=json'
```

## Response Shape

The response is a JSON array:

```json
[
  {
    "id": "33538a2f-d27d-4a96-8f05-fa4b0e4d940e",
    "text": "AbelsonTaylor Writer",
    "hostedUrl": "https://jobs.lever.co/leverdemo/...",
    "applyUrl": "https://jobs.lever.co/leverdemo/.../apply",
    "categories": {
      "team": "Engineering",
      "location": "New York",
      "commitment": "Full-time"
    },
    "description": "...",
    "descriptionPlain": "...",
    "lists": []
  }
]
```

## Detail Endpoint

Use the posting ID from the listing response:

```http
GET https://api.lever.co/v0/postings/{site_slug}/{posting_id}
```

Append `?mode=json` if needed:

```http
GET https://api.lever.co/v0/postings/{site_slug}/{posting_id}?mode=json
```

## Fields To Normalize

- `id` -> `job_id`
- `text` -> `job_title`
- `categories.team` -> `team`
- `categories.location` -> `location`
- `categories.commitment` -> `employment_type`
- `categories.department` if present -> department/team metadata
- `description`, `descriptionBody`, `additional`, `lists` -> `description`
- `hostedUrl` -> `job_url`
- `createdAt` -> source created timestamp

## Notes

- No authentication is required for public postings.
- Lever also has authenticated APIs for internal recruiting objects; do not use those for public job ingestion.
- Some fields can be HTML and some have `Plain` variants. Prefer HTML for evidence storage and plain text for classification.
