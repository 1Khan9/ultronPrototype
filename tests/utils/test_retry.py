"""Tests for ultron.utils.retry."""

from __future__ import annotations

import asyncio
import time

import pytest

from ultron.utils import retry as r


# ---------------------------------------------------------------------------
# parse_retry_after
# ---------------------------------------------------------------------------

class TestParseRetryAfter:
    def test_delta_seconds_returns_value(self) -> None:
        assert r.parse_retry_after("5", now_unix=1000.0) == 5.0

    def test_zero_returns_zero(self) -> None:
        assert r.parse_retry_after("0", now_unix=1000.0) == 0.0

    def test_unix_timestamp_returns_delta(self) -> None:
        out = r.parse_retry_after("2000", now_unix=1000.0)
        assert out == 1000.0

    def test_negative_returns_none(self) -> None:
        assert r.parse_retry_after("-1", now_unix=1000.0) is None

    def test_garbage_returns_none(self) -> None:
        assert r.parse_retry_after("not-a-number") is None

    def test_empty_returns_none(self) -> None:
        assert r.parse_retry_after("") is None
        assert r.parse_retry_after("   ") is None

    def test_none_returns_none(self) -> None:
        assert r.parse_retry_after(None) is None  # type: ignore[arg-type]

    def test_unix_in_past_returns_delta_seconds(self) -> None:
        # If the parsed integer is less than current unix time it is treated
        # as delta-seconds, not as an already-elapsed timestamp.
        out = r.parse_retry_after("60", now_unix=1_000_000_000.0)
        assert out == 60.0


# ---------------------------------------------------------------------------
# RetriableError
# ---------------------------------------------------------------------------

class TestRetriableError:
    def test_default_status_is_429(self) -> None:
        err = r.RetriableError()
        assert err.status == 429
        assert err.retry_after is None

    def test_carries_retry_after_and_headers(self) -> None:
        err = r.RetriableError(retry_after=2.5, headers={"Retry-After": "3"})
        assert err.retry_after == 2.5
        assert err.headers["Retry-After"] == "3"


# ---------------------------------------------------------------------------
# RetryBudget
# ---------------------------------------------------------------------------

class TestRetryBudget:
    def test_initial_remaining_is_limit(self) -> None:
        budget = r.RetryBudget(limit_seconds=10.0)
        assert budget.remaining() == 10.0

    def test_charge_consumes_budget(self) -> None:
        budget = r.RetryBudget(limit_seconds=10.0)
        budget.charge(3.5)
        assert budget.remaining() == 6.5

    def test_charge_ignores_negative(self) -> None:
        budget = r.RetryBudget(limit_seconds=10.0)
        budget.charge(-2.0)
        assert budget.remaining() == 10.0

    def test_remaining_floors_at_zero(self) -> None:
        budget = r.RetryBudget(limit_seconds=2.0)
        budget.charge(5.0)
        assert budget.remaining() == 0.0

    def test_reset_clears_consumption(self) -> None:
        budget = r.RetryBudget(limit_seconds=10.0)
        budget.charge(7.0)
        budget.reset()
        assert budget.remaining() == 10.0


# ---------------------------------------------------------------------------
# Backoff arithmetic
# ---------------------------------------------------------------------------

class TestBackoffSeconds:
    def test_zero_attempt(self) -> None:
        assert r._backoff_seconds(0, 1.0, 10.0) == 1.0

    def test_geometric_growth(self) -> None:
        assert r._backoff_seconds(1, 1.0, 10.0) == 2.0
        assert r._backoff_seconds(2, 1.0, 10.0) == 4.0
        assert r._backoff_seconds(3, 1.0, 10.0) == 8.0

    def test_capped_at_max_delay(self) -> None:
        assert r._backoff_seconds(5, 1.0, 5.0) == 5.0

    def test_negative_attempt_treated_as_zero(self) -> None:
        assert r._backoff_seconds(-3, 1.0, 10.0) == 1.0

    def test_jitter_within_bounds(self) -> None:
        # Random by design — verify the bounds.
        for _ in range(20):
            out = r._backoff_seconds(2, 1.0, 10.0, jitter=0.5)
            base = 4.0  # 1 * 2 ** 2
            assert 0.5 * base <= out <= 1.5 * base


# ---------------------------------------------------------------------------
# _is_rate_limit
# ---------------------------------------------------------------------------

class TestIsRateLimit:
    def test_retriable_error(self) -> None:
        assert r._is_rate_limit(r.RetriableError()) is True

    def test_status_429(self) -> None:
        class E(Exception):
            status = 429
        assert r._is_rate_limit(E()) is True

    def test_status_code_429(self) -> None:
        class E(Exception):
            status_code = 429
        assert r._is_rate_limit(E()) is True

    def test_response_status_code_429(self) -> None:
        class Response:
            status_code = 429

        class E(Exception):
            response = Response()
        assert r._is_rate_limit(E()) is True

    def test_normal_exception(self) -> None:
        assert r._is_rate_limit(ValueError("x")) is False


# ---------------------------------------------------------------------------
# Extract retry-after from exception
# ---------------------------------------------------------------------------

class TestExtractRetryAfterFromException:
    def test_explicit_retry_after_attribute(self) -> None:
        err = r.RetriableError(retry_after=3.0)
        assert r._extract_retry_after_from_exception(err) == 3.0

    def test_header_lookup_case_insensitive(self) -> None:
        err = r.RetriableError(headers={"Retry-After": "4"})
        out = r._extract_retry_after_from_exception(err)
        assert out == 4.0

    def test_response_headers_lookup(self) -> None:
        class Response:
            headers = {"X-Ratelimit-Reset": "7"}

        class E(Exception):
            response = Response()

        out = r._extract_retry_after_from_exception(E())
        assert out == 7.0

    def test_no_retry_after_returns_none(self) -> None:
        assert r._extract_retry_after_from_exception(ValueError("x")) is None


# ---------------------------------------------------------------------------
# Async with_retry: coroutine
# ---------------------------------------------------------------------------

class TestWithRetryCoroutine:
    def test_succeeds_first_attempt(self) -> None:
        async def main() -> int:
            @r.with_retry(max_attempts=3, base_delay_s=0.0, max_delay_s=0.0)
            async def f() -> int:
                return 42
            return await f()
        assert asyncio.run(main()) == 42

    def test_retries_rate_limit_then_succeeds(self) -> None:
        calls = []

        async def main() -> int:
            @r.with_retry(max_attempts=3, base_delay_s=0.0, max_delay_s=0.0)
            async def f() -> int:
                calls.append(len(calls))
                if len(calls) < 3:
                    raise r.RetriableError("nope")
                return 100
            return await f()

        assert asyncio.run(main()) == 100
        assert len(calls) == 3

    def test_max_attempts_exhausted_raises(self) -> None:
        async def main() -> None:
            @r.with_retry(max_attempts=2, base_delay_s=0.0, max_delay_s=0.0)
            async def f() -> None:
                raise r.RetriableError("never recovers")
            await f()

        with pytest.raises(r.RetriableError):
            asyncio.run(main())

    def test_non_retriable_error_propagates_immediately(self) -> None:
        attempts: list[int] = []

        async def main() -> None:
            @r.with_retry(max_attempts=5, base_delay_s=0.0, max_delay_s=0.0)
            async def f() -> None:
                attempts.append(1)
                raise ValueError("normal")
            await f()

        with pytest.raises(ValueError):
            asyncio.run(main())
        assert len(attempts) == 1

    def test_retry_all_treats_every_exception_as_retryable(self) -> None:
        attempts: list[int] = []

        async def main() -> int:
            @r.with_retry(
                max_attempts=3, base_delay_s=0.0, max_delay_s=0.0, retry_all=True,
            )
            async def f() -> int:
                attempts.append(1)
                if len(attempts) < 3:
                    raise ValueError("transient")
                return 7
            return await f()

        assert asyncio.run(main()) == 7
        assert len(attempts) == 3

    def test_custom_should_retry_overrides_default(self) -> None:
        attempts: list[int] = []

        def custom(_err: BaseException) -> bool:
            return True

        async def main() -> int:
            @r.with_retry(
                max_attempts=2, base_delay_s=0.0, max_delay_s=0.0,
                should_retry=custom,
            )
            async def f() -> int:
                attempts.append(1)
                if len(attempts) < 2:
                    raise TypeError("transient")
                return 1
            return await f()

        assert asyncio.run(main()) == 1
        assert len(attempts) == 2

    def test_on_retry_callback_fires_with_record(self) -> None:
        attempts: list[r.RetryAttempt] = []

        async def main() -> int:
            @r.with_retry(
                max_attempts=3, base_delay_s=0.0, max_delay_s=0.0,
                on_retry=lambda rec: attempts.append(rec),
            )
            async def f() -> int:
                if len(attempts) < 2:
                    raise r.RetriableError("again")
                return 99
            return await f()

        assert asyncio.run(main()) == 99
        assert len(attempts) == 2
        first = attempts[0]
        assert first.attempt == 1 and first.max_attempts == 3
        assert first.error_class == "RetriableError"

    def test_on_retry_async_callback(self) -> None:
        attempts: list[r.RetryAttempt] = []

        async def on_retry(rec: r.RetryAttempt) -> None:
            attempts.append(rec)

        async def main() -> int:
            @r.with_retry(
                max_attempts=3, base_delay_s=0.0, max_delay_s=0.0, on_retry=on_retry,
            )
            async def f() -> int:
                if len(attempts) < 1:
                    raise r.RetriableError("again")
                return 1
            return await f()

        assert asyncio.run(main()) == 1
        assert len(attempts) == 1

    def test_on_retry_callback_exception_does_not_break_retry(self) -> None:
        def boom(_: r.RetryAttempt) -> None:
            raise RuntimeError("callback failure")

        async def main() -> int:
            @r.with_retry(
                max_attempts=3, base_delay_s=0.0, max_delay_s=0.0, on_retry=boom,
            )
            async def f() -> int:
                if not getattr(f, "called", False):
                    f.called = True  # type: ignore[attr-defined]
                    raise r.RetriableError("once")
                return 1
            return await f()

        assert asyncio.run(main()) == 1

    def test_budget_exhaustion_propagates(self) -> None:
        budget = r.RetryBudget(limit_seconds=0.001)
        budget.charge(0.001)
        attempts: list[int] = []

        async def main() -> int:
            @r.with_retry(
                max_attempts=4, base_delay_s=1.0, max_delay_s=10.0, budget=budget,
            )
            async def f() -> int:
                attempts.append(1)
                raise r.RetriableError("nope")
            return await f()

        with pytest.raises(r.RetriableError):
            asyncio.run(main())
        assert len(attempts) == 1

    def test_retry_after_header_clips_backoff(self) -> None:
        recorded: list[float] = []

        def on_retry(rec: r.RetryAttempt) -> None:
            recorded.append(rec.delay_seconds)

        async def main() -> int:
            @r.with_retry(
                max_attempts=3, base_delay_s=10.0, max_delay_s=10.0,
                on_retry=on_retry,
            )
            async def f() -> int:
                if not getattr(f, "called", False):
                    f.called = True  # type: ignore[attr-defined]
                    raise r.RetriableError(headers={"Retry-After": "0"})
                return 1
            return await f()

        assert asyncio.run(main()) == 1
        # retry-after was 0 so the recorded delay should be 0 even though
        # the geometric backoff would have been 10s.
        assert recorded == [0.0]

    def test_cancelled_error_propagates_immediately(self) -> None:
        attempts: list[int] = []

        async def main() -> None:
            @r.with_retry(max_attempts=5, base_delay_s=0.0, max_delay_s=0.0)
            async def f() -> None:
                attempts.append(1)
                raise asyncio.CancelledError()
            await f()

        with pytest.raises(asyncio.CancelledError):
            asyncio.run(main())
        assert len(attempts) == 1


# ---------------------------------------------------------------------------
# Async with_retry: async generator
# ---------------------------------------------------------------------------

class TestWithRetryAsyncGenerator:
    def test_yields_after_retry(self) -> None:
        seen: list[int] = []

        async def main() -> None:
            attempts: list[int] = []

            @r.with_retry(max_attempts=3, base_delay_s=0.0, max_delay_s=0.0)
            async def gen():
                attempts.append(1)
                if len(attempts) < 2:
                    raise r.RetriableError("first")
                yield 1
                yield 2
                yield 3

            async for value in gen():
                seen.append(value)

        asyncio.run(main())
        assert seen == [1, 2, 3]

    def test_async_generator_max_attempts_exhausted(self) -> None:
        async def main() -> None:
            @r.with_retry(max_attempts=2, base_delay_s=0.0, max_delay_s=0.0)
            async def gen():
                raise r.RetriableError("nope")
                yield  # pragma: no cover

            async for _ in gen():
                pass

        with pytest.raises(r.RetriableError):
            asyncio.run(main())


# ---------------------------------------------------------------------------
# with_retry_sync
# ---------------------------------------------------------------------------

class TestWithRetrySync:
    def test_succeeds_first_attempt(self) -> None:
        @r.with_retry_sync(max_attempts=3, base_delay_s=0.0, max_delay_s=0.0)
        def f() -> int:
            return 7
        assert f() == 7

    def test_retries_rate_limit(self) -> None:
        attempts: list[int] = []

        @r.with_retry_sync(max_attempts=3, base_delay_s=0.0, max_delay_s=0.0)
        def f() -> int:
            attempts.append(1)
            if len(attempts) < 2:
                raise r.RetriableError("once")
            return 11

        assert f() == 11
        assert len(attempts) == 2

    def test_non_retriable_propagates(self) -> None:
        attempts: list[int] = []

        @r.with_retry_sync(max_attempts=4, base_delay_s=0.0, max_delay_s=0.0)
        def f() -> int:
            attempts.append(1)
            raise ValueError("normal")

        with pytest.raises(ValueError):
            f()
        assert len(attempts) == 1

    def test_on_retry_callback(self) -> None:
        records: list[r.RetryAttempt] = []

        @r.with_retry_sync(
            max_attempts=3, base_delay_s=0.0, max_delay_s=0.0,
            on_retry=lambda rec: records.append(rec),
        )
        def f() -> int:
            if not getattr(f, "called", False):
                f.called = True  # type: ignore[attr-defined]
                raise r.RetriableError("once")
            return 1

        assert f() == 1
        assert len(records) == 1
        assert records[0].error_class == "RetriableError"

    def test_budget_exhaustion(self) -> None:
        budget = r.RetryBudget(limit_seconds=0.001)
        budget.charge(0.001)

        @r.with_retry_sync(
            max_attempts=5, base_delay_s=1.0, max_delay_s=5.0, budget=budget,
        )
        def f() -> int:
            raise r.RetriableError("nope")

        with pytest.raises(r.RetriableError):
            f()


# ---------------------------------------------------------------------------
# retry_iterable_keys helper
# ---------------------------------------------------------------------------

class TestRetryIterableKeys:
    def test_extracts_known_keys(self) -> None:
        out = list(r.retry_iterable_keys({
            "Retry-After": "5",
            "Other": "x",
        }))
        assert out == [("retry-after", "5")]

    def test_priority_order(self) -> None:
        out = list(r.retry_iterable_keys({
            "X-Ratelimit-Reset": "9",
            "Retry-After": "3",
        }))
        # retry-after wins on priority order.
        assert out[0] == ("retry-after", "3")

    def test_empty_input(self) -> None:
        assert list(r.retry_iterable_keys({})) == []


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class TestValidation:
    def test_max_attempts_zero_rejected(self) -> None:
        with pytest.raises(ValueError):
            r.with_retry(max_attempts=0)

    def test_negative_delays_rejected(self) -> None:
        with pytest.raises(ValueError):
            r.with_retry(base_delay_s=-1.0)
        with pytest.raises(ValueError):
            r.with_retry(max_delay_s=-1.0)

    def test_sync_max_attempts_zero_rejected(self) -> None:
        with pytest.raises(ValueError):
            r.with_retry_sync(max_attempts=0)

    def test_with_retry_on_sync_function_raises(self) -> None:
        with pytest.raises(TypeError):
            @r.with_retry(max_attempts=2)
            def f() -> int:  # pragma: no cover
                return 1
