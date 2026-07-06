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
<rss>
  <channel>
    <item>
      <title>Performance Marketer</title>
      <link>https://career.teamtailor.com/jobs/...</link>
      <description><![CDATA[...]]></description>
      <pubDate>...</pubDate>
      <guid>...</guid>
    </item>
  </channel>
</rss>
```

## Detail Retrieval

The RSS feed is good for discovering active jobs. For full extraction, fetch each `item/link` and parse the public job page.

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
- `item/description` -> initial `description`
- `item/pubDate` -> source published timestamp
- detail page location/department tags -> `location` and `team`

## Notes

- Teamtailor has an official JSON API, but it requires an API token and should not be used for public crawling unless explicitly authorized.
- RSS is public and simple but may be less complete than the job detail page.
- Custom domains may still expose `/jobs.rss`; if not, discover the RSS link from the career page HTML.
