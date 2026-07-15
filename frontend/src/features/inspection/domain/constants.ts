export const MISSING_VALUE = "__missing__";
export const PAGE_SIZE = 50;

export const workflowOptions = ["inspect", "shortlist", "outreach", "closed", "rejected"] as const;
export type Workflow = (typeof workflowOptions)[number];

export const workflowLabels: Record<Workflow, string> = {
  inspect: "Inspect",
  shortlist: "Shortlist",
  outreach: "Outreach",
  closed: "Closed",
  rejected: "Rejected",
};

export const fitStatusOptions = ["unreviewed", "best_fit", "possible_fit", "not_interesting"] as const;
export type FitStatus = (typeof fitStatusOptions)[number];

export const outreachStatusOptions = [
  "not_started",
  "message_sent",
  "follow_up_sent",
  "active_conversation",
  "closed",
  "lost_client_rejection",
  "lost_no_response",
] as const;
export type OutreachStatus = (typeof outreachStatusOptions)[number];

export const sortFields = [
  "job_description_extract_count",
  "job_count",
  "company",
  "fit_status",
  "outreach_status",
  "company_type",
  "company_size",
  "ai_tech_forward_signal",
  "countries",
  "sources",
] as const;
export type SortField = (typeof sortFields)[number];
export type SortDirection = "asc" | "desc";

export const sortLabels: Record<SortField, string> = {
  job_description_extract_count: "JD Extracts",
  job_count: "Jobs",
  company: "Company",
  fit_status: "Fit Status",
  outreach_status: "Outreach Status",
  company_type: "Company Type",
  company_size: "Company Size",
  ai_tech_forward_signal: "AI Signal",
  countries: "Countries",
  sources: "Sources",
};

export const fitStatusLabels: Record<FitStatus, string> = {
  unreviewed: "Unreviewed",
  best_fit: "Best fit",
  possible_fit: "Possible fit",
  not_interesting: "Not interesting",
};

export const outreachStatusLabels: Record<OutreachStatus, string> = {
  not_started: "Not started",
  message_sent: "Message sent",
  follow_up_sent: "Follow-up sent",
  active_conversation: "Active conversation",
  closed: "Closed",
  lost_client_rejection: "Lost: client rejection",
  lost_no_response: "Lost: no response",
};

export const followUpLabels: Record<string, string> = {
  "": "",
  fresh: "Fresh",
  due_soon: "Due soon",
  follow_up: "Follow up",
  date_missing: "Date missing",
  invalid_date: "Invalid date",
};

export function isWorkflow(value: string | null): value is Workflow {
  return workflowOptions.includes(value as Workflow);
}

export function isSortField(value: string | null): value is SortField {
  return sortFields.includes(value as SortField);
}

export function isSortDirection(value: string | null): value is SortDirection {
  return value === "asc" || value === "desc";
}
