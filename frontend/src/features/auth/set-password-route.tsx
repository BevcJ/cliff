import { FormEvent, useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { createPasswordSetupClient, supabase } from "../../lib/supabase";
import { AuthCard } from "./auth-card";

const MINIMUM_PASSWORD_LENGTH = 8;

type PasswordSetupType = "invite" | "recovery";
type VerificationStatus = "confirm" | "checking" | "ready" | "error";

type PasswordSetupCredentials = {
  key: string;
  tokenHash: string;
  type: PasswordSetupType;
};

type PasswordSetupClient = ReturnType<typeof createPasswordSetupClient>;
type VerificationRequest = ReturnType<PasswordSetupClient["auth"]["verifyOtp"]>;

type PasswordSetupFlow = {
  client: PasswordSetupClient;
  credentials: PasswordSetupCredentials;
  verificationRequest: VerificationRequest | null;
};

export function SetPasswordRoute() {
  const location = useLocation();
  const navigate = useNavigate();
  const mounted = useRef(false);
  const setupFlow = useRef<PasswordSetupFlow | null>(null);
  const verifiedUserId = useRef<string | null>(null);
  const [verificationStatus, setVerificationStatus] = useState<VerificationStatus>("checking");
  const [verificationError, setVerificationError] = useState<string | null>(null);
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [passwordSaved, setPasswordSaved] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    const authParams = new URLSearchParams(location.hash.replace(/^#/, ""));
    const tokenHash = authParams.get("token_hash");
    const tokenType = authParams.get("type");

    if (tokenHash || tokenType) removeAuthTokenFromUrl(location);

    if (!tokenHash || !isPasswordSetupType(tokenType)) {
      setupFlow.current = null;
      verifiedUserId.current = null;
      setPassword("");
      setConfirmPassword("");
      setError(null);
      setPasswordSaved(false);
      setSubmitting(false);
      setVerificationError("This password link is invalid or has expired. Request a new email and try again.");
      setVerificationStatus("error");
      return;
    }

    const key = `${tokenType}:${tokenHash}`;
    if (setupFlow.current?.credentials.key === key) return;

    setupFlow.current = {
      client: createPasswordSetupClient(),
      credentials: { key, tokenHash, type: tokenType },
      verificationRequest: null,
    };
    verifiedUserId.current = null;
    setPassword("");
    setConfirmPassword("");
    setError(null);
    setPasswordSaved(false);
    setSubmitting(false);
    setVerificationError(null);
    setVerificationStatus("confirm");
  }, [location]);

  async function verifyLink() {
    const flow = setupFlow.current;
    if (!flow) {
      setVerificationError("This password link is invalid or has expired. Request a new email and try again.");
      setVerificationStatus("error");
      return;
    }

    setVerificationStatus("checking");
    const request =
      flow.verificationRequest ??
      flow.client.auth.verifyOtp({
        token_hash: flow.credentials.tokenHash,
        type: flow.credentials.type,
      });
    flow.verificationRequest = request;

    try {
      const { data, error: verifyError } = await request;
      if (setupFlow.current !== flow) return;
      if (verifyError || !data.session || !data.user || data.session.user.id !== data.user.id) {
        setVerificationError("This password link is invalid or has expired. Request a new email and try again.");
        setVerificationStatus("error");
        return;
      }

      verifiedUserId.current = data.user.id;
      setVerificationStatus("ready");
    } catch {
      if (setupFlow.current !== flow) return;
      setVerificationError("This password link is invalid or has expired. Request a new email and try again.");
      setVerificationStatus("error");
    }
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);

    if (password.length < MINIMUM_PASSWORD_LENGTH) {
      setError(`Password must contain at least ${MINIMUM_PASSWORD_LENGTH} characters.`);
      return;
    }
    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    const flow = setupFlow.current;
    const expectedUserId = verifiedUserId.current;
    if (!flow || !expectedUserId) {
      setVerificationError("Your secure session expired. Request a new password email and try again.");
      setVerificationStatus("error");
      return;
    }

    let saved = false;
    setSubmitting(true);
    try {
      const { error: updateError } = await flow.client.auth.updateUser({ password });
      if (updateError) {
        setError(updateError.message);
        return;
      }
      saved = true;
      if (!isCurrentFlow(flow)) return;

      const { data: setupData, error: setupSessionError } = await flow.client.auth.getSession();
      if (!isCurrentFlow(flow)) return;
      if (setupSessionError || !setupData.session || setupData.session.user.id !== expectedUserId) {
        await requireManualSignIn(flow);
        return;
      }

      const { data: appData, error: sessionError } = await supabase.auth.setSession({
        access_token: setupData.session.access_token,
        refresh_token: setupData.session.refresh_token,
      });
      if (!isCurrentFlow(flow)) {
        await clearStaleHandoff(expectedUserId);
        return;
      }
      if (sessionError || !appData.session || appData.session.user.id !== expectedUserId) {
        await requireManualSignIn(flow);
        return;
      }

      navigate("/inspection", { replace: true });
    } catch (updateError) {
      if (!isCurrentFlow(flow)) return;
      if (saved) {
        await requireManualSignIn(flow);
      } else if (isCurrentFlow(flow)) {
        setError(updateError instanceof Error ? updateError.message : "Unable to save the password. Please try again.");
      }
    } finally {
      if (isCurrentFlow(flow)) setSubmitting(false);
    }
  }

  function isCurrentFlow(flow: PasswordSetupFlow) {
    return mounted.current && setupFlow.current === flow;
  }

  async function requireManualSignIn(flow: PasswordSetupFlow) {
    try {
      await supabase.auth.signOut({ scope: "local" });
    } catch {
      // The reauthentication login route remains available even if local cleanup fails.
    }
    if (isCurrentFlow(flow)) setPasswordSaved(true);
  }

  async function clearStaleHandoff(expectedUserId: string) {
    try {
      const { data } = await supabase.auth.getSession();
      if (data.session?.user.id === expectedUserId) {
        await supabase.auth.signOut({ scope: "local" });
      }
    } catch {
      // A stale flow must not update the replacement flow's UI.
    }
  }

  if (verificationStatus === "confirm") {
    return (
      <AuthCard
        description="Continue to verify this one-time link before choosing your password."
        title="Confirm secure link"
      >
        <Button className="w-full" onClick={verifyLink} type="button">
          Continue
        </Button>
      </AuthCard>
    );
  }

  if (verificationStatus === "checking") {
    return (
      <AuthCard description="Please wait while we verify your secure link." title="Verifying link">
        <p aria-live="polite" className="text-sm text-muted-foreground">
          Verifying your invitation...
        </p>
      </AuthCard>
    );
  }

  if (verificationStatus === "error") {
    return (
      <AuthCard description="We could not verify this secure link." title="Link unavailable">
        <div className="space-y-4">
          <p role="alert" className="text-sm text-destructive">
            {verificationError}
          </p>
          <Button asChild className="w-full" variant="outline">
            <Link to="/forgot-password">Request a password reset</Link>
          </Button>
        </div>
      </AuthCard>
    );
  }

  if (passwordSaved) {
    return (
      <AuthCard
        description="Your password was saved, but automatic sign-in failed. Sign in with your new password."
        title="Password saved"
      >
        <Button asChild className="w-full">
          <Link to="/login?reauthenticate=1">Go to sign in</Link>
        </Button>
      </AuthCard>
    );
  }

  return (
    <AuthCard description="Choose a password for your invited account." title="Set your password">
      <form className="space-y-4" onSubmit={onSubmit}>
        <div className="space-y-2">
          <label className="text-sm font-medium" htmlFor="password">
            New password
          </label>
          <Input
            autoComplete="new-password"
            id="password"
            minLength={MINIMUM_PASSWORD_LENGTH}
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
          />
          <p className="text-xs text-muted-foreground">Use at least {MINIMUM_PASSWORD_LENGTH} characters.</p>
        </div>
        <div className="space-y-2">
          <label className="text-sm font-medium" htmlFor="confirm-password">
            Confirm password
          </label>
          <Input
            autoComplete="new-password"
            id="confirm-password"
            minLength={MINIMUM_PASSWORD_LENGTH}
            type="password"
            value={confirmPassword}
            onChange={(event) => setConfirmPassword(event.target.value)}
            required
          />
        </div>
        {error ? (
          <p aria-live="polite" className="text-sm text-destructive">
            {error}
          </p>
        ) : null}
        <Button className="w-full" disabled={submitting} type="submit">
          {submitting ? "Saving password..." : "Save password"}
        </Button>
      </form>
    </AuthCard>
  );
}

function isPasswordSetupType(value: string | null): value is PasswordSetupType {
  return value === "invite" || value === "recovery";
}

function removeAuthTokenFromUrl(location: ReturnType<typeof useLocation>) {
  const hashParams = new URLSearchParams(location.hash.replace(/^#/, ""));
  hashParams.delete("token_hash");
  hashParams.delete("type");
  const hash = hashParams.toString();
  window.history.replaceState(
    window.history.state,
    "",
    `${location.pathname}${location.search}${hash ? `#${hash}` : ""}`,
  );
}
