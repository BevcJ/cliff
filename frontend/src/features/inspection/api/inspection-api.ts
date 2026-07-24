import { z } from "zod";

import { supabase } from "../../../lib/supabase";
import type { InspectionFilters } from "../domain/filters";
import { filtersForQuery } from "../domain/filters";
import type { FitStatus, OutreachStatus, SortDirection, SortField, Workflow } from "../domain/constants";
import {
  collectionSchema,
  companyDetailSchema,
  companyListSchema,
  countsSchema,
  filterOptionsSchema,
  reviewStateSchema,
} from "./schemas";

async function rpc<T>(name: string, args: Record<string, unknown>, schema: z.ZodType<T>) {
  const { data, error } = await supabase.rpc(name as never, args as never);
  if (error) throw new Error(error.message);
  return schema.parse(data);
}

export function listCollections() {
  return rpc("inspection_list_collections", {}, z.array(collectionSchema));
}

export function getFilterOptions(collectionDate: string) {
  return rpc("inspection_get_filter_options", { p_collection_date: collectionDate }, filterOptionsSchema);
}

export function getCounts(collectionDate: string, filters: InspectionFilters) {
  return rpc("inspection_get_counts", { p_collection_date: collectionDate, p_filters: filtersForQuery(filters) }, countsSchema);
}

export function listCompanies(args: {
  collectionDate: string;
  filters: InspectionFilters;
  workflow: Workflow;
  sortField: SortField;
  sortDirection: SortDirection;
  page: number;
  pageSize: number;
}) {
  return rpc(
    "inspection_list_companies",
    {
      p_collection_date: args.collectionDate,
      p_filters: filtersForQuery(args.filters),
      p_workflow: args.workflow,
      p_sort_field: args.sortField,
      p_sort_direction: args.sortDirection,
      p_page: args.page,
      p_page_size: args.pageSize,
    },
    companyListSchema,
  );
}

export function getCompany(collectionDate: string, companyKey: string) {
  return rpc("inspection_get_company", { p_collection_date: collectionDate, p_company_key: companyKey }, companyDetailSchema);
}

export function updateStatus(args: { collectionDate: string; companyKey: string; fitStatus: FitStatus; outreachStatus: OutreachStatus }) {
  return rpc(
    "inspection_update_status",
    {
      p_collection_date: args.collectionDate,
      p_company_key: args.companyKey,
      p_fit_status: args.fitStatus,
      p_outreach_status: args.outreachStatus,
    },
    reviewStateSchema,
  );
}

export function updateStatusWithLastOutreach(args: {
  collectionDate: string;
  companyKey: string;
  fitStatus: FitStatus;
  outreachStatus: "message_sent" | "follow_up_sent";
  lastOutreachDate: string;
}) {
  return rpc(
    "inspection_update_status_with_last_outreach",
    {
      p_collection_date: args.collectionDate,
      p_company_key: args.companyKey,
      p_fit_status: args.fitStatus,
      p_outreach_status: args.outreachStatus,
      p_last_outreach_date: args.lastOutreachDate,
    },
    reviewStateSchema,
  );
}

export function updateLastOutreach(args: { collectionDate: string; companyKey: string; lastOutreachDate: string | null }) {
  return rpc(
    "inspection_update_last_outreach",
    {
      p_collection_date: args.collectionDate,
      p_company_key: args.companyKey,
      p_last_outreach_date: args.lastOutreachDate,
    },
    reviewStateSchema,
  );
}

export function updateStar(args: { collectionDate: string; companyKey: string; isStarred: boolean }) {
  return rpc(
    "inspection_update_star",
    {
      p_collection_date: args.collectionDate,
      p_company_key: args.companyKey,
      p_is_starred: args.isStarred,
    },
    reviewStateSchema,
  );
}

export function updateNotes(args: { collectionDate: string; companyKey: string; notes: string; communicationHistory: string }) {
  return rpc(
    "inspection_update_notes",
    {
      p_collection_date: args.collectionDate,
      p_company_key: args.companyKey,
      p_notes: args.notes,
      p_communication_history: args.communicationHistory,
    },
    reviewStateSchema,
  );
}
