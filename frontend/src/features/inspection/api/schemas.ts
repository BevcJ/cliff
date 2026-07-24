import { z } from "zod";

import { fitStatusOptions, outreachStatusOptions, workflowOptions } from "../domain/constants";

export const collectionSchema = z.object({
  collection_date: z.string(),
  snapshot_count: z.number(),
  job_count: z.number(),
  synced_at: z.string().nullable(),
});

export const filterOptionsSchema = z.object({
  workplace_modes: z.array(z.string()).default([]),
  has_missing_workplace_modes: z.boolean().default(false),
  ai_team_contexts: z.array(z.string()).default([]),
  has_missing_ai_team_contexts: z.boolean().default(false),
  delivery_contexts: z.array(z.string()).default([]),
  has_missing_delivery_contexts: z.boolean().default(false),
  company_types: z.array(z.string()).default([]),
  has_missing_company_types: z.boolean().default(false),
  company_sizes: z.array(z.string()).default([]),
  has_missing_company_sizes: z.boolean().default(false),
  countries: z.array(z.string()).default([]),
  has_missing_countries: z.boolean().default(false),
  role_classifications: z.array(z.string()).default([]),
  has_missing_role_classifications: z.boolean().default(false),
  sources: z.array(z.string()).default([]),
  has_missing_sources: z.boolean().default(false),
  ai_tech_forward_signals: z.array(z.string()).default([]),
  has_missing_ai_tech_forward_signals: z.boolean().default(false),
});

export const countsSchema = z.object({
  total_companies: z.number(),
  total_jobs: z.number(),
  total_job_description_extracts: z.number(),
  with_contacts: z.number(),
  with_job_description_extracts: z.number(),
  with_company_enrichment: z.number(),
  workflows: z.record(z.string(), z.number()),
  fit_statuses: z.record(z.string(), z.number()),
  outreach_statuses: z.record(z.string(), z.number()),
});

export const companySummarySchema = z.object({
  collection_date: z.string(),
  company_key: z.string(),
  company: z.string(),
  countries: z.array(z.string()).default([]),
  role_classification: z.string().nullable(),
  sources: z.array(z.string()).default([]),
  workplace_modes: z.array(z.string()).default([]),
  ai_team_contexts: z.array(z.string()).default([]),
  delivery_contexts: z.array(z.string()).default([]),
  company_type: z.string().nullable(),
  company_size: z.string().nullable(),
  ai_tech_forward_signal: z.string().nullable(),
  job_count: z.number(),
  job_description_extract_count: z.number(),
  has_contacts: z.boolean(),
  has_job_description_extracts: z.boolean(),
  has_company_enrichment: z.boolean(),
  fit_status: z.enum(fitStatusOptions),
  outreach_status: z.enum(outreachStatusOptions),
  last_outreach_date: z.string().nullable(),
  is_starred: z.boolean(),
  has_review_state: z.boolean(),
  workflow: z.enum(workflowOptions),
  follow_up_status: z.string(),
});

export const companyListSchema = z.object({
  page: z.number(),
  page_size: z.number(),
  total: z.number(),
  rows: z.array(companySummarySchema),
});

export const contactSchema = z
  .object({
    name: z.string().optional(),
    title: z.string().optional(),
    role: z.string().optional(),
    email: z.string().optional(),
    linkedin_url: z.string().optional(),
    source_urls: z.array(z.string()).optional(),
  })
  .passthrough();

export const jobSchema = z
  .object({
    job_title_raw: z.string().optional(),
    role_group: z.string().optional(),
    platform: z.string().optional(),
    source: z.string().optional(),
    country: z.string().optional(),
    location: z.string().optional(),
    department: z.string().optional(),
    team: z.string().optional(),
    employment_type: z.string().optional(),
    workplace_mode: z.string().optional(),
    ai_team_context: z.string().optional(),
    delivery_context: z.string().optional(),
    posted_at: z.string().optional(),
    updated_at: z.string().optional(),
    has_description: z.boolean().optional(),
    url: z.string().optional(),
    source_url: z.string().optional(),
    contacts: z.array(contactSchema).optional(),
  })
  .passthrough();

const nullableDetailStringSchema = z
  .string()
  .nullish()
  .transform((value) => value ?? null);

export const companyDetailSchema = companySummarySchema
  .omit({ collection_date: true })
  .extend({
    role_classification: nullableDetailStringSchema,
    company_type: nullableDetailStringSchema,
    company_size: nullableDetailStringSchema,
    ai_tech_forward_signal: nullableDetailStringSchema,
    inspection_artifact_version: z.number().optional(),
    company_description: z.string().optional().nullable(),
    industry: z.string().optional().nullable(),
    founded_year: z.union([z.string(), z.number()]).optional().nullable(),
    ai_tech_forward_reason: z.string().optional().nullable(),
    why_interesting: z.string().optional().nullable(),
    review_notes: z.string().default(""),
    review_communication_history: z.string().default(""),
    inspected_at: z.string().nullable().optional(),
    last_reviewed_at: z.string().nullable().optional(),
    last_reviewed_by: z.string().nullable().optional(),
    job_count: z.number(),
    job_description_extract_count: z.number(),
    has_contacts: z.boolean(),
    has_job_description_extracts: z.boolean(),
    has_company_enrichment: z.boolean(),
    jobs: z.array(jobSchema).default([]),
    company_contacts: z.array(contactSchema).default([]),
    contacts: z.array(contactSchema).default([]),
    company_source_urls: z.array(z.string()).default([]),
    evidence_urls: z.array(z.string()).default([]),
  })
  .passthrough();

export const reviewStateSchema = z.object({
  company_key: z.string(),
  company: z.string(),
  fit_status: z.enum(fitStatusOptions),
  outreach_status: z.enum(outreachStatusOptions),
  notes: z.string(),
  communication_history: z.string(),
  last_outreach_date: z.string().nullable(),
  is_starred: z.boolean(),
  inspected_at: z.string().nullable(),
  last_seen_collection_date: z.string().nullable(),
  created_at: z.string().nullable(),
  last_updated_at: z.string().nullable(),
  last_updated_by: z.string().nullable(),
});

export type InspectionCollection = z.infer<typeof collectionSchema>;
export type FilterOptions = z.infer<typeof filterOptionsSchema>;
export type InspectionCounts = z.infer<typeof countsSchema>;
export type CompanySummary = z.infer<typeof companySummarySchema>;
export type CompanyList = z.infer<typeof companyListSchema>;
export type CompanyDetail = z.infer<typeof companyDetailSchema>;
export type ReviewState = z.infer<typeof reviewStateSchema>;
