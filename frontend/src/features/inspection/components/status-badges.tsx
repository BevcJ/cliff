import { Badge } from "../../../components/ui/badge";
import { fitStatusLabels, followUpLabels, outreachStatusLabels, type FitStatus, type OutreachStatus } from "../domain/constants";

export function FitStatusBadge({ status }: { status: FitStatus }) {
  const variant = status === "best_fit" ? "success" : status === "possible_fit" ? "warning" : status === "not_interesting" ? "danger" : "secondary";
  return <Badge variant={variant}>{fitStatusLabels[status]}</Badge>;
}

export function OutreachStatusBadge({ status }: { status: OutreachStatus }) {
  const variant = status === "closed" ? "success" : status.startsWith("lost") ? "danger" : status === "not_started" ? "secondary" : "warning";
  return <Badge variant={variant}>{outreachStatusLabels[status]}</Badge>;
}

export function FollowUpBadge({ status }: { status: string }) {
  if (!status) return null;
  const variant = status === "fresh" ? "success" : status === "due_soon" ? "warning" : "danger";
  return <Badge variant={variant}>{followUpLabels[status] ?? status}</Badge>;
}
