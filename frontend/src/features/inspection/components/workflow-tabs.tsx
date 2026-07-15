import { Button } from "../../../components/ui/button";
import { formatCount } from "../../../lib/utils";
import type { InspectionCounts } from "../api/schemas";
import { workflowLabels, workflowOptions, type Workflow } from "../domain/constants";

type WorkflowTabsProps = {
  counts: InspectionCounts | undefined;
  value: Workflow;
  onChange: (workflow: Workflow) => void;
};

export function WorkflowTabs({ counts, value, onChange }: WorkflowTabsProps) {
  return (
    <div className="flex items-center gap-2">
      {workflowOptions.map((workflow) => (
        <Button
          key={workflow}
          size="sm"
          variant={value === workflow ? "default" : "outline"}
          onClick={() => onChange(workflow)}
        >
          {workflowLabels[workflow]}
          <span className="ml-2 rounded-full bg-white/20 px-2 py-0.5 text-xs">{formatCount(counts?.workflows?.[workflow] ?? 0)}</span>
        </Button>
      ))}
    </div>
  );
}
