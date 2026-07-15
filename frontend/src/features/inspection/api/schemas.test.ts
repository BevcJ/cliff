import { describe, expect, it } from "vitest";

import { companyDetailSchema } from "./schemas";

const detailPayload = {
  company_key: "acme ai",
  company: "Acme AI",
  job_count: 1,
  job_description_extract_count: 0,
  has_contacts: false,
  has_job_description_extracts: false,
  has_company_enrichment: false,
  fit_status: "unreviewed",
  outreach_status: "not_started",
  last_outreach_date: null,
  has_review_state: false,
  workflow: "inspect",
  follow_up_status: "",
};

describe("companyDetailSchema", () => {
  it("normalizes omitted nullable company facts to null", () => {
    const result = companyDetailSchema.parse(detailPayload);

    expect(result).toMatchObject({
      role_classification: null,
      company_type: null,
      company_size: null,
      ai_tech_forward_signal: null,
    });
  });

  it("accepts a missing company size alongside populated enrichment facts", () => {
    const result = companyDetailSchema.parse({
      ...detailPayload,
      role_classification: "AI Execution Role",
      company_type: "ai_native",
      ai_tech_forward_signal: "strong",
    });

    expect(result.company_size).toBeNull();
    expect(result.company_type).toBe("ai_native");
    expect(result.ai_tech_forward_signal).toBe("strong");
  });
});
