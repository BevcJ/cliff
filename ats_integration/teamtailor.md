# Teamtailor Public Job Retrieval

## When To Use

Use this connector when the company careers page is on:

```text
https://{company_slug}.teamtailor.com
```

The `company_slug` is the subdomain before `.teamtailor.com`.

## Listing Feed

```http
GET https://{company_slug}.teamtailor.com/jobs.rss
```

## Example

```bash
curl 'https://career.teamtailor.com/jobs.rss'
```

## Response Shape

The response is RSS XML:

```xml
<rss version="2.0" xmlns:tt="https://teamtailor.com/locations">
  <channel>
    <item>
      <title>Performance Marketer</title>
      <link>https://career.teamtailor.com/jobs/...</link>
      <description><![CDATA[...]]></description>
      <pubDate>...</pubDate>
      <remoteStatus>hybrid</remoteStatus>
      <guid>...</guid>
      <tt:locations>
        <tt:location>
          <tt:name>London</tt:name>
          <tt:city>London</tt:city>
          <tt:country>United Kingdom</tt:country>
        </tt:location>
      </tt:locations>
      <tt:department>Engineering</tt:department>
      <tt:role>Software Engineering</tt:role>
      <tt:division>Product</tt:division>
    </item>
  </channel>
</rss>
```

## Detail Retrieval

The first-pass connector uses the RSS feed only. It does not fetch or parse public job detail HTML pages because RSS already contains current jobs, descriptions, locations, departments, roles, remote status, publish dates, and job URLs for observed boards.

If a future connector needs fields not present in RSS, fetch each `item/link` and parse the public job page as a separate enhancement.

The page can contain richer fields such as:

- department
- location
- remote or hybrid tags
- employment type
- full description sections
- application URL

## Fields To Normalize

- `item/guid` or URL-derived ID -> `job_id`
- `item/title` -> `job_title`
- `item/link` -> `job_url`
- `item/description` -> `description` and provider HTML description
- `item/pubDate` -> source published timestamp
- `item/remoteStatus` -> `workplace_type`
- `tt:locations/tt:location` -> `location`, `job_locations_raw`, country inference fields
- `tt:department` -> `team` and `department`
- `tt:role` -> provider role field
- `tt:division` -> division

## Notes

- Teamtailor has an official JSON API, but it requires an API token and should not be used for public crawling unless explicitly authorized.
- RSS is public and simple. It may be less complete than the job detail page, but observed feeds include enough data for the current pipeline.
- The first-pass connector accepts Teamtailor-hosted board URLs such as `https://{company_slug}.teamtailor.com` and preserves custom job links found inside RSS items as `job_url` and `source_url`.
- Direct custom-domain board inputs such as `https://careers.example.com/jobs.rss` are not supported yet. Add this only when there is a concrete seed-list or coverage need.
