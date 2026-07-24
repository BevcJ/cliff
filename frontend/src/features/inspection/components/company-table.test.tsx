import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { CompanySummary } from "../api/schemas";
import { CompanyTable } from "./company-table";

const row: CompanySummary = {
  collection_date: "2026-07-03",
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
  job_count: 3,
  job_description_extract_count: 2,
  has_contacts: true,
  has_job_description_extracts: true,
  has_company_enrichment: true,
  fit_status: "unreviewed",
  outreach_status: "not_started",
  last_outreach_date: null,
  is_starred: false,
  has_review_state: false,
  workflow: "inspect",
  follow_up_status: "",
};

describe("CompanyTable", () => {
  it("opens the detail drawer only from non-interactive cells", async () => {
    const onSelect = vi.fn();
    renderTable({ onSelect });

    await userEvent.click(screen.getByText("Acme AI"));
    expect(onSelect).toHaveBeenCalledWith("acme ai");
  });

  it("does not open the drawer when editing status or Last Outreach", async () => {
    const onSelect = vi.fn();
    const onStatusChange = vi.fn();
    renderTable({ onSelect, onStatusChange });

    await userEvent.selectOptions(screen.getByLabelText("Fit status for Acme AI"), "possible_fit");
    await userEvent.click(screen.getByRole("button", { name: "Edit Last Outreach" }));

    expect(onStatusChange).toHaveBeenCalledWith(row, "possible_fit", "not_started");
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("stars a company without opening the detail drawer", async () => {
    const onSelect = vi.fn();
    const onStarChange = vi.fn();
    renderTable({ onSelect, onStarChange });

    await userEvent.click(screen.getByRole("button", { name: "Star Acme AI" }));

    expect(onStarChange).toHaveBeenCalledWith(row, true);
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("shows and disables the active star while the company is saving", () => {
    renderTable({ rows: [{ ...row, is_starred: true }], savingCompanyKey: row.company_key });

    const button = screen.getByRole("button", { name: "Unstar Acme AI" });
    expect(button).toHaveAttribute("aria-pressed", "true");
    expect(button).toBeDisabled();
  });

  it("requires date confirmation before saving outbound outreach statuses", async () => {
    const onStatusChange = vi.fn();
    const onStatusWithLastOutreachChange = vi.fn();
    renderTable({ onStatusChange, onStatusWithLastOutreachChange });

    await userEvent.selectOptions(screen.getByLabelText("Outreach status for Acme AI"), "message_sent");

    expect(screen.getByText("Confirm message sent date")).toBeInTheDocument();
    expect(onStatusChange).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("button", { name: /Save/ }));

    expect(onStatusWithLastOutreachChange).toHaveBeenCalledWith(row, "unreviewed", "message_sent", expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/));
  });

  it("cancels outbound status confirmation without saving", async () => {
    const onStatusWithLastOutreachChange = vi.fn();
    renderTable({ onStatusWithLastOutreachChange });

    await userEvent.selectOptions(screen.getByLabelText("Outreach status for Acme AI"), "follow_up_sent");
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(onStatusWithLastOutreachChange).not.toHaveBeenCalled();
  });

  it("does not allow Last Outreach to be cleared while the company is outbound", async () => {
    renderTable({ rows: [{ ...row, outreach_status: "message_sent", last_outreach_date: "2026-07-03" }] });

    await userEvent.click(screen.getByRole("button", { name: "Edit Last Outreach" }));

    expect(screen.queryByRole("button", { name: /Clear/ })).not.toBeInTheDocument();
    expect(screen.getByText("Date required while outbound")).toBeInTheDocument();
  });
});

function renderTable(overrides: Partial<React.ComponentProps<typeof CompanyTable>> = {}) {
  return render(
    <CompanyTable
      rows={[row]}
      selectedCompanyKey=""
      sortField="job_description_extract_count"
      sortDirection="desc"
      page={1}
      total={1}
      pageSize={50}
      savingCompanyKey={null}
      onSelect={vi.fn()}
      onSort={vi.fn()}
      onPageChange={vi.fn()}
      onStarChange={vi.fn()}
      onStatusChange={vi.fn()}
      onStatusWithLastOutreachChange={vi.fn()}
      onLastOutreachChange={vi.fn()}
      {...overrides}
    />,
  );
}
