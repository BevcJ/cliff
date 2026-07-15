import { FormEvent, useState } from "react";
import { Link, Navigate } from "react-router-dom";

import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { supabase } from "../../lib/supabase";
import { AuthCard } from "./auth-card";
import { useAuth } from "./auth-provider";

export function ForgotPasswordRoute() {
  const { session } = useAuth();
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  if (session) return <Navigate to="/inspection" replace />;

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const { error: resetError } = await supabase.auth.resetPasswordForEmail(email, {
        redirectTo: `${window.location.origin}/set-password`,
      });
      if (resetError) {
        setError(resetError.message);
        return;
      }
      setSent(true);
    } catch (resetError) {
      setError(resetError instanceof Error ? resetError.message : "Unable to send the reset email. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthCard
      description="Enter your invited email address and we will send you a secure password reset link."
      title="Reset password"
    >
      {sent ? (
        <div className="space-y-4">
          <p aria-live="polite" className="text-sm text-green-700">
            If an account exists for that email, a password reset link has been sent.
          </p>
          <Button asChild className="w-full" variant="outline">
            <Link to="/login">Back to sign in</Link>
          </Button>
        </div>
      ) : (
        <form className="space-y-4" onSubmit={onSubmit}>
          <div className="space-y-2">
            <label className="text-sm font-medium" htmlFor="email">
              Email
            </label>
            <Input
              autoComplete="email"
              id="email"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
            />
          </div>
          {error ? (
            <p aria-live="polite" className="text-sm text-destructive">
              {error}
            </p>
          ) : null}
          <Button className="w-full" disabled={submitting} type="submit">
            {submitting ? "Sending reset link..." : "Send reset link"}
          </Button>
          <div className="text-center">
            <Link className="text-sm font-medium text-primary hover:underline" to="/login">
              Back to sign in
            </Link>
          </div>
        </form>
      )}
    </AuthCard>
  );
}
