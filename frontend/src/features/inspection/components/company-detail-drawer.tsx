import { useEffect, useState } from "react";

import { Badge } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../../components/ui/card";
import { Drawer } from "../../../components/ui/drawer";
import { Textarea } from "../../../components/ui/textarea";
import type { CompanyDetail } from "../api/schemas";
import { followUpLabels } from "../domain/constants";
import { FitStatusBadge, FollowUpBadge, OutreachStatusBadge } from "./status-badges";

type CompanyDetailDrawerProps = {
  open: boolean;
  company: CompanyDetail | undefined;
  loading: boolean;
  error: Error | null;
  saving: boolean;
  onOpenChange: (open: boolean) => void;
  onSaveNotes: (notes: string, communicationHistory: string) => void;
};

export function CompanyDetailDrawer({ open, company, loading, error, saving, onOpenChange, onSaveNotes }: CompanyDetailDrawerProps) {
  const [notes, setNotes] = useState("");
  const [history, setHistory] = useState("");

  useEffect(() => {
    setNotes(company?.review_notes ?? "");
    setHistory(company?.review_communication_history ?? "");
  }, [company?.company_key, company?.review_notes, company?.review_communication_history]);

  return (
    <Drawer open={open} title={company?.company ?? "Company detail"} onOpenChange={onOpenChange}>
      {loading ? <p className="text-sm text-muted-foreground">Loading company...</p> : null}
      {error ? <p className="text-sm text-destructive">{error.message}</p> : null}
      {company ? (
        <div className="space-y-5">
          <div className="space-y-3">
            <div className="flex flex-wrap gap-2">
              <FitStatusBadge status={company.fit_status} />
              <OutreachStatusBadge status={company.outreach_status} />
              <FollowUpBadge status={company.follow_up_status} />
              {company.ai_tech_forward_signal ? <Badge variant="outline">AI signal: {company.ai_tech_forward_signal}</Badge> : null}
            </div>
            <dl className="grid grid-cols-2 gap-3 text-sm">
              <Fact label="Countries" value={company.countries.join(", ")} />
              <Fact label="Role" value={company.role_classification} />
              <Fact label="Company type" value={company.company_type} />
              <Fact label="Company size" value={company.company_size} />
              <Fact label="Jobs" value={String(company.job_count)} />
              <Fact label="JD extracts" value={String(company.job_description_extract_count)} />
              <Fact label="Last outreach" value={company.last_outreach_date} />
              <Fact label="Follow-up" value={followUpLabels[company.follow_up_status] ?? company.follow_up_status} />
            </dl>
          </div>

          <Card>
            <CardHeader>
              <CardTitle>Review notes</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <label className="block space-y-1 text-sm font-medium">
                <span>General Notes</span>
                <Textarea value={notes} onChange={(event) => setNotes(event.target.value)} />
              </label>
              <label className="block space-y-1 text-sm font-medium">
                <span>Communication History</span>
                <Textarea value={history} onChange={(event) => setHistory(event.target.value)} />
              </label>
              <Button disabled={saving} onClick={() => onSaveNotes(notes, history)}>
                {saving ? "Saving..." : "Save notes"}
              </Button>
              {company.last_reviewed_by ? <p className="text-xs text-muted-foreground">Last saved by {company.last_reviewed_by}</p> : null}
            </CardContent>
          </Card>

          <TextPanel title="Company description" value={company.company_description} />
          <TextPanel title="AI signal reason" value={company.ai_tech_forward_reason} />
          <TextPanel title="Why interesting" value={company.why_interesting} />
          <ContactsPanel contacts={company.contacts} />
          <JobsPanel jobs={company.jobs} />
          <LinksPanel title="Evidence URLs" urls={company.evidence_urls} />
          <LinksPanel title="Company source URLs" urls={company.company_source_urls} />
        </div>
      ) : null}
    </Drawer>
  );
}

function Fact({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div>
      <div className="text-xs uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="mt-1 font-medium">{value || "-"}</div>
    </div>
  );
}

function TextPanel({ title, value }: { title: string; value: string | null | undefined }) {
  if (!value) return null;
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="whitespace-pre-wrap text-sm leading-6">{value}</p>
      </CardContent>
    </Card>
  );
}

function JobsPanel({ jobs }: { jobs: CompanyDetail["jobs"] }) {
  if (jobs.length === 0) return null;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Jobs</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {jobs.map((job, index) => (
          <div key={`${job.job_title_raw ?? "job"}-${index}`} className="rounded-lg border p-3 text-sm">
            <div className="font-medium">{job.job_title_raw ?? "Untitled role"}</div>
            <div className="mt-1 text-muted-foreground">{[job.platform, job.country, job.location].filter(Boolean).join(" · ")}</div>
            <div className="mt-2 grid grid-cols-2 gap-2 text-xs">
              <Fact label="Role group" value={job.role_group} />
              <Fact label="Workplace" value={job.workplace_mode} />
              <Fact label="Team" value={job.team} />
              <Fact label="Department" value={job.department} />
            </div>
            <LinksPanel title="Job links" urls={[job.url, job.source_url].filter(Boolean) as string[]} compact />
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

function ContactsPanel({ contacts }: { contacts: CompanyDetail["contacts"] }) {
  if (contacts.length === 0) return null;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Contacts</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {contacts.map((contact, index) => (
          <div key={`${contact.email ?? contact.name ?? "contact"}-${index}`} className="rounded-lg border p-3 text-sm">
            <div className="font-medium">{contact.name || contact.email || "Contact"}</div>
            <div className="text-muted-foreground">{[contact.title, contact.role].filter(Boolean).join(" · ")}</div>
            {contact.email ? <a className="mt-1 block text-primary" href={`mailto:${contact.email}`}>{contact.email}</a> : null}
            {contact.linkedin_url ? <SafeLink label="LinkedIn profile" url={contact.linkedin_url} /> : null}
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

function LinksPanel({ title, urls, compact = false }: { title: string; urls: string[]; compact?: boolean }) {
  const safeUrls = urls.filter(Boolean);
  if (safeUrls.length === 0) return null;
  return (
    <div className={compact ? "mt-3 space-y-1" : "space-y-2"}>
      <h4 className="text-sm font-semibold">{title}</h4>
      <div className="space-y-1">
        {safeUrls.map((url) => (
          <SafeLink key={url} url={url} />
        ))}
      </div>
    </div>
  );
}

function SafeLink({ url, label }: { url: string; label?: string }) {
  const isSafe = url.startsWith("https://") || url.startsWith("http://");
  if (!isSafe) return <span className="block truncate text-xs text-muted-foreground">{url}</span>;
  return (
    <a className="block truncate text-xs text-primary hover:underline" href={url} rel="noopener noreferrer" target="_blank" title={url}>
      {label ?? url.replace(/^https?:\/\//, "")}
    </a>
  );
}
