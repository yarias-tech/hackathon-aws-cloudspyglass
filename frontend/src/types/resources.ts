export interface Resource {
  arn: string;
  resource_type: string;
  name: string;
  region: string;
  tags: Record<string, string>;
  creation_date: string | null;
  iam_role: string | null;
  attributes: Record<string, unknown>;
  is_external: boolean;
  is_unresolved: boolean;
}

export interface Relationship {
  source_arn: string;
  target_arn: string;
  category: "network" | "iam" | "event" | "data";
  derived_from: string;
}

export interface RegionFailure {
  region: string;
  resource_type: string;
  error_message: string;
  timestamp: string;
}

export interface ScanResult {
  account_id: string;
  scan_timestamp: string;
  resources: Resource[];
  relationships: Relationship[];
  failures: RegionFailure[];
  scanned_regions: string[];
  total_scan_duration_ms: number;
}
