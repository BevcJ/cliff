import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { CompanyDetail } from "../api/schemas";
import { CompanyDetailDrawer } from "./company-detail-drawer";

const company: CompanyDetail = {
  company_key: "acme ai",
  company: "Acme AI",
  countries: ["Netherlands"],
  role_classification: "AI Execution Role",
  sources: ["lever"],
  workplace_modes: ["remote"],
  ai_team_contexts: ["existing_ai_team"],
  delivery_contexts: ["internal"],
  company_type: "ai_native",
  company_size: "51-100",
  ai_tech_forward_signal: "strong",
  job_count: 2,
  job_description_extract_count: 2,
  has_contacts: true,
  has_job_description_extracts: true,
  has_company_enrichment: true,
  fit_status: "unreviewed",
  outreach_status: "not_started",
  last_outreach_date: null,
  has_review_state: false,
  workflow: "inspect",
  follow_up_status: "",
  review_notes: "",
  review_communication_history: "",
  jobs: [
    { job_title_raw: "AI Engineer" },
    { job_title_raw: "Machine Learning Lead" },
  ],
  company_contacts: [],
  contacts: [
    {
      name: "Ada Lovelace",
      title: "VP Engineering",
      linkedin_url: "https://www.linkedin.com/in/ada-lovelace",
    },
  ],
  company_source_urls: [],
  evidence_urls: [],
};

describe("CompanyDetailDrawer", () => {
  it("shows aggregate contacts and their LinkedIn profiles before every job posting", () => {
    render(
      <CompanyDetailDrawer
        open
        company={company}
        loading={false}
        error={null}
        saving={false}
        onOpenChange={vi.fn()}
        onSaveNotes={vi.fn()}
      />,
    );

    expect(screen.getByText("Ada Lovelace")).toBeInTheDocument();
    expect(screen.getByText("AI Engineer")).toBeInTheDocument();
    expect(screen.getByText("Machine Learning Lead")).toBeInTheDocument();

    const linkedinLink = screen.getByRole("link", { name: "LinkedIn profile" });
    expect(linkedinLink).toHaveAttribute("href", "https://www.linkedin.com/in/ada-lovelace");
    expect(linkedinLink).toHaveAttribute("target", "_blank");

    const contactsHeading = screen.getByRole("heading", { name: "Contacts" });
    const jobsHeading = screen.getByRole("heading", { name: "Jobs" });
    expect(contactsHeading.compareDocumentPosition(jobsHeading)).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
  });
});
