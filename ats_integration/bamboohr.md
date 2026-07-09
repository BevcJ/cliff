# BambooHR Public Job Retrieval

## When To Use

Use this connector candidate when the company careers page is on:

```text
https://{company_slug}.bamboohr.com/careers
```

The `company_slug` is the subdomain before `.bamboohr.com`.

## Candidate Listing Endpoint

Public BambooHR careers pages are commonly reported to use:

```http
GET https://{company_slug}.bamboohr.com/careers/list
```

This endpoint should be treated as a candidate public endpoint, not yet as a verified stable connector target in this repository.

## Verification Status

Observed checks from this environment returned Cloudflare `403` for several BambooHR tenant subdomains, including the vendor's own BambooHR-hosted careers page and multiple public-looking customer subdomains.

This means one of the following is likely true:

- BambooHR blocks some automated requests at the edge.
- Some tenants do not expose a public JSON careers endpoint.
- The endpoint may require browser/session behavior that should not be copied into the crawler.

Do not bypass Cloudflare, CAPTCHA, bot challenges, or cookie/session gates.

## Official API Boundary

BambooHR's documented API uses authenticated URLs under:

```text
https://{company_slug}.bamboohr.com/api/v1/...
```

Applicant tracking endpoints such as:

```http
GET https://{company_slug}.bamboohr.com/api/v1/applicant_tracking/jobs
```

require API authentication and ATS permissions. They are not suitable for public crawling without explicit customer authorization.

## Expected Response Shape

The public careers endpoint still needs tenant-level validation. If available, expect a JSON response with current public job openings and fields similar to:

```json
[
  {
    "id": 123,
    "jobOpeningName": "Software Engineer",
    "departmentLabel": "Engineering",
    "employmentStatusLabel": "Full-Time",
    "location": {
      "city": "Amsterdam",
      "state": "North Holland",
      "country": "Netherlands"
    }
  }
]
```

Do not rely on this exact shape until validated against accessible public tenants.

## Detail Retrieval

If a public listing endpoint is accessible, job detail pages may be available under the public careers site, for example:

```text
https://{company_slug}.bamboohr.com/careers/{job_id}
```

Use detail pages only when they are public, require no copied cookies, and do not trigger bot challenges.

## Fields To Normalize

Once a public response shape is verified, normalize:

- provider job ID -> `job_id`
- title field -> `job_title`
- department field -> `team` or `department`
- employment type/status field -> `employment_type`
- structured location fields -> `location`, `country`, and `country_code`
- public careers detail URL -> `job_url`
- description/detail body -> `description`

Country inference must use BambooHR job-location data only, not the discovery query country.

## Discovery Notes

Search-index discovery should target:

```text
site:bamboohr.com/careers "Amsterdam" "AI Engineer"
site:bamboohr.com/careers "Netherlands" "Machine Learning"
site:bamboohr.com/careers "GenAI"
```

Discovery results should be normalized to one board record per `{company_slug}.bamboohr.com` host.

## Notes

- Access rank is `2` in the discovery plan, but current verification risk is higher than Workable.
- Official BambooHR APIs are authenticated and should not be used for public crawling.
- Do not add a connector until at least a small sample of public tenants can be fetched without copied cookies, authentication, CAPTCHA bypass, or Cloudflare bypass.
- If public access remains blocked, defer BambooHR or treat it as a company-first/manual-validation source rather than a general ATS connector.
