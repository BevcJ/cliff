# SmartRecruiters Public Job Retrieval

## When To Use

Use this connector when the company careers page is on:

```text
https://careers.smartrecruiters.com/{company_identifier}
```

The `company_identifier` is the path segment after `careers.smartrecruiters.com`.

## Listing Endpoint

```http
GET https://api.smartrecruiters.com/v1/companies/{company_identifier}/postings
```

Useful query parameters:

```text
limit=100
offset=0
q={search_text}
```

## Example

```bash
curl 'https://api.smartrecruiters.com/v1/companies/SmartRecruiters/postings?limit=100&offset=0'
```

## Response Shape

The response is JSON and contains paginated `content`:

```json
{
  "content": [
    {
      "id": "744000132215059",
      "name": "Engineering Team Lead",
      "ref": "https://api.smartrecruiters.com/v1/companies/SmartRecruiters/postings/744000132215059",
      "location": {
        "city": "Krakow",
        "country": "pl",
        "remote": true,
        "hybrid": false,
        "fullLocation": "Krakow, Poland"
      }
    }
  ],
  "limit": 100,
  "offset": 0,
  "totalFound": 1
}
```

## Detail Endpoint

Use the `ref` field from each listing item, or construct:

```http
GET https://api.smartrecruiters.com/v1/companies/{company_identifier}/postings/{posting_id}
```

The detail response usually includes richer job ad sections, such as description, qualifications, and additional information.

## Fields To Normalize

- `id` -> `job_id`
- `name` -> `job_title`
- `location.fullLocation` -> `location`
- `location.country` -> `country`
- `location.remote` and `location.hybrid` -> `workplace_type`
- detail `jobAd.sections` -> `description`
- `ref` or public posting URL fields -> `source_url`

## Pagination

Fetch pages until `offset + limit >= totalFound`.

## Notes

- Public postings can be fetched without authentication in observed company career pages.
- SmartRecruiters also documents customer APIs with API-key auth. Those are not needed for public job ingestion.
- Always store the `ref` URL because it is the canonical API detail source.
