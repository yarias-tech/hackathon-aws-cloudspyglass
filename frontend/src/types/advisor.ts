export type Pillar = "Security" | "Cost_Optimization" | "Performance";
export type Severity = "critical" | "high" | "medium" | "low";

export interface Suggestion {
  pillar: Pillar;
  title: string;
  description: string;
  severity: Severity;
  affected_resources: string[];
  remediation: string;
  estimated_impact: string | null;
}

export interface AdvisorResponse {
  suggestions: Suggestion[];
  task_id: string;
  status: "idle" | "in_progress" | "completed" | "failed";
  error: string | null;
}

export interface AdvisorStatus {
  status: "idle" | "in_progress" | "completed" | "failed";
  task_id: string | null;
}

export interface AnalyzeRequest {
  pillars?: Pillar[];
}
