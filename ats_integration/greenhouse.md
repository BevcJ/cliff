# Greenhouse Public Job Retrieval

## When To Use

Use this connector when the company careers page is on:

```text
https://boards.greenhouse.io/{board_token}
```

The `board_token` is the path segment after `boards.greenhouse.io`.

## Listing Endpoint

```http
GET https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true
```

`content=true` includes full job description content, departments, and offices in the list response.

## Example

```bash
curl 'https://boards-api.greenhouse.io/v1/boards/airbnb/jobs?content=true'
```

## Response Shape

The response is JSON and contains:

```json
{
  "jobs": [
    {
      "id": 7995153,
      "title": "Acquisition Manager",
      "updated_at": "2026-06-16T00:00:00Z",
      "location": { "name": "Berlin, Germany" },
      "absolute_url": "https://...",
      "content": "<p>...</p>",
      "departments": [],
      "offices": []
    }
  ],
  "meta": { "total": 223 }
}
```

## Detail Endpoint

Use the detail endpoint when application questions, pay transparency, or additional per-job metadata is needed.

```http
GET https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs/{job_id}?questions=true&pay_transparency=true
```

## Fields To Normalize

- `id` -> `job_id`
- `title` -> `job_title`
- `location.name` -> `location`
- `departments[].name` -> `team`
- `offices[].location` or `offices[].name` -> location metadata
- `content` -> `description`
- `absolute_url` -> `job_url`
- `pay_input_ranges` -> `compensation`
- `updated_at` -> source update timestamp

## Notes

- Greenhouse explicitly exposes public GET endpoints without authentication.
- Application submission endpoints are not part of this ingestion flow and require authentication.
- Some companies use custom career pages but still include Greenhouse job IDs or board tokens behind the scenes.
