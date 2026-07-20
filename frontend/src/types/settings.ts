export type AutoRefreshInterval = "1m" | "5m" | "15m" | "30m" | "60m" | "manual";

export interface AppSettings {
  auto_refresh_interval: AutoRefreshInterval;
  selected_regions: string[];
}
