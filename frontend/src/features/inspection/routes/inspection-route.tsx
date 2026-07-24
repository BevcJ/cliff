import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import { Button } from "../../../components/ui/button";
import { PAGE_SIZE, type FitStatus, type OutreachStatus, type SortField, type Workflow } from "../domain/constants";
import { buildSearchParams, emptyFilters, parseUrlState } from "../domain/filters";
import { useCollectionsQuery, useCompanyDetailQuery, useCompanyListQuery, useCountsQuery, useFilterOptionsQuery, useReviewMutations } from "../hooks/use-inspection-queries";
import { AppShell } from "../components/app-shell";
import { CompanyDetailDrawer } from "../components/company-detail-drawer";
import { CompanyTable } from "../components/company-table";
import { FilterRail } from "../components/filter-rail";
import { MetricStrip } from "../components/metric-strip";
import { WorkflowTabs } from "../components/workflow-tabs";
import type { CompanySummary } from "../api/schemas";

export function InspectionRoute() {
  const params = useParams();
  const collectionDate = params.collectionDate ?? "";
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const state = useMemo(() => parseUrlState(searchParams), [searchParams]);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [savingCompanyKey, setSavingCompanyKey] = useState<string | null>(null);

  const collectionsQuery = useCollectionsQuery();
  const filterOptionsQuery = useFilterOptionsQuery(collectionDate);
  const countsQuery = useCountsQuery(collectionDate, state.filters);
  const companyListQuery = useCompanyListQuery({
    collectionDate,
    filters: state.filters,
    workflow: state.workflow,
    sortField: state.sortField,
    sortDirection: state.sortDirection,
    page: state.page,
  });
  const detailQuery = useCompanyDetailQuery(collectionDate, state.selectedCompanyKey);
  const mutations = useReviewMutations(collectionDate);

  useEffect(() => {
    if (!companyListQuery.data || companyListQuery.isPlaceholderData) return;
    const totalPages = Math.max(1, Math.ceil(companyListQuery.data.total / PAGE_SIZE));
    if (state.page <= totalPages) return;
    setSearchParams(buildSearchParams({ ...state, page: totalPages, selectedCompanyKey: "" }), { replace: true });
  }, [companyListQuery.data, companyListQuery.isPlaceholderData, setSearchParams, state]);

  const collections = collectionsQuery.data ?? [];
  const collectionExists = collections.some((collection) => collection.collection_date === collectionDate);

  function updateState(next: Partial<typeof state>) {
    const merged = { ...state, ...next };
    setSearchParams(buildSearchParams(merged));
  }

  function updateFilters(filters: typeof state.filters) {
    updateState({ filters, page: 1, selectedCompanyKey: "" });
  }

  function updateWorkflow(workflow: Workflow) {
    updateState({ workflow, page: 1, selectedCompanyKey: "" });
  }

  function updateSort(field: SortField) {
    updateState({
      sortField: field,
      sortDirection: state.sortField === field && state.sortDirection === "desc" ? "asc" : "desc",
      page: 1,
    });
  }

  async function saveStatus(row: CompanySummary, fitStatus: FitStatus, outreachStatus: OutreachStatus) {
    setErrorMessage(null);
    setSavingCompanyKey(row.company_key);
    try {
      await mutations.updateStatus.mutateAsync({ collectionDate, companyKey: row.company_key, fitStatus, outreachStatus });
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Failed to save status");
    } finally {
      setSavingCompanyKey(null);
    }
  }

  async function saveStatusWithLastOutreach(row: CompanySummary, fitStatus: FitStatus, outreachStatus: "message_sent" | "follow_up_sent", lastOutreachDate: string) {
    setErrorMessage(null);
    setSavingCompanyKey(row.company_key);
    try {
      await mutations.updateStatusWithLastOutreach.mutateAsync({ collectionDate, companyKey: row.company_key, fitStatus, outreachStatus, lastOutreachDate });
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Failed to save outreach status");
    } finally {
      setSavingCompanyKey(null);
    }
  }

  async function saveLastOutreach(row: CompanySummary, lastOutreachDate: string | null) {
    setErrorMessage(null);
    setSavingCompanyKey(row.company_key);
    try {
      await mutations.updateLastOutreach.mutateAsync({ collectionDate, companyKey: row.company_key, lastOutreachDate });
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Failed to save Last Outreach");
    } finally {
      setSavingCompanyKey(null);
    }
  }

  async function saveStar(row: CompanySummary, isStarred: boolean) {
    setErrorMessage(null);
    setSavingCompanyKey(row.company_key);
    try {
      await mutations.updateStar.mutateAsync({ collectionDate, companyKey: row.company_key, isStarred });
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Failed to save star");
    } finally {
      setSavingCompanyKey(null);
    }
  }

  async function saveNotes(notes: string, communicationHistory: string) {
    if (!state.selectedCompanyKey) return;
    setErrorMessage(null);
    try {
      await mutations.updateNotes.mutateAsync({ collectionDate, companyKey: state.selectedCompanyKey, notes, communicationHistory });
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Failed to save notes");
    }
  }

  if (collectionsQuery.isLoading) {
    return <div className="flex min-h-screen items-center justify-center text-sm text-muted-foreground">Loading inspection workspace...</div>;
  }

  if (collectionsQuery.isError) {
    return <div className="flex min-h-screen items-center justify-center text-sm text-destructive">{collectionsQuery.error.message}</div>;
  }

  if (!collectionExists) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background p-6">
        <div className="rounded-xl border bg-white p-6 text-center shadow-sm">
          <h1 className="text-lg font-semibold">Collection not found</h1>
          <p className="mt-2 text-sm text-muted-foreground">{collectionDate} has not been synced to Supabase.</p>
          <Button className="mt-4" onClick={() => navigate("/inspection")}>Go to latest collection</Button>
        </div>
      </div>
    );
  }

  return (
    <AppShell collectionDate={collectionDate} collections={collections}>
      <main className="space-y-4 p-6">
        <MetricStrip counts={countsQuery.data} loading={countsQuery.isLoading} />
        <div className="flex items-center justify-between rounded-xl border bg-white p-3">
          <WorkflowTabs counts={countsQuery.data} value={state.workflow} onChange={updateWorkflow} />
          <Button variant="outline" size="sm" onClick={() => updateFilters(emptyFilters)}>
            Clear filters
          </Button>
        </div>
        {errorMessage ? <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{errorMessage}</div> : null}
        <div className="flex gap-4">
          <FilterRail filters={state.filters} options={filterOptionsQuery.data} onChange={updateFilters} />
          <section className="min-w-0 flex-1 space-y-3">
            {companyListQuery.isError ? <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{companyListQuery.error.message}</div> : null}
            {companyListQuery.isLoading ? <div className="rounded-xl border bg-white p-8 text-center text-sm text-muted-foreground">Loading companies...</div> : null}
            <CompanyTable
              rows={companyListQuery.data?.rows ?? []}
              total={companyListQuery.data?.total ?? 0}
              page={state.page}
              pageSize={PAGE_SIZE}
              selectedCompanyKey={state.selectedCompanyKey}
              sortField={state.sortField}
              sortDirection={state.sortDirection}
              savingCompanyKey={savingCompanyKey}
              onSelect={(companyKey) => updateState({ selectedCompanyKey: companyKey })}
              onSort={updateSort}
              onPageChange={(page) => updateState({ page, selectedCompanyKey: "" })}
              onStarChange={(row, isStarred) => void saveStar(row, isStarred)}
              onStatusChange={(row, fitStatus, outreachStatus) => void saveStatus(row, fitStatus, outreachStatus)}
              onStatusWithLastOutreachChange={(row, fitStatus, outreachStatus, lastOutreachDate) => void saveStatusWithLastOutreach(row, fitStatus, outreachStatus, lastOutreachDate)}
              onLastOutreachChange={(row, lastOutreachDate) => void saveLastOutreach(row, lastOutreachDate)}
            />
          </section>
        </div>
      </main>
      <CompanyDetailDrawer
        open={Boolean(state.selectedCompanyKey)}
        company={detailQuery.data}
        loading={detailQuery.isFetching}
        error={detailQuery.error}
        saving={mutations.updateNotes.isPending}
        onOpenChange={(open) => {
          if (!open) updateState({ selectedCompanyKey: "" });
        }}
        onSaveNotes={(notes, communicationHistory) => void saveNotes(notes, communicationHistory)}
      />
    </AppShell>
  );
}
