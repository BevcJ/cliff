import { format } from "date-fns";
import { flexRender, getCoreRowModel, useReactTable, type ColumnDef } from "@tanstack/react-table";
import { ArrowDown, ArrowUp, CalendarIcon, X } from "lucide-react";
import type { MouseEvent } from "react";
import { useState } from "react";

import { Button } from "../../../components/ui/button";
import { Calendar } from "../../../components/ui/calendar";
import { Popover, PopoverAnchor, PopoverContent, PopoverTrigger } from "../../../components/ui/popover";
import { cn } from "../../../lib/utils";
import type { CompanySummary } from "../api/schemas";
import { fitStatusLabels, fitStatusOptions, outreachStatusLabels, outreachStatusOptions, sortLabels, type FitStatus, type OutreachStatus, type SortDirection, type SortField } from "../domain/constants";
import { FollowUpBadge } from "./status-badges";

type CompanyTableProps = {
  rows: CompanySummary[];
  selectedCompanyKey: string;
  sortField: SortField;
  sortDirection: SortDirection;
  page: number;
  total: number;
  pageSize: number;
  savingCompanyKey: string | null;
  onSelect: (companyKey: string) => void;
  onSort: (field: SortField) => void;
  onPageChange: (page: number) => void;
  onStatusChange: (row: CompanySummary, fitStatus: FitStatus, outreachStatus: OutreachStatus) => void;
  onStatusWithLastOutreachChange: (row: CompanySummary, fitStatus: FitStatus, outreachStatus: "message_sent" | "follow_up_sent", lastOutreachDate: string) => void;
  onLastOutreachChange: (row: CompanySummary, lastOutreachDate: string | null) => void;
};

export function CompanyTable({
  rows,
  selectedCompanyKey,
  sortField,
  sortDirection,
  page,
  total,
  pageSize,
  savingCompanyKey,
  onSelect,
  onSort,
  onPageChange,
  onStatusChange,
  onStatusWithLastOutreachChange,
  onLastOutreachChange,
}: CompanyTableProps) {
  const columns: ColumnDef<CompanySummary>[] = [
    {
      accessorKey: "company",
      size: 230,
      header: () => <SortHeader field="company" label="Company" onSort={onSort} sortDirection={sortDirection} sortField={sortField} />,
      cell: ({ row }) => <span className="font-medium">{row.original.company}</span>,
    },
    {
      accessorKey: "follow_up_status",
      size: 125,
      header: "Follow-up",
      cell: ({ row }) => <FollowUpBadge status={row.original.follow_up_status} />,
    },
    {
      accessorKey: "fit_status",
      size: 170,
      header: () => <SortHeader field="fit_status" label="Fit Status" onSort={onSort} sortDirection={sortDirection} sortField={sortField} />,
      cell: ({ row }) => (
        <select
          data-row-control
          aria-label={`Fit status for ${row.original.company}`}
          className="h-8 w-full min-w-0 rounded-full border border-input bg-white px-2 text-xs"
          disabled={savingCompanyKey === row.original.company_key}
          value={row.original.fit_status}
          onChange={(event) => onStatusChange(row.original, event.target.value as FitStatus, row.original.outreach_status)}
        >
          {fitStatusOptions.map((status) => (
            <option key={status} value={status}>
              {fitStatusLabels[status]}
            </option>
          ))}
        </select>
      ),
    },
    {
      accessorKey: "outreach_status",
      size: 200,
      header: () => <SortHeader field="outreach_status" label="Outreach Status" onSort={onSort} sortDirection={sortDirection} sortField={sortField} />,
      cell: ({ row }) => <OutreachStatusEditor disabled={savingCompanyKey === row.original.company_key} row={row.original} onStatusChange={onStatusChange} onStatusWithLastOutreachChange={onStatusWithLastOutreachChange} />,
    },
    {
      accessorKey: "last_outreach_date",
      size: 170,
      header: "Last Outreach",
      cell: ({ row }) => <LastOutreachPicker disabled={savingCompanyKey === row.original.company_key} value={row.original.last_outreach_date} onChange={(value) => onLastOutreachChange(row.original, value)} />,
    },
    { accessorKey: "job_count", size: 70, header: () => <SortHeader field="job_count" label="Jobs" onSort={onSort} sortDirection={sortDirection} sortField={sortField} /> },
    { accessorKey: "job_description_extract_count", size: 100, header: () => <SortHeader field="job_description_extract_count" label="JD Extracts" onSort={onSort} sortDirection={sortDirection} sortField={sortField} /> },
    { accessorKey: "countries", size: 280, header: () => <SortHeader field="countries" label="Countries" onSort={onSort} sortDirection={sortDirection} sortField={sortField} />, cell: ({ row }) => row.original.countries.join(", ") },
    { accessorKey: "role_classification", size: 170, header: "Role Classification" },
    { accessorKey: "workplace_modes", size: 170, header: "Workplace", cell: ({ row }) => row.original.workplace_modes.join(", ") },
    { accessorKey: "ai_team_contexts", size: 170, header: "AI Team", cell: ({ row }) => row.original.ai_team_contexts.join(", ") },
    { accessorKey: "delivery_contexts", size: 170, header: "Delivery", cell: ({ row }) => row.original.delivery_contexts.join(", ") },
    { accessorKey: "company_type", size: 175, header: () => <SortHeader field="company_type" label="Company Type" onSort={onSort} sortDirection={sortDirection} sortField={sortField} /> },
    { accessorKey: "company_size", size: 125, header: () => <SortHeader field="company_size" label="Company Size" onSort={onSort} sortDirection={sortDirection} sortField={sortField} /> },
    { accessorKey: "ai_tech_forward_signal", size: 120, header: () => <SortHeader field="ai_tech_forward_signal" label="AI Signal" onSort={onSort} sortDirection={sortDirection} sortField={sortField} /> },
    { accessorKey: "sources", size: 180, header: () => <SortHeader field="sources" label="Sources" onSort={onSort} sortDirection={sortDirection} sortField={sortField} />, cell: ({ row }) => row.original.sources.join(", ") },
    { accessorKey: "has_contacts", size: 120, header: "Has Contacts", cell: ({ row }) => (row.original.has_contacts ? "Yes" : "No") },
  ];

  const table = useReactTable({ data: rows, columns, getCoreRowModel: getCoreRowModel(), manualPagination: true, manualSorting: true });
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const tableWidth = table.getTotalSize();

  return (
    <div className="rounded-xl border bg-white">
      <div className="overflow-x-auto">
        <table className="table-fixed border-collapse text-sm" style={{ width: tableWidth }}>
          <colgroup>
            {table.getAllLeafColumns().map((column) => (
              <col key={column.id} style={{ width: column.getSize() }} />
            ))}
          </colgroup>
          <thead>
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id} className="border-b bg-secondary text-left text-xs uppercase tracking-wide text-muted-foreground">
                {headerGroup.headers.map((header) => (
                  <th key={header.id} className={cellClass(header.column.id, "px-3 py-2 font-semibold", true)} style={{ width: header.getSize() }}>{flexRender(header.column.columnDef.header, header.getContext())}</th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map((row) => (
              <tr
                key={row.original.company_key}
                data-selected={selectedCompanyKey === row.original.company_key ? "true" : undefined}
                className={selectedCompanyKey === row.original.company_key ? "group border-b bg-accent" : "group border-b bg-white hover:bg-secondary"}
                onClick={(event) => {
                  if (isRowControlClick(event)) return;
                  onSelect(row.original.company_key);
                }}
              >
                {row.getVisibleCells().map((cell) => {
                  const controlCell = isControlColumn(cell.column.id);
                  return (
                    <td key={cell.id} className={cellClass(cell.column.id, cn("px-3 py-2 align-middle", !controlCell && "truncate"))} style={{ width: cell.column.getSize() }}>
                      <div className={controlCell ? "min-w-0" : "truncate"}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</div>
                    </td>
                  );
                })}
              </tr>
            ))}
            {rows.length === 0 ? (
              <tr>
                <td className="px-3 py-10 text-center text-muted-foreground" colSpan={columns.length}>
                  No companies match the current filters.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
      <div className="flex items-center justify-between border-t px-4 py-3 text-sm">
        <div className="text-muted-foreground">
          Page {page} of {totalPages} ({total} companies)
        </div>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" disabled={page <= 1} onClick={() => onPageChange(page - 1)}>
            Previous
          </Button>
          <Button size="sm" variant="outline" disabled={page >= totalPages} onClick={() => onPageChange(page + 1)}>
            Next
          </Button>
        </div>
      </div>
    </div>
  );
}

function SortHeader({ field, label, sortField, sortDirection, onSort }: { field: SortField; label: string; sortField: SortField; sortDirection: SortDirection; onSort: (field: SortField) => void }) {
  const active = sortField === field;
  return (
    <button className="inline-flex items-center gap-1" type="button" onClick={() => onSort(field)} title={`Sort by ${sortLabels[field]}`}>
      {label}
      {active ? sortDirection === "asc" ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" /> : null}
    </button>
  );
}

function LastOutreachPicker({ disabled, value, onChange }: { disabled: boolean; value: string | null; onChange: (value: string | null) => void }) {
  const [open, setOpen] = useState(false);
  const selectedDate = parseIsoDate(value);
  const today = new Date();

  return (
    <div className="w-full min-w-0" data-row-control onClick={(event) => event.stopPropagation()}>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button aria-label="Edit Last Outreach" className="h-8 w-full min-w-0 justify-start px-2 text-xs font-normal" disabled={disabled} variant="outline">
            <CalendarIcon className="mr-2 h-3.5 w-3.5" />
            {selectedDate ? format(selectedDate, "MM/dd/yyyy") : "Set date"}
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-auto p-0" align="start">
          <Calendar
            mode="single"
            selected={selectedDate}
            disabled={{ after: today }}
            onSelect={(date) => {
              if (!date) return;
              onChange(format(date, "yyyy-MM-dd"));
              setOpen(false);
            }}
          />
          <div className="flex items-center justify-between border-t p-2">
            <Button size="sm" variant="ghost" onClick={() => {
              onChange(null);
              setOpen(false);
            }}>
              <X className="mr-1 h-3.5 w-3.5" /> Clear
            </Button>
            <span className="text-xs text-muted-foreground">Future dates disabled</span>
          </div>
        </PopoverContent>
      </Popover>
    </div>
  );
}

function OutreachStatusEditor({
  disabled,
  row,
  onStatusChange,
  onStatusWithLastOutreachChange,
}: {
  disabled: boolean;
  row: CompanySummary;
  onStatusChange: (row: CompanySummary, fitStatus: FitStatus, outreachStatus: OutreachStatus) => void;
  onStatusWithLastOutreachChange: (row: CompanySummary, fitStatus: FitStatus, outreachStatus: "message_sent" | "follow_up_sent", lastOutreachDate: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [pendingStatus, setPendingStatus] = useState<"message_sent" | "follow_up_sent" | null>(null);
  const [selectedDateIso, setSelectedDateIso] = useState(todayIsoDate());
  const selectedDate = parseIsoDate(selectedDateIso);
  const today = new Date();

  function handleChange(nextStatus: OutreachStatus) {
    if (isOutboundStatus(nextStatus)) {
      setPendingStatus(nextStatus);
      setSelectedDateIso(todayIsoDate());
      setOpen(true);
      return;
    }
    onStatusChange(row, row.fit_status, nextStatus);
  }

  function confirm() {
    if (!pendingStatus) return;
    onStatusWithLastOutreachChange(row, row.fit_status, pendingStatus, selectedDateIso);
    setOpen(false);
    setPendingStatus(null);
  }

  function cancel() {
    setOpen(false);
    setPendingStatus(null);
    setSelectedDateIso(todayIsoDate());
  }

  return (
    <div className="w-full min-w-0" data-row-control onClick={(event) => event.stopPropagation()}>
      <Popover
        open={open}
        onOpenChange={(nextOpen) => {
          if (!nextOpen) cancel();
        }}
      >
        <PopoverAnchor asChild>
          <select
            data-row-control
            aria-label={`Outreach status for ${row.company}`}
            className="h-8 w-full min-w-0 rounded-full border border-input bg-white px-2 text-xs"
            disabled={disabled}
            value={row.outreach_status}
            onChange={(event) => handleChange(event.target.value as OutreachStatus)}
          >
            {outreachStatusOptions.map((status) => (
              <option key={status} value={status}>
                {outreachStatusLabels[status]}
              </option>
            ))}
          </select>
        </PopoverAnchor>
        <PopoverContent className="w-auto p-0" align="start">
          <div className="border-b px-3 py-2 text-sm font-medium">
            Confirm {pendingStatus ? outreachStatusLabels[pendingStatus].toLowerCase() : "outreach"} date
          </div>
          <Calendar
            mode="single"
            selected={selectedDate}
            disabled={{ after: today }}
            onSelect={(date) => {
              if (!date) return;
              setSelectedDateIso(format(date, "yyyy-MM-dd"));
            }}
          />
          <div className="flex items-center justify-between gap-2 border-t p-2">
            <Button size="sm" variant="ghost" onClick={cancel}>
              Cancel
            </Button>
            <Button size="sm" onClick={confirm}>
              Save {format(parseIsoDate(selectedDateIso) ?? new Date(), "MM/dd/yyyy")}
            </Button>
          </div>
        </PopoverContent>
      </Popover>
    </div>
  );
}

function parseIsoDate(value: string | null) {
  if (!value) return undefined;
  const date = new Date(`${value}T00:00:00`);
  return Number.isNaN(date.getTime()) ? undefined : date;
}

function todayIsoDate() {
  return format(new Date(), "yyyy-MM-dd");
}

function isOutboundStatus(status: OutreachStatus): status is "message_sent" | "follow_up_sent" {
  return status === "message_sent" || status === "follow_up_sent";
}

function isRowControlClick(event: MouseEvent<HTMLTableRowElement>) {
  return Boolean((event.target as HTMLElement | null)?.closest("[data-row-control]"));
}

function isControlColumn(columnId: string) {
  return columnId === "fit_status" || columnId === "outreach_status" || columnId === "last_outreach_date";
}

function cellClass(columnId: string, className: string, header = false) {
  if (columnId !== "company") return className;
  return cn(
    className,
    "sticky left-0 z-20 shadow-[1px_0_0_hsl(var(--border))]",
    header ? "bg-secondary" : "bg-white group-hover:bg-secondary group-data-[selected=true]:bg-accent",
  );
}
