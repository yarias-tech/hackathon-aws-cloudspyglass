"""Advisor Service orchestrating the AI architecture analysis lifecycle."""

import asyncio
import logging
import uuid
from enum import Enum

from openai import APIStatusError, RateLimitError

from ..exceptions import CloudSpyglassError
from ..models.advisor import AdvisorResponse, FilterCriteriaInput
from .ai_credential_manager import AiCredentialManager
from .context_serializer import ContextSerializer
from .prompts import CLOUD_ARCHITECT_SYSTEM_PROMPT, build_user_message
from .response_parser import ResponseParser
from .scan_storage import ScanStorage

logger = logging.getLogger(__name__)

VALID_PILLARS = {"Security", "Cost_Optimization", "Performance"}
ALL_PILLARS = ["Security", "Cost_Optimization", "Performance"]

# Retry configuration
MAX_RETRY_ATTEMPTS = 3
BACKOFF_DELAYS = [1, 2, 4]  # seconds: 1s, 2s, 4s exponential backoff

# Timeout for each AI API call attempt
API_CALL_TIMEOUT_SECONDS = 60


class AnalysisState(str, Enum):
    """Analysis lifecycle states."""

    IDLE = "idle"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class AdvisorService:
    """Orchestrates the full AI architecture analysis lifecycle.

    Manages state transitions, validates preconditions, calls the AI API
    with retry logic, and stores results for retrieval.

    State transitions: idle -> in_progress -> completed/failed
    Concurrency: Only one analysis at a time (rejects with 409 if in_progress).
    """

    def __init__(
        self,
        ai_credential_manager: AiCredentialManager,
        scan_storage: ScanStorage,
        context_serializer: ContextSerializer,
        response_parser: ResponseParser,
    ) -> None:
        self._ai_credential_manager = ai_credential_manager
        self._scan_storage = scan_storage
        self._context_serializer = context_serializer
        self._response_parser = response_parser

        self._state: AnalysisState = AnalysisState.IDLE
        self._task_id: str | None = None
        self._results: AdvisorResponse | None = None
        self._error: str | None = None

    async def start_analysis(
        self, pillars: list[str] | None, account_id: str, filter_criteria: FilterCriteriaInput | None = None
    ) -> str:
        """Validate preconditions and initiate background analysis.

        Args:
            pillars: List of pillars to analyze, or None for all pillars.
            account_id: AWS account ID whose scan to analyze.
            filter_criteria: Optional filter criteria to scope analysis to filtered resources.

        Returns:
            A task_id string identifying this analysis run.

        Raises:
            CloudSpyglassError: If validation fails (no scan, invalid pillars,
                concurrent request).
        """
        # Reject concurrent requests
        if self._state == AnalysisState.IN_PROGRESS:
            raise CloudSpyglassError(
                error_code="ANALYSIS_ALREADY_RUNNING",
                message="An analysis is already in progress. Please wait for it to complete.",
                recoverable=True,
                status_code=409,
            )

        # Validate scan exists
        scan_result = await self._scan_storage.load(account_id)
        if scan_result is None:
            raise CloudSpyglassError(
                error_code="NO_COMPLETED_SCAN",
                message="A scan must be completed before requesting analysis.",
                recoverable=False,
                status_code=400,
            )

        # Default to all pillars if none specified
        if pillars is None or len(pillars) == 0:
            pillars = list(ALL_PILLARS)

        # Validate pillar values
        invalid_pillars = [p for p in pillars if p not in VALID_PILLARS]
        if invalid_pillars:
            raise CloudSpyglassError(
                error_code="INVALID_PILLAR",
                message=f"Invalid pillar value(s): {', '.join(invalid_pillars)}. "
                f"Must be one of: Security, Cost_Optimization, Performance.",
                recoverable=False,
                status_code=422,
            )

        # Transition to in_progress
        task_id = str(uuid.uuid4())
        self._state = AnalysisState.IN_PROGRESS
        self._task_id = task_id
        self._results = None
        self._error = None

        # Launch background task
        asyncio.create_task(self.run_analysis(task_id, pillars, account_id, filter_criteria))

        return task_id

    async def run_analysis(
        self, task_id: str, pillars: list[str], account_id: str, filter_criteria: FilterCriteriaInput | None = None
    ) -> None:
        """Execute the full analysis pipeline as a background task.

        1. Load scan from storage
        1.5. Apply filters if provided
        2. Serialize context using ContextSerializer
        3. Get client and model from AiCredentialManager
        4. Call AI API with retry logic
        5. Parse response using ResponseParser
        6. Store results and update state

        Args:
            task_id: The task identifier for this analysis run.
            pillars: List of pillars to analyze.
            account_id: AWS account ID whose scan to analyze.
            filter_criteria: Optional filter criteria to scope analysis to filtered resources.
        """
        try:
            # 1. Load scan from storage
            scan_result = await self._scan_storage.load(account_id)
            if scan_result is None:
                raise CloudSpyglassError(
                    error_code="NO_COMPLETED_SCAN",
                    message="Scan result no longer available.",
                    recoverable=False,
                    status_code=400,
                )

            # 1.5 Apply filters if provided
            if filter_criteria is not None:
                tag_filters = filter_criteria.tag_filters or []
                type_filters = filter_criteria.type_filters or []
                tag_operator = filter_criteria.tag_filter_operator or "AND"

                if tag_filters or type_filters:
                    from ..models.filters import TagFilter as TagFilterModel
                    from .filter_engine import FilterEngine

                    # Convert to TagFilter models (they're already TagFilter instances from Pydantic)
                    tag_filter_models = [
                        TagFilterModel(key=tf.key, value=tf.value)
                        for tf in tag_filters
                    ]

                    filter_engine = FilterEngine()
                    filtered_result = filter_engine.apply_filters(
                        scan_result,
                        tag_filters=tag_filter_models,
                        type_filters=type_filters,
                        tag_filter_operator=tag_operator,
                    )

                    # Create a new ScanResult with only the filtered resources
                    filtered_arns = {node.id for node in filtered_result.diagram.nodes}
                    filtered_resources = [
                        r for r in scan_result.resources if r.arn in filtered_arns
                    ]
                    filtered_relationships = [
                        rel for rel in scan_result.relationships
                        if rel.source_arn in filtered_arns and rel.target_arn in filtered_arns
                    ]

                    from ..models.scan import ScanResult as ScanResultModel

                    scan_result = ScanResultModel(
                        account_id=scan_result.account_id,
                        scan_timestamp=scan_result.scan_timestamp,
                        resources=filtered_resources,
                        relationships=filtered_relationships,
                        failures=scan_result.failures,
                        scanned_regions=scan_result.scanned_regions,
                        total_scan_duration_ms=scan_result.total_scan_duration_ms,
                    )

            # 2. Serialize context
            serialized_context = self._context_serializer.serialize(
                scan_result, pillars
            )

            # 3. Get AI client and model
            client = self._ai_credential_manager.get_client()
            model = self._ai_credential_manager.get_model()

            # 4. Call AI API with retry logic
            system_message = {"role": "system", "content": CLOUD_ARCHITECT_SYSTEM_PROMPT}
            user_message = {
                "role": "user",
                "content": build_user_message(serialized_context, pillars),
            }

            raw_content = await self._call_ai_with_retry(
                client, model, [system_message, user_message]
            )

            # 5. Parse response
            valid_arns = {r.arn for r in scan_result.resources}
            advisor_response = self._response_parser.parse(raw_content, valid_arns)

            # 6. Store results and update state
            advisor_response.task_id = task_id
            advisor_response.status = "completed"
            self._results = advisor_response
            self._state = AnalysisState.COMPLETED

            logger.info(
                "Analysis %s completed with %d suggestions",
                task_id,
                len(advisor_response.suggestions),
            )

        except Exception as exc:
            self._state = AnalysisState.FAILED
            if isinstance(exc, CloudSpyglassError) and exc.details:
                self._error = f"{exc} | Details: {exc.details}"
                logger.error("Analysis %s failed: %s | Details: %s", task_id, exc, exc.details)
            else:
                self._error = str(exc)
                logger.error("Analysis %s failed: %s", task_id, exc)

    async def _call_ai_with_retry(
        self, client, model: str, messages: list[dict]
    ) -> str:
        """Call the AI API with exponential backoff retry on 429/5xx errors.

        Args:
            client: The AsyncOpenAI client instance.
            model: The model identifier to use.
            messages: The chat messages (system + user).

        Returns:
            The raw content string from the AI response.

        Raises:
            CloudSpyglassError: If all retries are exhausted or a non-retryable
                error occurs.
        """
        last_exception: Exception | None = None

        for attempt in range(MAX_RETRY_ATTEMPTS):
            try:
                response = await asyncio.wait_for(
                    client.chat.completions.create(
                        model=model,
                        messages=messages,
                    ),
                    timeout=API_CALL_TIMEOUT_SECONDS,
                )

                # Extract content from response
                content = response.choices[0].message.content
                if content is None:
                    raise CloudSpyglassError(
                        error_code="AI_EMPTY_RESPONSE",
                        message="AI API returned an empty response.",
                        recoverable=True,
                        status_code=502,
                    )
                return content

            except asyncio.TimeoutError:
                # Timeout — do not retry
                raise CloudSpyglassError(
                    error_code="AI_TIMEOUT",
                    message="AI API request timed out after 60 seconds.",
                    recoverable=True,
                    status_code=504,
                )

            except RateLimitError as exc:
                # 429 — retry with backoff
                last_exception = exc
                if attempt < MAX_RETRY_ATTEMPTS - 1:
                    delay = BACKOFF_DELAYS[attempt]
                    logger.warning(
                        "AI API rate limited (attempt %d/%d), retrying in %ds",
                        attempt + 1,
                        MAX_RETRY_ATTEMPTS,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    continue
                # Final attempt exhausted
                break

            except APIStatusError as exc:
                if exc.status_code >= 500:
                    # 5xx — retry with backoff
                    last_exception = exc
                    if attempt < MAX_RETRY_ATTEMPTS - 1:
                        delay = BACKOFF_DELAYS[attempt]
                        logger.warning(
                            "AI API server error %d (attempt %d/%d), retrying in %ds",
                            exc.status_code,
                            attempt + 1,
                            MAX_RETRY_ATTEMPTS,
                            delay,
                        )
                        await asyncio.sleep(delay)
                        continue
                    # Final attempt exhausted
                    break
                else:
                    # 4xx (non-429) — do not retry
                    raise CloudSpyglassError(
                        error_code="AI_CLIENT_ERROR",
                        message=f"AI API rejected the request with status {exc.status_code}.",
                        details=str(exc.message) if hasattr(exc, "message") else str(exc),
                        recoverable=False,
                        status_code=502,
                    )

            except CloudSpyglassError:
                raise

            except Exception as exc:
                # Unexpected error — do not retry
                raise CloudSpyglassError(
                    error_code="AI_UNEXPECTED_ERROR",
                    message="An unexpected error occurred while calling the AI API.",
                    details=str(exc),
                    recoverable=False,
                    status_code=500,
                ) from exc

        # All retry attempts exhausted
        error_detail = str(last_exception) if last_exception else "Unknown error"
        raise CloudSpyglassError(
            error_code="AI_RETRIES_EXHAUSTED",
            message="AI API request failed after all retry attempts.",
            details=error_detail,
            recoverable=True,
            status_code=502,
        )

    def get_status(self) -> dict:
        """Return the current analysis status and task_id.

        Returns:
            Dict with 'status' and 'task_id' keys.
        """
        return {
            "status": self._state.value,
            "task_id": self._task_id,
        }

    def get_results(self) -> AdvisorResponse | None:
        """Return the latest AdvisorResponse or None if no completed analysis.

        Returns:
            The most recent AdvisorResponse if state is completed, otherwise None.
        """
        return self._results
