import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StrictMode } from "react";
import { BrowserRouter, MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ForgotPasswordRoute } from "./forgot-password-route";
import { LoginRoute } from "./login-route";
import { SetPasswordRoute } from "./set-password-route";

const mocks = vi.hoisted(() => ({
  createPasswordSetupClient: vi.fn(),
  globalGetSession: vi.fn(),
  globalSignOut: vi.fn(),
  resetPasswordForEmail: vi.fn(),
  setSession: vi.fn(),
  signInWithPassword: vi.fn(),
  setupGetSession: vi.fn(),
  setupUpdateUser: vi.fn(),
  useAuth: vi.fn(),
  verifyOtp: vi.fn(),
}));

vi.mock("../../lib/supabase", () => ({
  createPasswordSetupClient: mocks.createPasswordSetupClient,
  supabase: {
    auth: {
      getSession: mocks.globalGetSession,
      resetPasswordForEmail: mocks.resetPasswordForEmail,
      setSession: mocks.setSession,
      signOut: mocks.globalSignOut,
      signInWithPassword: mocks.signInWithPassword,
    },
  },
}));

vi.mock("./auth-provider", () => ({ useAuth: mocks.useAuth }));

beforeEach(() => {
  vi.resetAllMocks();
  mocks.createPasswordSetupClient.mockImplementation(() => ({
    auth: {
      getSession: mocks.setupGetSession,
      updateUser: mocks.setupUpdateUser,
      verifyOtp: mocks.verifyOtp,
    },
  }));
  mocks.useAuth.mockReturnValue({ loading: false, session: null, signOut: vi.fn(), user: null });
  mocks.globalGetSession.mockResolvedValue({
    data: { session: { user: { id: "invited-user" } } },
    error: null,
  });
  mocks.globalSignOut.mockResolvedValue({ error: null });
  mocks.resetPasswordForEmail.mockResolvedValue({ data: {}, error: null });
  mocks.setSession.mockResolvedValue({
    data: { session: { user: { id: "invited-user" } }, user: { id: "invited-user" } },
    error: null,
  });
  mocks.signInWithPassword.mockResolvedValue({ data: { session: {}, user: {} }, error: null });
  mocks.setupGetSession.mockResolvedValue({
    data: {
      session: {
        access_token: "rotated-access-token",
        refresh_token: "rotated-refresh-token",
        user: { id: "invited-user" },
      },
    },
    error: null,
  });
  mocks.setupUpdateUser.mockResolvedValue({ data: { user: { id: "invited-user" } }, error: null });
  mocks.verifyOtp.mockResolvedValue({
    data: {
      session: {
        access_token: "invite-access-token",
        refresh_token: "invite-refresh-token",
        user: { id: "invited-user" },
      },
      user: { id: "invited-user" },
    },
    error: null,
  });
  window.history.replaceState({}, "", "/");
});

describe("LoginRoute", () => {
  it("signs in with the invited email and password", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <LoginRoute />
      </MemoryRouter>,
    );

    await user.type(screen.getByLabelText("Email"), "reviewer@example.com");
    await user.type(screen.getByLabelText("Password"), "correct horse battery staple");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(mocks.signInWithPassword).toHaveBeenCalledWith({
      email: "reviewer@example.com",
      password: "correct horse battery staple",
    });
  });

  it("shows a failed sign-in without navigating", async () => {
    mocks.signInWithPassword.mockResolvedValue({ data: { session: null, user: null }, error: new Error("Invalid login credentials") });
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <LoginRoute />
      </MemoryRouter>,
    );

    await user.type(screen.getByLabelText("Email"), "reviewer@example.com");
    await user.type(screen.getByLabelText("Password"), "wrong password");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByText("Invalid login credentials")).toBeInTheDocument();
  });

  it("allows explicit reauthentication when another account is already signed in", () => {
    mocks.useAuth.mockReturnValue({ loading: false, session: { access_token: "old-token" }, signOut: vi.fn(), user: {} });
    render(
      <MemoryRouter initialEntries={["/login?reauthenticate=1"]}>
        <LoginRoute />
      </MemoryRouter>,
    );

    expect(screen.getByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toBeInTheDocument();
  });
});

describe("ForgotPasswordRoute", () => {
  it("sends recovery links to the password setup route", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <ForgotPasswordRoute />
      </MemoryRouter>,
    );

    await user.type(screen.getByLabelText("Email"), "reviewer@example.com");
    await user.click(screen.getByRole("button", { name: "Send reset link" }));

    expect(mocks.resetPasswordForEmail).toHaveBeenCalledWith("reviewer@example.com", {
      redirectTo: `${window.location.origin}/set-password`,
    });
    expect(await screen.findByText(/If an account exists/)).toBeInTheDocument();
  });
});

describe("SetPasswordRoute", () => {
  it("verifies an invitation, removes its token from the URL, and saves the password", async () => {
    window.history.replaceState({}, "", "/set-password#token_hash=secret-token&type=invite");
    const user = userEvent.setup();
    renderSetPasswordRoute();

    expect(await screen.findByRole("heading", { name: "Confirm secure link" })).toBeInTheDocument();
    expect(mocks.verifyOtp).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Continue" }));
    expect(await screen.findByRole("heading", { name: "Set your password" })).toBeInTheDocument();
    expect(mocks.verifyOtp).toHaveBeenCalledWith({ token_hash: "secret-token", type: "invite" });
    expect(window.location.pathname).toBe("/set-password");
    expect(window.location.hash).toBe("");

    await user.type(screen.getByLabelText("New password"), "a-secure-password");
    await user.type(screen.getByLabelText("Confirm password"), "a-secure-password");
    await user.click(screen.getByRole("button", { name: "Save password" }));

    expect(mocks.setupUpdateUser).toHaveBeenCalledWith({ password: "a-secure-password" });
    expect(mocks.setSession).toHaveBeenCalledWith({
      access_token: "rotated-access-token",
      refresh_token: "rotated-refresh-token",
    });
    expect(await screen.findByText("Inspection page")).toBeInTheDocument();
  });

  it("accepts a recovery token", async () => {
    window.history.replaceState({}, "", "/set-password#token_hash=recovery-token&type=recovery");
    const user = userEvent.setup();
    renderSetPasswordRoute();

    await user.click(await screen.findByRole("button", { name: "Continue" }));
    expect(await screen.findByRole("heading", { name: "Set your password" })).toBeInTheDocument();
    expect(mocks.verifyOtp).toHaveBeenCalledWith({ token_hash: "recovery-token", type: "recovery" });
  });

  it("verifies a token only once under React StrictMode", async () => {
    window.history.replaceState({}, "", "/set-password#token_hash=strict-token&type=invite");
    const user = userEvent.setup();
    renderSetPasswordRoute(true);

    await user.click(await screen.findByRole("button", { name: "Continue" }));
    expect(await screen.findByRole("heading", { name: "Set your password" })).toBeInTheDocument();
    expect(mocks.createPasswordSetupClient).toHaveBeenCalledTimes(1);
    expect(mocks.verifyOtp).toHaveBeenCalledTimes(1);
  });

  it("rejects an expired invitation", async () => {
    mocks.verifyOtp.mockResolvedValue({ data: { session: null, user: null }, error: new Error("Token expired") });
    window.history.replaceState({}, "", "/set-password#token_hash=expired-token&type=invite");
    const user = userEvent.setup();
    renderSetPasswordRoute();

    await user.click(await screen.findByRole("button", { name: "Continue" }));
    expect(await screen.findByRole("heading", { name: "Link unavailable" })).toBeInTheDocument();
    expect(screen.getByText(/invalid or has expired/)).toBeInTheDocument();
    expect(window.location.hash).toBe("");
  });

  it("does not update when password confirmation differs", async () => {
    window.history.replaceState({}, "", "/set-password#token_hash=secret-token&type=invite");
    const user = userEvent.setup();
    renderSetPasswordRoute();

    await user.click(await screen.findByRole("button", { name: "Continue" }));
    await user.type(await screen.findByLabelText("New password"), "first-password");
    await user.type(screen.getByLabelText("Confirm password"), "second-password");
    await user.click(screen.getByRole("button", { name: "Save password" }));

    expect(await screen.findByText("Passwords do not match.")).toBeInTheDocument();
    expect(mocks.setupUpdateUser).not.toHaveBeenCalled();
  });

  it("rejects direct unauthenticated access without a token", async () => {
    window.history.replaceState({}, "", "/set-password");
    renderSetPasswordRoute();

    expect(await screen.findByRole("heading", { name: "Link unavailable" })).toBeInTheDocument();
    expect(mocks.verifyOtp).not.toHaveBeenCalled();
  });

  it("falls back to manual sign-in when session persistence fails after saving", async () => {
    mocks.setSession.mockResolvedValue({ data: { session: null, user: null }, error: new Error("Storage unavailable") });
    window.history.replaceState({}, "", "/set-password#token_hash=secret-token&type=invite");
    const user = userEvent.setup();
    renderSetPasswordRoute();

    await user.click(await screen.findByRole("button", { name: "Continue" }));
    await user.type(await screen.findByLabelText("New password"), "a-secure-password");
    await user.type(screen.getByLabelText("Confirm password"), "a-secure-password");
    await user.click(screen.getByRole("button", { name: "Save password" }));

    expect(await screen.findByRole("heading", { name: "Password saved" })).toBeInTheDocument();
    expect(mocks.globalSignOut).toHaveBeenCalledWith({ scope: "local" });
    expect(screen.getByRole("link", { name: "Go to sign in" })).toHaveAttribute("href", "/login?reauthenticate=1");
  });

  it("clears entered passwords when a different secure link replaces the flow", async () => {
    window.history.replaceState({}, "", "/set-password#token_hash=first-token&type=invite");
    const user = userEvent.setup();
    renderSetPasswordRoute();

    await user.click(await screen.findByRole("button", { name: "Continue" }));
    await user.type(await screen.findByLabelText("New password"), "first-password");
    await user.type(screen.getByLabelText("Confirm password"), "first-password");

    act(() => {
      window.history.pushState({}, "", "/set-password#token_hash=second-token&type=recovery");
      window.dispatchEvent(new PopStateEvent("popstate"));
    });

    await user.click(await screen.findByRole("button", { name: "Continue" }));
    expect(await screen.findByLabelText("New password")).toHaveValue("");
    expect(screen.getByLabelText("Confirm password")).toHaveValue("");
    expect(mocks.createPasswordSetupClient).toHaveBeenCalledTimes(2);
  });

  it("clears a stale session handoff when the route changes while persistence is pending", async () => {
    let resolveSetSession: ((value: unknown) => void) | undefined;
    mocks.setSession.mockReturnValue(
      new Promise((resolve) => {
        resolveSetSession = resolve;
      }),
    );
    window.history.replaceState({}, "", "/set-password#token_hash=first-token&type=invite");
    const user = userEvent.setup();
    renderSetPasswordRoute();

    await user.click(await screen.findByRole("button", { name: "Continue" }));
    await user.type(await screen.findByLabelText("New password"), "first-password");
    await user.type(screen.getByLabelText("Confirm password"), "first-password");
    await user.click(screen.getByRole("button", { name: "Save password" }));
    await waitFor(() => expect(mocks.setSession).toHaveBeenCalled());

    act(() => {
      window.history.pushState({}, "", "/set-password#token_hash=second-token&type=recovery");
      window.dispatchEvent(new PopStateEvent("popstate"));
    });
    await screen.findByRole("heading", { name: "Confirm secure link" });

    await act(async () => {
      resolveSetSession?.({
        data: { session: { user: { id: "invited-user" } }, user: { id: "invited-user" } },
        error: null,
      });
    });

    await waitFor(() => expect(mocks.globalSignOut).toHaveBeenCalledWith({ scope: "local" }));
    expect(screen.getByRole("heading", { name: "Confirm secure link" })).toBeInTheDocument();
  });
});

function renderSetPasswordRoute(strict = false) {
  const app = (
    <BrowserRouter>
      <Routes>
        <Route path="/set-password" element={<SetPasswordRoute />} />
        <Route path="/inspection" element={<p>Inspection page</p>} />
      </Routes>
    </BrowserRouter>
  );
  return render(strict ? <StrictMode>{app}</StrictMode> : app);
}
