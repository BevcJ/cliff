# Workable Public Job Retrieval

## When To Use

Use this connector when the company careers page is on:

```text
https://apply.workable.com/{company_slug}
```

The `company_slug` is the first path segment after `apply.workable.com`.

Workable can also expose customer-specific or legacy domains such as:

```text
https://{company_slug}.workable.com
```

For the first connector pass, prefer `apply.workable.com/{company_slug}` because that is the current hosted careers app pattern.

## Listing Endpoints

Fetch account metadata first when useful:

```http
GET https://apply.workable.com/api/v1/accounts/{company_slug}?full=true
```

Fetch the public jobs list through the current careers app endpoint:

```http
POST https://apply.workable.com/api/v3/accounts/{company_slug}/jobs
Content-Type: application/json

{}
```

Useful filters observed in the careers app include:

```text
department
location
workplace
worktype
query
```

For broad collection, start with an empty JSON body and store the unfiltered response.

## Count Endpoint

The hosted careers app can request a count before loading jobs:

```http
GET https://apply.workable.com/api/v1/accounts/{company_slug}/jobs/count
```

This is useful for quick validation, but the connector should still rely on the listing endpoint for job data.

## Detail Endpoint

For listing items that pass title-only AI filtering and are not marked internal,
hidden, or non-`published`, use the `shortcode` to fetch richer public detail:

```http
GET https://apply.workable.com/api/v2/accounts/{company_slug}/jobs/{shortcode}
```

The detail response can include richer fields such as:

- `description`
- `requirements`
- `benefits`

## Example

```bash
curl -X POST \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  --data '{}' \
  'https://apply.workable.com/api/v3/accounts/workmotion/jobs'
```

## Response Shape

The listing response is JSON:

```json
{
  "total": 2,
  "results": [
    {
      "id": 5875457,
      "shortcode": "164CBEF1EB",
      "title": "HR Operations Specialist",
      "remote": true,
      "location": {
        "country": "Belgium",
        "countryCode": "BE",
        "city": "",
        "region": null
      },
      "locations": [
        {
          "country": "Belgium",
          "countryCode": "BE",
          "city": "",
          "region": null,
          "hidden": false
        }
      ],
      "state": "published",
      "isInternal": false,
      "published": "2026-07-07T00:00:00.000Z",
      "language": "en",
      "department": ["WorkMotion"],
      "workplace": "remote"
    }
  ]
}
```

The detail response repeats the listing fields and can add full job text:

```json
{
  "id": 5875457,
  "shortcode": "164CBEF1EB",
  "title": "HR Operations Specialist",
  "description": "<h3>...</h3>",
  "requirements": "",
  "benefits": ""
}
```

## Fields To Normalize

- `shortcode` or `id` -> `job_id`
- `title` -> `job_title`
- `department[]` -> `team` or `department`
- `location.countryCode` or `locations[].countryCode` -> `country_code`
- `location.country` or `locations[].country` -> `country`
- `location.city`, `location.region`, and `location.country` -> `location`
- `remote` or `workplace` -> `workplace_type`
- `published` -> source published timestamp
- detail `description`, `requirements`, and `benefits` -> `description` or description sections
- `https://apply.workable.com/{company_slug}/j/{shortcode}` -> `job_url`

## Discovery Notes

Search-index discovery should target:

```text
site:apply.workable.com "Amsterdam" "AI Engineer"
site:apply.workable.com "Netherlands" "Machine Learning"
site:apply.workable.com "GenAI"
```

Discovery results can point to board URLs or job URLs. Normalize both to one board record per `company_slug`.

## Auth And API Boundary

Workable also documents authenticated account APIs under Workable SPI/API paths. Those endpoints require API keys and must not be used for public crawling.

The endpoints above are used by the public hosted careers app and were verified without copied cookies or authentication.

## Notes

- Access rank is `2`: public JSON is available, but the endpoint is app-specific and less stable than the rank-1 providers.
- The listing endpoint uses `POST` with a JSON body even for an unfiltered public listing.
- Some known or old Workable account slugs return `404` or valid accounts with zero current jobs. Treat this as an empty or inactive board, not necessarily a connector failure.
- Use detail retrieval only after listing fetch succeeds and only for title-qualified public-visible candidates. Continue per job if a detail call fails.
- Store the full listing response and candidate detail responses in the raw wrapper so normalization can be replayed if the schema changes.
