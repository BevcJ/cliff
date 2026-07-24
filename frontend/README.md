# AI Hiring Radar Frontend

Desktop-only Vite React application for the company inspection workflow.

## Local setup

```bash
npm install
cp .env.example .env.local
npm run dev
```

Required browser-safe variables:

```text
VITE_SUPABASE_URL
VITE_SUPABASE_PUBLISHABLE_KEY
```

Do not expose `AI_HIRING_RADAR_DATABASE_URL`, Supabase secret keys, service-role keys, or PostgreSQL passwords to this application.

## Checks

```bash
npm run typecheck
npm run test
npm run build
```

## Authentication

The application uses invite-only Supabase email/password authentication. It does not expose public registration or use a service-role/secret key in the browser.

### Hosted Supabase settings

Before deploying the frontend, configure the hosted Supabase project:

1. Open **Authentication > Providers > Email** and keep the email provider enabled.
2. Disable **Allow new users to sign up**. This is the control that makes access invite-only; the frontend publishable key cannot enforce this setting.
3. Set the minimum password length to at least 8 characters.
4. Set **Authentication > URL Configuration > Site URL** to the deployed frontend origin, without a trailing slash.
5. Add the exact deployed and local password callback URLs to **Redirect URLs**:

```text
https://your-domain.example/set-password
http://localhost:5173/set-password
```

6. Disable click tracking or link rewriting for authentication emails in the configured SMTP/email provider. Rewriting one-time authentication links can expose or break their URL fragments.

The checked-in local Supabase configuration also disables signup, requires 8-character passwords, allows the local callback URL, and loads matching templates from `supabase/templates/`.

### Email templates

The invitation template must use a token hash because admin invitations do not initiate a PKCE flow. In **Authentication > Email Templates > Invite user**, make the action link point to:

```html
<a href="{{ .SiteURL }}/set-password#token_hash={{ .TokenHash }}&amp;type=invite">Set your password</a>
```

In **Authentication > Email Templates > Reset password**, make the action link point to:

```html
<a href="{{ .RedirectTo }}#token_hash={{ .TokenHash }}&amp;type=recovery">Reset your password</a>
```

Do not replace these links with `{{ .ConfirmationURL }}`. The URL fragment keeps the one-time credential out of hosting/CDN request logs and referrer headers. The frontend removes the token from the address bar, waits for an explicit user confirmation so passive link scanners do not consume it, verifies and updates through an isolated non-persistent client, and persists that exact session only after the password succeeds.

### User onboarding

1. Open **Authentication > Users** in the Supabase dashboard.
2. Choose **Add user > Send invitation** and enter the user's email address.
3. The user follows the invitation email to `/set-password`, chooses a password, and is signed in.
4. Future sign-ins use the email and password at `/login`.

Users who forget their password can use `/forgot-password`. Account creation and invitation remain administrator-only.

## Review behavior

Selecting `message_sent` or `follow_up_sent` requires choosing Last Outreach in the same operation. Fit-only edits preserve that date, and Last Outreach cannot be cleared while either outbound status remains active.

## Manual hosting notes

The build output is `dist/`. Static hosting must serve `index.html` for unknown routes so React Router can handle `/inspection` and `/inspection/:collectionDate`.

Configure the Supabase Auth settings and email templates above before sending invitations.
