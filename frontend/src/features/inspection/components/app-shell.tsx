import { LogOut } from "lucide-react";
import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { Button } from "../../../components/ui/button";
import { useAuth } from "../../auth/auth-provider";
import type { InspectionCollection } from "../api/schemas";

type AppShellProps = {
  collectionDate: string;
  collections: InspectionCollection[];
  children: React.ReactNode;
};

export function AppShell({ collectionDate, collections, children }: AppShellProps) {
  const { signOut, user } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [signingOut, setSigningOut] = useState(false);
  const [signOutError, setSignOutError] = useState<string | null>(null);

  function changeCollection(nextCollectionDate: string) {
    const nextSearch = new URLSearchParams(location.search);
    nextSearch.delete("company");
    nextSearch.delete("page");
    const search = nextSearch.toString();
    navigate(`/inspection/${nextCollectionDate}${search ? `?${search}` : ""}`);
  }

  async function handleSignOut() {
    setSigningOut(true);
    setSignOutError(null);
    const nextError = await signOut();
    setSignOutError(nextError);
    setSigningOut(false);
  }

  return (
    <div className="min-h-screen min-w-[1180px] bg-background">
      <header className="border-b border-t-4 border-t-primary bg-white">
        <div className="flex h-16 items-center justify-between px-6">
          <div className="flex items-center gap-3">
            <img
              alt=""
              className="h-9 w-9"
              src="https://www.pareto.si/wp-content/uploads/2023/03/logo_90.png"
            />
            <div>
              <h1 className="text-lg font-semibold tracking-tight">AI Hiring Radar</h1>
              <p className="text-xs text-muted-foreground">Company inspection workspace</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <label className="text-xs font-medium text-muted-foreground" htmlFor="collection-date">
              Collection
            </label>
            <select
              id="collection-date"
              className="h-9 rounded-full border border-input bg-white px-3 text-sm"
              value={collectionDate}
              onChange={(event) => changeCollection(event.target.value)}
            >
              {collections.map((collection) => (
                <option key={collection.collection_date} value={collection.collection_date}>
                  {collection.collection_date}
                </option>
              ))}
            </select>
            <div className="max-w-64 truncate text-sm text-muted-foreground">{user?.email}</div>
            {signOutError ? (
              <p role="alert" className="max-w-64 text-xs text-destructive">
                {signOutError}
              </p>
            ) : null}
            <Button disabled={signingOut} size="sm" variant="outline" onClick={() => void handleSignOut()}>
              <LogOut className="mr-2 h-4 w-4" />
              {signingOut ? "Signing out..." : "Sign out"}
            </Button>
          </div>
        </div>
      </header>
      {children}
    </div>
  );
}
