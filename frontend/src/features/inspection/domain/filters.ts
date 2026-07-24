import { MISSING_VALUE, type SortDirection, type SortField, isSortDirection, isSortField, isWorkflow, PAGE_SIZE, type Workflow } from "./constants";

export type InspectionFilters = {
  workplace_modes: string[];
  ai_team_contexts: string[];
  delivery_contexts: string[];
  company_types: string[];
  company_sizes: string[];
  min_jobs: number | null;
  max_jobs: number | null;
  countries: string[];
  role_classifications: string[];
  sources: string[];
  ai_tech_forward_signals: string[];
  fit_statuses: string[];
  outreach_statuses: string[];
  has_contacts: boolean | null;
  has_job_description_extracts: boolean | null;
  has_company_enrichment: boolean | null;
  starred_only: boolean;
  search: string;
};

export type InspectionUrlState = {
  filters: InspectionFilters;
  workflow: Workflow;
  sortField: SortField;
  sortDirection: SortDirection;
  page: number;
  selectedCompanyKey: string;
};

export const emptyFilters: InspectionFilters = {
  workplace_modes: [],
  ai_team_contexts: [],
  delivery_contexts: [],
  company_types: [],
  company_sizes: [],
  min_jobs: null,
  max_jobs: null,
  countries: [],
  role_classifications: [],
  sources: [],
  ai_tech_forward_signals: [],
  fit_statuses: [],
  outreach_statuses: [],
  has_contacts: null,
  has_job_description_extracts: null,
  has_company_enrichment: null,
  starred_only: false,
  search: "",
};

const multiKeys = [
  "workplace_modes",
  "ai_team_contexts",
  "delivery_contexts",
  "company_types",
  "company_sizes",
  "countries",
  "role_classifications",
  "sources",
  "ai_tech_forward_signals",
  "fit_statuses",
  "outreach_statuses",
] as const;

const booleanKeys = ["has_contacts", "has_job_description_extracts", "has_company_enrichment"] as const;

export function filtersForQuery(filters: InspectionFilters): InspectionFilters {
  const normalized: InspectionFilters = { ...filters };
  for (const key of multiKeys) {
    normalized[key] = [...new Set(filters[key].filter(Boolean))].sort();
  }
  normalized.search = filters.search.trim();
  return normalized;
}

export function parseUrlState(searchParams: URLSearchParams): InspectionUrlState {
  const filters: InspectionFilters = { ...emptyFilters };

  for (const key of multiKeys) {
    filters[key] = searchParams.getAll(key).filter(Boolean);
  }

  filters.min_jobs = parseNullableNumber(searchParams.get("min_jobs"));
  filters.max_jobs = parseNullableNumber(searchParams.get("max_jobs"));
  filters.search = searchParams.get("search") ?? "";
  filters.starred_only = searchParams.get("starred_only") === "true";

  for (const key of booleanKeys) {
    filters[key] = parseNullableBoolean(searchParams.get(key));
  }

  const workflowParam = searchParams.get("workflow");
  const sortParam = searchParams.get("sort");
  const directionParam = searchParams.get("direction");
  const pageParam = Number(searchParams.get("page") ?? "1");

  return {
    filters,
    workflow: isWorkflow(workflowParam) ? workflowParam : "inspect",
    sortField: isSortField(sortParam) ? sortParam : "job_description_extract_count",
    sortDirection: isSortDirection(directionParam) ? directionParam : "desc",
    page: Number.isFinite(pageParam) && pageParam > 0 ? Math.floor(pageParam) : 1,
    selectedCompanyKey: searchParams.get("company") ?? "",
  };
}

export function buildSearchParams(state: InspectionUrlState): URLSearchParams {
  const params = new URLSearchParams();
  if (state.workflow !== "inspect") params.set("workflow", state.workflow);
  if (state.sortField !== "job_description_extract_count") params.set("sort", state.sortField);
  if (state.sortDirection !== "desc") params.set("direction", state.sortDirection);
  if (state.page > 1) params.set("page", String(state.page));
  if (state.selectedCompanyKey) params.set("company", state.selectedCompanyKey);

  for (const key of multiKeys) {
    for (const value of state.filters[key]) params.append(key, value);
  }
  if (state.filters.min_jobs !== null) params.set("min_jobs", String(state.filters.min_jobs));
  if (state.filters.max_jobs !== null) params.set("max_jobs", String(state.filters.max_jobs));
  if (state.filters.search.trim()) params.set("search", state.filters.search.trim());
  if (state.filters.starred_only) params.set("starred_only", "true");
  for (const key of booleanKeys) {
    if (state.filters[key] !== null) params.set(key, String(state.filters[key]));
  }
  return params;
}

export function optionLabel(value: string) {
  return value === MISSING_VALUE ? "(missing)" : value;
}

export { PAGE_SIZE };

function parseNullableNumber(value: string | null) {
  if (!value) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function parseNullableBoolean(value: string | null) {
  if (value === "true") return true;
  if (value === "false") return false;
  return null;
}
