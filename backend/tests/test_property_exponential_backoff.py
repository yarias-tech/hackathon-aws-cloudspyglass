"""Property-based tests for exponential backoff calculation.

**Validates: Requirements 3.4**

Property 5: Exponential backoff calculation
- For any retry number n in the range [1, 5], the delay equals min(2^(n-1), 30)
- The delay is always >= 1 second (minimum retry is 1, 2^0 = 1)
- The delay never exceeds MAX_BACKOFF_SECONDS (30)
- The delay sequence is monotonically non-decreasing
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from backend.services.scanner import MAX_BACKOFF_SECONDS, MAX_RETRIES, calculate_backoff_delay


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Strategy: valid retry numbers (1 through MAX_RETRIES)
retry_number_strategy = st.integers(min_value=1, max_value=MAX_RETRIES)

# Strategy: pairs of consecutive retry numbers for monotonicity check
consecutive_retry_strategy = st.integers(min_value=1, max_value=MAX_RETRIES - 1)


# ---------------------------------------------------------------------------
# Property: Delay equals min(2^(n-1), 30) for any valid retry number
# ---------------------------------------------------------------------------

class TestBackoffFormulaCorrectness:
    """The backoff delay matches the formula min(2^(n-1), MAX_BACKOFF_SECONDS)."""

    @given(n=retry_number_strategy)
    @settings(max_examples=50)
    def test_delay_matches_formula(self, n: int) -> None:
        """For any retry n in [1, 5], delay == min(2^(n-1), 30).

        This verifies the core exponential backoff calculation produces
        the expected value for all valid retry numbers.
        """
        expected = min(2 ** (n - 1), MAX_BACKOFF_SECONDS)
        actual = calculate_backoff_delay(n)
        assert actual == expected, (
            f"For retry {n}: expected delay={expected}, got {actual}"
        )


# ---------------------------------------------------------------------------
# Property: Delay is always >= 1 second
# ---------------------------------------------------------------------------

class TestBackoffMinimumDelay:
    """The backoff delay is always at least 1 second."""

    @given(n=retry_number_strategy)
    @settings(max_examples=50)
    def test_delay_is_at_least_one_second(self, n: int) -> None:
        """For any valid retry number, the delay is >= 1 second.

        Since the minimum retry is 1 and 2^(1-1) = 2^0 = 1, the delay
        should never be less than 1 second.
        """
        delay = calculate_backoff_delay(n)
        assert delay >= 1, (
            f"For retry {n}: expected delay >= 1, got {delay}"
        )


# ---------------------------------------------------------------------------
# Property: Delay never exceeds MAX_BACKOFF_SECONDS
# ---------------------------------------------------------------------------

class TestBackoffMaximumDelay:
    """The backoff delay never exceeds MAX_BACKOFF_SECONDS (30)."""

    @given(n=retry_number_strategy)
    @settings(max_examples=50)
    def test_delay_never_exceeds_max(self, n: int) -> None:
        """For any valid retry number, the delay is capped at MAX_BACKOFF_SECONDS.

        The min() in the formula ensures the delay cannot grow unbounded.
        """
        delay = calculate_backoff_delay(n)
        assert delay <= MAX_BACKOFF_SECONDS, (
            f"For retry {n}: expected delay <= {MAX_BACKOFF_SECONDS}, got {delay}"
        )


# ---------------------------------------------------------------------------
# Property: Delay sequence is monotonically non-decreasing
# ---------------------------------------------------------------------------

class TestBackoffMonotonicity:
    """The backoff delay sequence is monotonically non-decreasing."""

    @given(n=consecutive_retry_strategy)
    @settings(max_examples=50)
    def test_delay_is_non_decreasing(self, n: int) -> None:
        """For consecutive retries n and n+1, delay(n+1) >= delay(n).

        Exponential backoff should never decrease between consecutive attempts.
        """
        delay_n = calculate_backoff_delay(n)
        delay_next = calculate_backoff_delay(n + 1)
        assert delay_next >= delay_n, (
            f"Delay decreased between retry {n} ({delay_n}s) "
            f"and retry {n + 1} ({delay_next}s)"
        )


# ---------------------------------------------------------------------------
# Property: Known expected values for each retry number
# ---------------------------------------------------------------------------

class TestBackoffExpectedValues:
    """The backoff produces exact expected values for the known retry range."""

    @given(data=st.data())
    @settings(max_examples=20)
    def test_expected_delay_values(self, data) -> None:
        """Verify the specific expected values for retries 1 through 5.

        Expected: retry 1 → 1s, retry 2 → 2s, retry 3 → 4s,
                  retry 4 → 8s, retry 5 → 16s
        """
        expected_values = {1: 1, 2: 2, 3: 4, 4: 8, 5: 16}
        n = data.draw(st.sampled_from(list(expected_values.keys())))
        delay = calculate_backoff_delay(n)
        assert delay == expected_values[n], (
            f"For retry {n}: expected {expected_values[n]}s, got {delay}s"
        )
