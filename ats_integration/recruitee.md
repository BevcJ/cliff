# Recruitee Public Job Retrieval

## When To Use

Use this connector when the company careers page is on:

```text
https://{company_slug}.recruitee.com
```

The `company_slug` is the subdomain before `.recruitee.com`.

## Listing Endpoint

```http
GET https://{company_slug}.recruitee.com/api/offers/
```

## Example

```bash
curl 'https://careers.tellent.com/api/offers/'
```

## Response Shape

The response is JSON and contains an `offers` array:

```json
{
  "offers": [
    {
      "id": 2641582,
      "slug": "junior-accounts-payable-specialist-part-time-24-hoursweek",
      "title": "Junior Accounts Payable Specialist",
      "careers_url": "https://careers.tellent.com/o/...",
      "location": "Amsterdam, Noord-Holland, Netherlands",
      "department": "Finance"
    }
  ]
}
```

## Detail Endpoint

Recruitee supports detail retrieval by ID or slug:

```http
GET https://{company_slug}.recruitee.com/api/offers/{offer_id}
GET https://{company_slug}.recruitee.com/api/offers/{offer_slug}
```

The response contains an `offer` object with richer fields.

## Detail Response Fields

Common detail fields include:

- `title`
- `description`
- `requirements`
- `department`
- `location`, `locations`, `city`, `country`, `country_code`
- `remote`, `hybrid`, `on_site`
- `employment_type_code`
- `salary`
- `careers_url`
- `careers_apply_url`
- `published_at`, `updated_at`

## Fields To Normalize

- `offer.id` -> `job_id`
- `offer.title` -> `job_title`
- `offer.department` -> `team`
- `offer.location` or `offer.locations` -> `location`
- `offer.country` or `offer.country_code` -> `country`
- `offer.remote`, `offer.hybrid`, `offer.on_site` -> `workplace_type`
- `offer.employment_type_code` -> `employment_type`
- `offer.description` and `offer.requirements` -> `description`
- `offer.salary` -> `compensation`
- `offer.careers_url` -> `job_url`

## Notes

- No authentication is required for public offers.
- The detail endpoint is recommended because listing responses may omit full descriptions.
- Custom domains can still use the same `/api/offers/` path.
