import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { WorkflowTabs } from "./workflow-tabs";

describe("WorkflowTabs", () => {
  it("renders workflow counts and emits selected workflow", async () => {
    const onChange = vi.fn();
    render(
      <WorkflowTabs
        value="inspect"
        onChange={onChange}
        counts={{
          total_companies: 3,
          total_jobs: 4,
          total_job_description_extracts: 2,
          with_contacts: 1,
          with_job_description_extracts: 2,
          with_company_enrichment: 3,
          workflows: { inspect: 1, shortlist: 2, outreach: 0, closed: 0, rejected: 0 },
          fit_statuses: {},
          outreach_statuses: {},
        }}
      />,
    );

    expect(screen.getByRole("button", { name: /Inspect\s*1/ })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Shortlist\s*2/ }));

    expect(onChange).toHaveBeenCalledWith("shortlist");
  });
});
