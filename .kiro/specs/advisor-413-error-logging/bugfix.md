# Bugfix Requirements Document

## Introduction

When the AI Architecture Advisor sends a payload that exceeds the AI provider's context window or request body size limit, the API responds with HTTP 413 ("Payload Too Large"). The backend logs only the generic wrapper message ("AI API rejected the request with status 413.") and discards the provider's detailed error message (e.g., "Maximum context length exceeded"). Additionally, the default token budget of 120,000 tokens exceeds the context limits of many AI providers, making this error likely to occur with large infrastructure scans.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN the AI API returns a 4xx error (non-429) THEN the system logs only the `CloudSpyglassError` wrapper message via `str(exc)` and discards the `details` field containing the actual API provider error message

1.2 WHEN the AI API returns HTTP 413 because the serialized context exceeds the provider's maximum request size THEN the user sees only "Analysis failed. Please try again" with no actionable diagnostic information in the logs

1.3 WHEN the `AI_API_MAX_TOKENS` environment variable is not set THEN the system defaults to 120,000 tokens which exceeds the context window of many AI providers (e.g., Groq models at 8K-32K, some OpenRouter models at 8K-128K)

### Expected Behavior (Correct)

2.1 WHEN the AI API returns a 4xx error (non-429) THEN the system SHALL log both the wrapper message and the `details` field (containing the provider's actual error message) at ERROR level

2.2 WHEN a `CloudSpyglassError` with a non-null `details` field is caught in `run_analysis` THEN the system SHALL include the `details` content in the log output

2.3 WHEN the `AI_API_MAX_TOKENS` environment variable is not set THEN the system SHALL default to 30,000 tokens which is within the context limits of most common AI providers

### Unchanged Behavior (Regression Prevention)

3.1 WHEN the AI API returns a successful response THEN the system SHALL CONTINUE TO parse the response and store results normally

3.2 WHEN the AI API returns a 429 (rate limit) error THEN the system SHALL CONTINUE TO retry with exponential backoff as before

3.3 WHEN the AI API returns a 5xx (server) error THEN the system SHALL CONTINUE TO retry with exponential backoff as before

3.4 WHEN the AI API request times out THEN the system SHALL CONTINUE TO raise a timeout error without retrying

3.5 WHEN `AI_API_MAX_TOKENS` is explicitly set via environment variable THEN the system SHALL CONTINUE TO use the user-provided value regardless of the new default
