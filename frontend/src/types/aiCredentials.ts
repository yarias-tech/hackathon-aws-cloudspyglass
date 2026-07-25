export interface AiCredentialSubmission {
  base_url: string;
  api_key: string;
  model: string;
}

export interface AiCredentialStatus {
  connected: boolean;
  source: "custom" | "environment" | "none";
  model: string | null;
  validated_at: string | null;
}
