import { describe, expect, it } from "vitest";

import { MISSING_VALUE } from "./constants";
import { buildSearchParams, emptyFilters, filtersForQuery, parseUrlState } from "./filters";

describe("inspection URL state", () => {
  it("parses repeated filter values, booleans, sorting, page, and selection", () => {
    const params = new URLSearchParams();
    params.append("countries", "Netherlands");
    params.append("countries", MISSING_VALUE);
    params.set("has_contacts", "true");
    params.set("workflow", "outreach");
    params.set("sort", "job_count");
    params.set("direction", "asc");
    params.set("page", "3");
    params.set("company", "acme ai");

    const state = parseUrlState(params);

    expect(state.filters.countries).toEqual(["Netherlands", MISSING_VALUE]);
    expect(state.filters.has_contacts).toBe(true);
    expect(state.workflow).toBe("outreach");
    expect(state.sortField).toBe("job_count");
    expect(state.sortDirection).toBe("asc");
    expect(state.page).toBe(3);
    expect(state.selectedCompanyKey).toBe("acme ai");
  });

  it("round-trips compact default-free search params", () => {
    const params = buildSearchParams({
      filters: { ...emptyFilters, search: " tooling ", countries: ["Netherlands"] },
      workflow: "inspect",
      sortField: "job_description_extract_count",
      sortDirection: "desc",
      page: 1,
      selectedCompanyKey: "",
    });

    expect(params.toString()).toBe("countries=Netherlands&search=tooling");
  });

  it("normalizes filter query keys for stable TanStack Query caching", () => {
    expect(filtersForQuery({ ...emptyFilters, sources: ["lever", "ashby", "lever"] }).sources).toEqual(["ashby", "lever"]);
  });
});
