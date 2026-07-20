import type { FilterCriteria } from "./filters";

export type ExportFormat = "pdf" | "png" | "svg";

export interface ExportRequest {
  format: ExportFormat;
  filters: FilterCriteria | null;
}

export interface ExportResult {
  filename: string;
  format: ExportFormat;
  size_bytes: number;
  path: string;
}
