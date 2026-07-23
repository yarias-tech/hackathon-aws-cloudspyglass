import type { RegionFailure } from "./resources";
import type { HierarchyTree } from "./hierarchy";

export interface DiagramNode {
  id: string;
  resource_type: string;
  name: string;
  region: string;
  is_external: boolean;
  is_unresolved: boolean;
  icon_url: string;
}

export interface DiagramEdge {
  id: string;
  source: string;
  target: string;
  category: "network" | "iam" | "event" | "data";
  derived_from: string;
  label: string | null;
}

export interface DiagramData {
  nodes: DiagramNode[];
  edges: DiagramEdge[];
  account_id: string;
  scan_timestamp: string;
  total_resources: number;
  scanned_regions: string[];
  failures: RegionFailure[];
  hierarchy: HierarchyTree | null;
}
