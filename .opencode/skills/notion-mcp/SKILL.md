---
name: notion-mcp
description: >
  Practical guide for agents using the Notion MCP server integration.
  Covers fetching schema, creating/updating pages in databases, setting relations,
  and formatting content. Learned from real-world usage across Tasks, Epics, etc.
---

# Notion MCP — Practical Guide

## Golden Rule

**Always fetch first.** Before creating pages or updating properties, `fetch` the
 target database/page to read its exact schema, data source URLs, and property types.
 Every database has different column names, relation targets, and status options.

## Discovery

The entities that are commonly used can be found using the following DB/collection IDs:

| Entity | URL / ID | Data Source | Notes |
|--------|-----------|-------------|-------|
| **Epics DB** | `https://www.notion.so/408eebe549794e59bbae6a6c20e82256` | `collection://6fe30f98-6985-4980-b544-2c8698cb5454` | Parent of all epics |
| **Tasks DB** | `https://www.notion.so/f30c7f097eeb43dfa18c8e4c5aac8808` | `collection://e053c5dd-157c-4970-83f2-14bc293bc12b` | Where work items live |
| **Sprints DB** | `https://www.notion.so/8b9acd2460f6453a81ffea5ddaa9e77c` | `collection://4c9ce5a5-7cd9-413d-a303-81e23c561aa5` | Sprints live here |

### Find a database by name
```json
{
  "query": "Tasks",
  "query_type": "internal",
  "page_size": 5
}
```

### Get the full schema
```json
{"id": "DATABASE_URL_OR_UUID"}
```

**What to extract from the fetch response:**
- `<data-source url="collection://...">` — used as `data_source_id` for create/update.
- `<sqlite-table>` — column names, types, allowed values for status/select.
- Existing page properties as example values.

## Creating Pages in a Database

### Required `parent`
```json
{"parent": {"data_source_id": "collection://e053c5dd-157c-4970-83f2-14bc293bc12b"}}
```

### Property formats by type

| Type | Format | Example value |
|------|--------|---------------|
| **title** | plain string | `"Task name": "Fix auth"` |
| **status** | option name string | `"Status": "to-do"` |
| **select** | option name string | `"Effort": "XS (≤ 2 hours)"` |
| **multi_select** | comma-separated inside JSON array string | `"Tags": "[\"Mobile\", \"Website\"]"` |
| **people** | JSON array of user IDs as string | `"Assignee": "[{\"id\": \"281d...\"}]"` |
| **relation** | JSON array of **full page URLs** as string | `"⛰️ Epic": "[\"https://app.notion.com/p/388...\"]"` |
| **number** | raw number | `"Priority": 5` |
| **date** | expanded properties | `"date:Due date:start": "2026-06-30"` |
| **checkbox** | `"__YES__"` or `"__NO__"` | `"Done": "__YES__"` |

**Why relations need full URLs:** Notion validates relation values as page URLs.
 Passing bare UUIDs triggers `invalid compressed URL or shorthand identifier`.

### Creating a task with relations
```json
{
  "pages": [
    {
      "properties": {
        "Task name": "Add retry cap",
        "Effort": "XS (≤ 2 hours)",
        "Status": "to-do",
        "Assignee": "[{\"id\": \"281d872b-594c-81ab-8960-00026a1996cc\"}]",
        "Sprint": "[\"https://app.notion.com/p/38961e6824408084818dcdca22a580da\"]",
        "⛰️ Epic": "[\"https://app.notion.com/p/38861e682440807d88b8f0caf4e185ba\"]"
      },
      "content": "Task description in Notion-flavored Markdown."
    }
  ],
  "parent": {"data_source_id": "collection://e053c5dd-157c-4970-83f2-14bc293bc12b"}
}
```

### Self-referential relations (`Blocked by` / `Blocking`)
Set them **after** creation via `update_page`, because the target pages must exist first.

```json
{
  "page_id": "PAGE_UUID",
  "command": "update_properties",
  "properties": {
    "Blocked by": "[\"https://app.notion.com/p/OTHER_PAGE_ID\"]"
  }
}
```

## Updating Existing Pages

### Replace entire body
```json
{
  "page_id": "38861e68-2440-807d-88b8-f0caf4e185ba",
  "command": "replace_content",
  "new_str": "# New content\nRest of doc..."
}
```

### Update specific properties
```json
{
  "page_id": "38861e68-2440-807d-88b8-f0caf4e185ba",
  "command": "update_properties",
  "properties": {
    "Status": "in progress",
    "Blocked by": "[\"https://app.notion.com/p/38f...\"]"
  }
}
```

### Insert at top or bottom
```json
{
  "page_id": "PAGE_UUID",
  "command": "insert_content",
  "content": "## Update\nDetails...",
  "position": {"type": "start"}
}
```

## Querying Data

### Query a specific database view
Use the `view_url` from the fetch response (includes `?v=` param).

```json
{"view_url": "https://notion.so/workspace/Tasks-DB-ID?v=VIEW_ID"}
```

### SQL across data sources
```json
{
  "data": {
    "mode": "sql",
    "data_source_urls": ["collection://e053c5dd-157c-4970-83f2-14bc293bc12b"],
    "query": "SELECT * FROM \"collection://e053c5dd-157c-4970-83f2-14bc293bc12b\" WHERE Status = ? LIMIT 10",
    "params": ["to-do"]
  }
}
```

## Key Gotchas

1. **Arrays in properties must be JSON strings.** The `create_pages` / `update_page`
   properties map only accepts string/number/null values. Pass arrays as
   JSON-stringified text: `"[\"value1\", \"value2\"]"`.

2. **Status vs Select.** Both are plain strings, but status has group logic
   (`to-do`, `in progress`, `done`). Select has no groups.

3. **Never guess column names.** Fetch first — a database may use `Task name`
   as the title, `⛰️ Epic` for the epic relation, or `userDefined:ID` for
   custom IDs. Exact spelling matters.

4. **Title property is the database title column.** It is not literally `"title"`.
   Check the schema for which property has `type: title`.

5. **People values work with just the user ID in a JSON array.** Relations need
   fully qualified `https://app.notion.com/p/...` URLs.

6. **Meeting notes are a separate system.** Use `query_meeting_notes` with filters
   rather than the generic search when looking for meeting data.

## Quick Reference — Property Cheat Sheet

```json
// title
{"Task name": "Do the thing"}

// status
{"Status": "to-do"}

// select
{"Effort": "XS (≤ 2 hours)"}

// multi_select
{"Tags": "[\"Mobile\", \"Website\"]"}

// people (JSON array of objects or bare IDs)
{"Assignee": "[{\"id\": \"281d...\"}]"}

// relation (JSON array of full Notion page URLs)
{"⛰️ Epic": "[\"https://app.notion.com/p/388...\"]"}

// number
{"Priority": 5}

// date (expanded format)
{"date:Due date:start": "2026-06-30", "date:Due date:is_datetime": 0}

// checkbox
{"Done": "__YES__"}
```

## Markdown for Notion Content

When writing page content, read the Notion Markdown spec first:
```
notion://docs/enhanced-markdown-spec
```

Supports headings, tables, code blocks, bold, italic, inline code, links.
Use `<page url="...">` tags to reference child pages so `replace_content`
 does not accidentally orphan them.