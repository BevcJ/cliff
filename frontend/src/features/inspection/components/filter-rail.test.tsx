import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { FilterOptions } from "../api/schemas";
import { emptyFilters } from "../domain/filters";
import { FilterRail } from "./filter-rail";

const options: FilterOptions = {
  workplace_modes: [],
  has_missing_workplace_modes: false,
  ai_team_contexts: [],
  has_missing_ai_team_contexts: false,
  delivery_contexts: [],
  has_missing_delivery_contexts: false,
  company_types: [],
  has_missing_company_types: false,
  company_sizes: [],
  has_missing_company_sizes: false,
  countries: ["Japan", "Latvia", "Lithuania"],
  has_missing_countries: true,
  role_classifications: [],
  has_missing_role_classifications: false,
  sources: ["ashby", "lever"],
  has_missing_sources: false,
  ai_tech_forward_signals: [],
  has_missing_ai_tech_forward_signals: false,
};

describe("FilterRail", () => {
  it("uses searchable click-to-toggle multi-select filters", async () => {
    const onChange = vi.fn();
    render(<FilterRail filters={emptyFilters} options={options} onChange={onChange} />);

    await userEvent.click(screen.getByRole("combobox", { name: "Countries filter" }));
    await userEvent.type(screen.getByPlaceholderText("Search countries"), "jap");
    await userEvent.click(screen.getByRole("button", { name: /Japan/ }));

    expect(onChange).toHaveBeenCalledWith({ ...emptyFilters, countries: ["Japan"] });
  });

  it("debounces search text updates", async () => {
    const onChange = vi.fn();
    render(<FilterRail filters={emptyFilters} options={options} onChange={onChange} />);

    await userEvent.type(screen.getByPlaceholderText("Search"), "ai");

    await waitFor(() => expect(onChange).toHaveBeenCalledWith({ ...emptyFilters, search: "ai" }));
  });

  it("enables the Starred-only filter", async () => {
    const onChange = vi.fn();
    render(<FilterRail filters={emptyFilters} options={options} onChange={onChange} />);

    await userEvent.click(screen.getByRole("checkbox", { name: "Starred only" }));

    expect(onChange).toHaveBeenCalledWith({ ...emptyFilters, starred_only: true });
  });
});
