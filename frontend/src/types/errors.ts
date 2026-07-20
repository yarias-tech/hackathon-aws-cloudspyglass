export interface ErrorResponse {
  error_code: string;
  message: string;
  details: string | null;
  timestamp: string;
  recoverable: boolean;
}
