# Personio Public Job Retrieval

## When To Use

Use this connector when the company careers page is on:

```text
https://{company_slug}.jobs.personio.com
```

The `company_slug` is the subdomain before `.jobs.personio.com`.

## Listing Feed

```http
GET https://{company_slug}.jobs.personio.com/xml?language=en
```

The `language` parameter controls localized output. Common values are `en`, `de`, `nl`, and other enabled career-site languages.

## Example

```bash
curl 'https://personio.jobs.personio.com/xml?language=en'
```

## Response Shape

The response is XML. The root element is commonly:

```xml
<workzag-jobs>
  <position>
    <id>...</id>
    <name>...</name>
    <office>...</office>
    <department>...</department>
    <recruitingCategory>...</recruitingCategory>
    <employmentType>...</employmentType>
    <schedule>...</schedule>
    <jobDescriptions>
      <jobDescription>
        <name>...</name>
        <value><![CDATA[...]]></value>
      </jobDescription>
    </jobDescriptions>
  </position>
</workzag-jobs>
```

## Detail Retrieval

The XML feed is usually the primary data source and often includes description sections. If the feed is incomplete, fetch the public job page linked in the XML, if present.

## Fields To Normalize

- `position/id` -> `job_id`
- `position/name` -> `job_title`
- `position/department` -> `team`
- `position/office` -> `location`
- `position/employmentType` -> `employment_type`
- `position/schedule` -> schedule metadata
- `position/jobDescriptions/jobDescription/value` -> `description`
- public job URL field, if present -> `job_url`

## Multi-Language Handling

If language coverage matters, fetch all known enabled languages and deduplicate by `position/id`.

## Notes

- No authentication is required when the XML feed is enabled.
- Some Personio tenants may not expose the XML feed or may expose only selected languages.
- Store raw XML in addition to normalized jobs.
