import type { DiagramData } from "./diagram";

export interface TagFilter {
  key: string;
  value: string;
}

export interface FilterCriteria {
  tag_filters: TagFilter[];
  type_filters: string[];
}

export interface FilteredResult {
  diagram: DiagramData;
  filtered_count: number;
  total_count: number;
  active_filters: FilterCriteria;
}

export interface TagSuggestion {
  key: string;
  value: string;
  count: number;
}
