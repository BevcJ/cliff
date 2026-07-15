import { Card } from "../../../components/ui/card";
import { formatCount } from "../../../lib/utils";
import type { InspectionCounts } from "../api/schemas";

type MetricStripProps = {
  counts: InspectionCounts | undefined;
  loading: boolean;
};

export function MetricStrip({ counts, loading }: MetricStripProps) {
  const metrics = [
    ["Companies", counts?.total_companies],
    ["Jobs", counts?.total_jobs],
    ["JD extracts", counts?.total_job_description_extracts],
    ["Contacts", counts?.with_contacts],
    ["Enriched", counts?.with_company_enrichment],
  ];

  return (
    <div className="grid grid-cols-5 gap-3">
      {metrics.map(([label, value]) => (
        <Card key={label} className="p-4">
          <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</div>
          <div className="mt-2 text-2xl font-semibold">{loading ? "..." : formatCount(Number(value ?? 0))}</div>
        </Card>
      ))}
    </div>
  );
}
