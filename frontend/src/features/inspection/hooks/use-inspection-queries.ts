import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type { CompanyDetail, CompanyList } from "../api/schemas";
import { PAGE_SIZE, type SortDirection, type SortField, type Workflow } from "../domain/constants";
import type { InspectionFilters } from "../domain/filters";
import { filtersForQuery } from "../domain/filters";
import { getCompany, getCounts, getFilterOptions, listCollections, listCompanies, updateLastOutreach, updateNotes, updateStatus, updateStatusWithLastOutreach } from "../api/inspection-api";

export const inspectionKeys = {
  collections: ["inspection", "collections"] as const,
  options: (date: string) => ["inspection", date, "options"] as const,
  counts: (date: string, filters: InspectionFilters) => ["inspection", date, "counts", filtersForQuery(filters)] as const,
  list: (date: string, filters: InspectionFilters, workflow: Workflow, sortField: SortField, sortDirection: SortDirection, page: number) =>
    ["inspection", date, "companies", filtersForQuery(filters), workflow, sortField, sortDirection, page] as const,
  detail: (date: string, companyKey: string) => ["inspection", date, "company", companyKey] as const,
};

export function useCollectionsQuery() {
  return useQuery({ queryKey: inspectionKeys.collections, queryFn: listCollections });
}

export function useFilterOptionsQuery(collectionDate: string) {
  return useQuery({ queryKey: inspectionKeys.options(collectionDate), queryFn: () => getFilterOptions(collectionDate), enabled: Boolean(collectionDate) });
}

export function useCountsQuery(collectionDate: string, filters: InspectionFilters) {
  return useQuery({ queryKey: inspectionKeys.counts(collectionDate, filters), queryFn: () => getCounts(collectionDate, filters), enabled: Boolean(collectionDate) });
}

export function useCompanyListQuery(args: {
  collectionDate: string;
  filters: InspectionFilters;
  workflow: Workflow;
  sortField: SortField;
  sortDirection: SortDirection;
  page: number;
}) {
  return useQuery({
    queryKey: inspectionKeys.list(args.collectionDate, args.filters, args.workflow, args.sortField, args.sortDirection, args.page),
    queryFn: () => listCompanies({ ...args, pageSize: PAGE_SIZE }),
    enabled: Boolean(args.collectionDate),
    placeholderData: keepPreviousData,
  });
}

export function useCompanyDetailQuery(collectionDate: string, companyKey: string) {
  return useQuery({
    queryKey: inspectionKeys.detail(collectionDate, companyKey),
    queryFn: () => getCompany(collectionDate, companyKey),
    enabled: Boolean(collectionDate && companyKey),
  });
}

export function useReviewMutations(collectionDate: string) {
  const queryClient = useQueryClient();

  function invalidate(companyKey?: string) {
    void queryClient.invalidateQueries({ queryKey: ["inspection", collectionDate] });
    if (companyKey) void queryClient.invalidateQueries({ queryKey: inspectionKeys.detail(collectionDate, companyKey) });
  }

  async function snapshot() {
    await queryClient.cancelQueries({ queryKey: ["inspection", collectionDate] });
    return queryClient.getQueriesData({ queryKey: ["inspection", collectionDate] });
  }

  function rollback(context: { previous: ReturnType<typeof queryClient.getQueriesData> } | undefined) {
    context?.previous.forEach(([queryKey, data]) => {
      queryClient.setQueryData(queryKey, data);
    });
  }

  function patchCompany(companyKey: string, patch: Partial<CompanyList["rows"][number]> & Partial<CompanyDetail>) {
    queryClient.setQueriesData<CompanyList>({ queryKey: ["inspection", collectionDate, "companies"] }, (old) => {
      if (!old?.rows) return old;
      return {
        ...old,
        rows: old.rows.map((row) => (row.company_key === companyKey ? { ...row, ...patch } : row)),
      };
    });
    queryClient.setQueryData<CompanyDetail>(inspectionKeys.detail(collectionDate, companyKey), (old) => (old ? { ...old, ...patch } : old));
  }

  return {
    updateStatus: useMutation({
      mutationFn: updateStatus,
      onMutate: async (variables) => {
        const previous = await snapshot();
        patchCompany(variables.companyKey, { fit_status: variables.fitStatus, outreach_status: variables.outreachStatus });
        return { previous };
      },
      onError: (_error, _variables, context) => rollback(context),
      onSettled: (_data, _error, variables) => invalidate(variables?.companyKey),
    }),
    updateStatusWithLastOutreach: useMutation({
      mutationFn: updateStatusWithLastOutreach,
      onMutate: async (variables) => {
        const previous = await snapshot();
        patchCompany(variables.companyKey, {
          fit_status: variables.fitStatus,
          outreach_status: variables.outreachStatus,
          last_outreach_date: variables.lastOutreachDate,
        });
        return { previous };
      },
      onError: (_error, _variables, context) => rollback(context),
      onSettled: (_data, _error, variables) => invalidate(variables?.companyKey),
    }),
    updateLastOutreach: useMutation({
      mutationFn: updateLastOutreach,
      onMutate: async (variables) => {
        const previous = await snapshot();
        patchCompany(variables.companyKey, { last_outreach_date: variables.lastOutreachDate });
        return { previous };
      },
      onError: (_error, _variables, context) => rollback(context),
      onSettled: (_data, _error, variables) => invalidate(variables?.companyKey),
    }),
    updateNotes: useMutation({
      mutationFn: updateNotes,
      onMutate: async (variables) => {
        const previous = await snapshot();
        patchCompany(variables.companyKey, {
          review_notes: variables.notes,
          review_communication_history: variables.communicationHistory,
        });
        return { previous };
      },
      onError: (_error, _variables, context) => rollback(context),
      onSettled: (_data, _error, variables) => invalidate(variables?.companyKey),
    }),
  };
}
