import { FormEvent, useState } from "react";
import { Navigate, useLocation } from "react-router-dom";

import { Button } from "../../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { Input } from "../../components/ui/input";
import { supabase } from "../../lib/supabase";
import { useAuth } from "./auth-provider";

export function LoginRoute() {
  const { session } = useAuth();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const from = (location.state as { from?: { pathname?: string } } | null)?.from?.pathname ?? "/inspection";

  if (session) return <Navigate to={from} replace />;

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    setStatus(null);
    const { error: signInError } = await supabase.auth.signInWithOtp({
      email,
      options: {
        emailRedirectTo: `${window.location.origin}${from}`,
      },
    });
    setSubmitting(false);
    if (signInError) {
      setError(signInError.message);
      return;
    }
    setStatus("Check your email for a sign-in link.");
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-background p-6">
      <Card className="w-full max-w-md">
        <CardHeader>
          <img
            alt=""
            className="mb-3 h-11 w-11"
            src="https://www.pareto.si/wp-content/uploads/2023/03/logo_90.png"
          />
          <CardTitle>AI Hiring Radar</CardTitle>
          <p className="text-sm text-muted-foreground">Sign in with an invited email address.</p>
        </CardHeader>
        <CardContent>
          <form className="space-y-4" onSubmit={onSubmit}>
            <div className="space-y-2">
              <label className="text-sm font-medium" htmlFor="email">
                Email
              </label>
              <Input id="email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
            </div>
            {error ? <p className="text-sm text-destructive">{error}</p> : null}
            {status ? <p className="text-sm text-green-700">{status}</p> : null}
            <Button className="w-full" disabled={submitting} type="submit">
              {submitting ? "Sending link..." : "Send sign-in link"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </main>
  );
}
