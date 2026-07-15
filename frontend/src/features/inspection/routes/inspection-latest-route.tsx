import { Navigate } from "react-router-dom";

import { useCollectionsQuery } from "../hooks/use-inspection-queries";

export function InspectionLatestRoute() {
  const collectionsQuery = useCollectionsQuery();

  if (collectionsQuery.isLoading) {
    return <div className="flex min-h-screen items-center justify-center text-sm text-muted-foreground">Loading collections...</div>;
  }

  if (collectionsQuery.isError) {
    return <div className="flex min-h-screen items-center justify-center text-sm text-destructive">{collectionsQuery.error.message}</div>;
  }

  const latest = collectionsQuery.data?.[0]?.collection_date;
  if (!latest) {
    return <div className="flex min-h-screen items-center justify-center text-sm text-muted-foreground">No synced inspection collections are available.</div>;
  }

  return <Navigate to={`/inspection/${latest}`} replace />;
}
