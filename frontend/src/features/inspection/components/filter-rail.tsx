import { Check, ChevronDown, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { Button } from "../../../components/ui/button";
import { Input } from "../../../components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "../../../components/ui/popover";
import { cn } from "../../../lib/utils";
import type { FilterOptions } from "../api/schemas";
import { MISSING_VALUE, fitStatusLabels, fitStatusOptions, outreachStatusLabels, outreachStatusOptions } from "../domain/constants";
import type { InspectionFilters } from "../domain/filters";
import { emptyFilters, optionLabel } from "../domain/filters";

type FilterRailProps = {
  filters: InspectionFilters;
  options: FilterOptions | undefined;
  onChange: (filters: InspectionFilters) => void;
};

export function FilterRail({ filters, options, onChange }: FilterRailProps) {
  function update<K extends keyof InspectionFilters>(key: K, value: InspectionFilters[K]) {
    onChange({ ...filters, [key]: value });
  }

  return (
    <aside className="sticky top-20 max-h-[calc(100vh-6rem)] w-80 shrink-0 overflow-y-auto rounded-xl border bg-white p-4 shadow-sm">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-sm font-semibold">Filters</h2>
        <Button size="sm" variant="ghost" onClick={() => onChange(emptyFilters)}>
          Clear
        </Button>
      </div>
      <div className="space-y-3">
        <FilterText label="Search" value={filters.search} onChange={(value) => update("search", value)} />
        <NumberFilter label="Min jobs" value={filters.min_jobs} onChange={(value) => update("min_jobs", value)} />
        <NumberFilter label="Max jobs" value={filters.max_jobs} onChange={(value) => update("max_jobs", value)} />
        <SearchableMultiFilter label="Countries" values={filters.countries} options={withMissing(options?.countries, options?.has_missing_countries)} onChange={(value) => update("countries", value)} />
        <SearchableMultiFilter label="Sources" values={filters.sources} options={withMissing(options?.sources, options?.has_missing_sources)} onChange={(value) => update("sources", value)} />
        <SearchableMultiFilter label="Company size" values={filters.company_sizes} options={withMissing(options?.company_sizes, options?.has_missing_company_sizes)} onChange={(value) => update("company_sizes", value)} />
        <SearchableMultiFilter label="Company type" values={filters.company_types} options={withMissing(options?.company_types, options?.has_missing_company_types)} onChange={(value) => update("company_types", value)} />
        <SearchableMultiFilter label="Role" values={filters.role_classifications} options={withMissing(options?.role_classifications, options?.has_missing_role_classifications)} onChange={(value) => update("role_classifications", value)} />
        <SearchableMultiFilter label="AI signal" values={filters.ai_tech_forward_signals} options={withMissing(options?.ai_tech_forward_signals, options?.has_missing_ai_tech_forward_signals)} onChange={(value) => update("ai_tech_forward_signals", value)} />
        <SearchableMultiFilter label="Workplace" values={filters.workplace_modes} options={withMissing(options?.workplace_modes, options?.has_missing_workplace_modes)} onChange={(value) => update("workplace_modes", value)} />
        <SearchableMultiFilter label="AI team" values={filters.ai_team_contexts} options={withMissing(options?.ai_team_contexts, options?.has_missing_ai_team_contexts)} onChange={(value) => update("ai_team_contexts", value)} />
        <SearchableMultiFilter label="Delivery" values={filters.delivery_contexts} options={withMissing(options?.delivery_contexts, options?.has_missing_delivery_contexts)} onChange={(value) => update("delivery_contexts", value)} />
        <SearchableMultiFilter label="Fit status" values={filters.fit_statuses} options={fitStatusOptions.map((value) => ({ value, label: fitStatusLabels[value] }))} onChange={(value) => update("fit_statuses", value)} />
        <SearchableMultiFilter label="Outreach" values={filters.outreach_statuses} options={outreachStatusOptions.map((value) => ({ value, label: outreachStatusLabels[value] }))} onChange={(value) => update("outreach_statuses", value)} />
        <BooleanFilter label="Has contacts" value={filters.has_contacts} onChange={(value) => update("has_contacts", value)} />
        <BooleanFilter label="Has JD extracts" value={filters.has_job_description_extracts} onChange={(value) => update("has_job_description_extracts", value)} />
        <BooleanFilter label="Has enrichment" value={filters.has_company_enrichment} onChange={(value) => update("has_company_enrichment", value)} />
      </div>
    </aside>
  );
}

function withMissing(values: string[] | undefined, hasMissing: boolean | undefined) {
  const options = (values ?? []).map((value) => ({ value, label: optionLabel(value) }));
  if (hasMissing) options.push({ value: MISSING_VALUE, label: optionLabel(MISSING_VALUE) });
  return options;
}

function FilterText({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  const [localValue, setLocalValue] = useState(value);

  useEffect(() => {
    setLocalValue(value);
  }, [value]);

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      if (localValue !== value) onChange(localValue);
    }, 300);
    return () => window.clearTimeout(timeout);
  }, [localValue, onChange, value]);

  return (
    <label className="block space-y-1 text-xs font-medium text-muted-foreground">
      <span>{label}</span>
      <Input value={localValue} onChange={(event) => setLocalValue(event.target.value)} placeholder="Search" />
    </label>
  );
}

function NumberFilter({ label, value, onChange }: { label: string; value: number | null; onChange: (value: number | null) => void }) {
  return (
    <label className="block space-y-1 text-xs font-medium text-muted-foreground">
      <span>{label}</span>
      <Input type="number" value={value ?? ""} onChange={(event) => onChange(event.target.value ? Number(event.target.value) : null)} />
    </label>
  );
}

function BooleanFilter({ label, value, onChange }: { label: string; value: boolean | null; onChange: (value: boolean | null) => void }) {
  return (
    <label className="block space-y-1 text-xs font-medium text-muted-foreground">
      <span>{label}</span>
      <select className="h-9 w-full rounded-full border border-input bg-white px-3 text-sm" value={value === null ? "" : String(value)} onChange={(event) => onChange(event.target.value === "" ? null : event.target.value === "true")}>
        <option value="">Any</option>
        <option value="true">Yes</option>
        <option value="false">No</option>
      </select>
    </label>
  );
}

function SearchableMultiFilter({ label, values, options, onChange }: { label: string; values: string[]; options: { value: string; label: string }[]; onChange: (values: string[]) => void }) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const selected = useMemo(() => new Set(values), [values]);
  const filteredOptions = useMemo(() => {
    const needle = search.trim().toLowerCase();
    if (!needle) return options;
    return options.filter((option) => option.label.toLowerCase().includes(needle) || option.value.toLowerCase().includes(needle));
  }, [options, search]);

  function toggle(value: string) {
    if (selected.has(value)) {
      onChange(values.filter((existing) => existing !== value));
      return;
    }
    onChange([...values, value]);
  }

  const triggerLabel = values.length === 0 ? "Any" : values.length === 1 ? optionLabel(options.find((option) => option.value === values[0])?.label ?? values[0]) : `${values.length} selected`;

  return (
    <div className="space-y-1 text-xs font-medium text-muted-foreground">
      <div>{label}</div>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button aria-expanded={open} aria-label={`${label} filter`} className="h-10 w-full justify-between px-3 text-left font-normal" role="combobox" variant="outline">
            <span className={cn("truncate", values.length === 0 && "text-muted-foreground")}>{triggerLabel}</span>
            <ChevronDown className="ml-2 h-4 w-4 shrink-0 opacity-60" />
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-80 p-0">
          <div className="border-b p-2">
            <Input autoFocus value={search} onChange={(event) => setSearch(event.target.value)} placeholder={`Search ${label.toLowerCase()}`} />
          </div>
          {values.length > 0 ? (
            <div className="flex items-center justify-between border-b px-3 py-2 text-xs">
              <span className="text-muted-foreground">{values.length} selected</span>
              <button className="inline-flex items-center gap-1 text-primary hover:underline" type="button" onClick={() => onChange([])}>
                <X className="h-3 w-3" /> Clear
              </button>
            </div>
          ) : null}
          <div className="max-h-72 overflow-y-auto p-1">
            {filteredOptions.length === 0 ? <div className="px-3 py-6 text-center text-sm text-muted-foreground">No options</div> : null}
            {filteredOptions.map((option) => {
              const checked = selected.has(option.value);
              return (
                <button
                  key={option.value}
                  className="flex w-full items-center gap-2 rounded-sm px-2 py-2 text-left text-sm hover:bg-accent"
                  type="button"
                  onClick={() => toggle(option.value)}
                >
                  <span className={cn("flex h-4 w-4 items-center justify-center rounded border", checked ? "border-primary bg-primary text-primary-foreground" : "border-input bg-white")}>
                    {checked ? <Check className="h-3 w-3" /> : null}
                  </span>
                  <span className="truncate">{option.label}</span>
                </button>
              );
            })}
          </div>
        </PopoverContent>
      </Popover>
      {values.length > 0 ? <div className="truncate text-[11px] text-muted-foreground">{values.map((value) => optionLabel(options.find((option) => option.value === value)?.label ?? value)).join(", ")}</div> : null}
    </div>
  );
}
