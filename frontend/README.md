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

## Manual hosting notes

The build output is `dist/`. Static hosting must serve `index.html` for unknown routes so React Router can handle `/inspection` and `/inspection/:collectionDate`.

Configure Supabase Auth redirect URLs for every deployed origin, for example:

```text
https://your-domain.example/**
http://localhost:5173/**
```

The application expects users to be invited through Supabase Auth. Disable arbitrary public sign-up in the Supabase project settings.
