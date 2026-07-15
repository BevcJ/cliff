import type { ReactNode } from "react";

import { Card, CardContent, CardHeader } from "../../components/ui/card";

type AuthCardProps = {
  children: ReactNode;
  description: string;
  title: string;
};

export function AuthCard({ children, description, title }: AuthCardProps) {
  return (
    <main className="flex min-h-screen items-center justify-center bg-background p-6">
      <Card className="w-full max-w-md">
        <CardHeader>
          <img
            alt=""
            className="mb-3 h-11 w-11"
            src="https://www.pareto.si/wp-content/uploads/2023/03/logo_90.png"
          />
          <p className="text-sm font-semibold text-primary">AI Hiring Radar</p>
          <h1 className="text-base font-semibold leading-none">{title}</h1>
          <p className="text-sm text-muted-foreground">{description}</p>
        </CardHeader>
        <CardContent>{children}</CardContent>
      </Card>
    </main>
  );
}
