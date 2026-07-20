export interface CredentialSubmission {
  access_key_id: string;
  secret_access_key: string;
  session_token: string | null;
  region: string;
}

export interface CredentialStatus {
  connected: boolean;
  account_id: string | null;
  credential_source: "ui" | "boto3_chain" | null;
  expiry: string | null;
  status: "Connected" | "Disconnected" | "Expired";
}

export interface ValidationResult {
  valid: boolean;
  account_id: string | null;
  arn: string | null;
  error: string | null;
}
