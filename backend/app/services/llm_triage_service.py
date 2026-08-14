import asyncio
import json
import random
import time
from collections.abc import Callable
from datetime import timezone
from threading import RLock
from typing import Awaitable

from fastapi import BackgroundTasks
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import Settings, settings
from app.db.database import SessionLocal
from app.db.models import (
    DuplicateCandidate,
    LlmAdvisorySnapshot,
    LlmTriageRun,
    utcnow,
)
from app.llm.audit import LLMAuditStore
from app.llm.cache import LLMCache
from app.llm.provider import LLMProvider
from app.llm.runtime import get_llm_audit, get_llm_cache, get_llm_provider_factory
from app.llm.service_contracts import LLMCapability
from app.llm.services import CandidateAdvisoryService, candidate_eligibility
from app.services.llm_snapshot_service import (
    SnapshotPersistenceError,
    persist_candidate_advisory_failure,
    persist_candidate_advisory_result,
    safe_error_category,
)


TRIAGE_CAPABILITY = LLMCapability.CANDIDATE_TRIAGE
RUN_TERMINAL_STATES = frozenset({"COMPLETED", "COMPLETED_WITH_FAILURES"})
RETRYABLE_FAILURE_CATEGORIES = frozenset({
    "rate_limited", "provider_5xx", "provider_timeout", "network_failure",
})
SAFE_FAILURE_CATEGORIES = frozenset({
    "rate_limited", "provider_5xx", "provider_timeout", "network_failure",
    "invalid_provider_output", "provider_failure",
})


class _PauseBeforeAttempt(Exception):
    pass


class _AttemptFailure(Exception):
    def __init__(self, cause: Exception) -> None:
        self.cause = cause


class _RunControl:
    def __init__(self) -> None:
        self.call_lock = asyncio.Lock()
        self.state_lock = asyncio.Lock()
        self.last_call_at: float | None = None
        self.consecutive_retryable_failures = 0
        self.paused = False
        self.last_safe_error_category: str | None = None


def format_utc_timestamp(value) -> str:
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.isoformat().replace("+00:00", "Z")


def llm_provider_configured(configuration: Settings) -> bool:
    return bool(
        configuration.llm_demo_enabled
        and configuration.llm_provider == "groq"
        and configuration.groq_api_key.get_secret_value().strip()
    )


def automatic_triage_ready(configuration: Settings) -> bool:
    return bool(
        configuration.llm_auto_triage_enabled
        and llm_provider_configured(configuration)
    )


def candidate_is_triage_eligible(candidate) -> bool:
    return bool(
        candidate.business_status == "POSSIBLE_DUPLICATE_REVIEW"
        and candidate_eligibility(candidate).eligible
    )


def effective_status(
    snapshot: LlmAdvisorySnapshot | None, *, eligible: bool, queued: bool = True
) -> str:
    if snapshot is None:
        return "LLM_PENDING" if eligible and queued else "NOT_APPLICABLE"
    if snapshot.state == "FAILED":
        return "LLM_FAILED"
    if snapshot.state == "INELIGIBLE":
        return "NOT_APPLICABLE"
    if snapshot.state == "AVAILABLE":
        return {
            "SUPPORTS_DUPLICATE": "LLM_LIKELY_DUPLICATE",
            "SUPPORTS_NON_DUPLICATE": "LLM_DOWNGRADED",
            "INCONCLUSIVE": "HUMAN_REVIEW",
        }.get(snapshot.assessment, "HUMAN_REVIEW")
    return "LLM_PENDING" if eligible else "NOT_APPLICABLE"


def effective_recommended_action(status: str) -> str:
    return {
        "LLM_LIKELY_DUPLICATE": "Prioritize duplicate review",
        "LLM_DOWNGRADED": "Review non-duplicate advisory",
        "HUMAN_REVIEW": "Human review required",
        "LLM_PENDING": "Await automatic LLM triage",
        "LLM_FAILED": "Human review required; LLM triage unavailable",
        "NOT_APPLICABLE": "Use deterministic result",
    }[status]


def parse_bounded_evidence(value: str | None) -> list[str]:
    try:
        parsed = json.loads(value or "[]")
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item)[:512] for item in parsed[:10]]


def candidate_triage_fields(
    candidate, snapshot: LlmAdvisorySnapshot | None, run_state: str | None = None
) -> dict:
    eligible = candidate_is_triage_eligible(candidate)
    status = effective_status(snapshot, eligible=eligible, queued=bool(run_state))
    if snapshot is None and run_state == "FAILED":
        status = "LLM_FAILED"
    return {
        "llm_triage_state": snapshot.state if snapshot else (
            "FAILED" if run_state == "FAILED" else (
                "PENDING" if eligible and run_state else "NOT_APPLICABLE"
            )
        ),
        "llm_triage_assessment": snapshot.assessment if snapshot else None,
        "llm_triage_confidence": snapshot.confidence if snapshot else None,
        "llm_triage_recommended_action": (
            snapshot.recommended_action if snapshot else None
        ),
        "llm_triage_supporting_evidence": parse_bounded_evidence(
            snapshot.supporting_evidence if snapshot else None
        ),
        "llm_triage_conflicting_evidence": parse_bounded_evidence(
            snapshot.conflicting_evidence if snapshot else None
        ),
        "llm_triage_provider": snapshot.provider if snapshot else None,
        "llm_triage_model": snapshot.model if snapshot else None,
        "llm_triage_cache_hit": snapshot.cache_hit if snapshot else False,
        "llm_triage_generated_at": format_utc_timestamp(
            snapshot.generated_at if snapshot else None
        ),
        "effective_status": status,
        "effective_recommended_action": effective_recommended_action(status),
        "deterministic_result_authoritative": True,
    }


def eligible_candidate_ids(db: Session, scan_id: int) -> list[int]:
    candidates = (
        db.query(DuplicateCandidate)
        .filter(DuplicateCandidate.scan_id == scan_id)
        .order_by(DuplicateCandidate.id)
        .all()
    )
    return [candidate.id for candidate in candidates if candidate_is_triage_eligible(candidate)]


def get_triage_run(db: Session, scan_id: int) -> LlmTriageRun | None:
    return db.query(LlmTriageRun).filter(LlmTriageRun.scan_id == scan_id).first()


def triage_failure_categories(db: Session, scan_id: int) -> dict[str, int]:
    rows = (
        db.query(
            LlmAdvisorySnapshot.safe_error_category,
            func.count(LlmAdvisorySnapshot.id),
        )
        .join(
            DuplicateCandidate,
            DuplicateCandidate.id == LlmAdvisorySnapshot.candidate_id,
        )
        .filter(
            DuplicateCandidate.scan_id == scan_id,
            LlmAdvisorySnapshot.capability == TRIAGE_CAPABILITY.value,
            LlmAdvisorySnapshot.state == "FAILED",
            LlmAdvisorySnapshot.safe_error_category.isnot(None),
        )
        .group_by(LlmAdvisorySnapshot.safe_error_category)
        .all()
    )
    aggregated: dict[str, int] = {}
    for category, count in rows:
        safe_category = (
            str(category)
            if str(category) in SAFE_FAILURE_CATEGORIES
            else "provider_failure"
        )
        aggregated[safe_category] = aggregated.get(safe_category, 0) + int(count)
    return dict(sorted(aggregated.items()))


def prepare_triage_run(
    db: Session,
    scan_id: int,
    configuration: Settings,
    *,
    retry_failed: bool = False,
    active: bool = False,
) -> tuple[LlmTriageRun, bool]:
    candidate_ids = eligible_candidate_ids(db, scan_id)
    total = len(candidate_ids)
    cap = configuration.llm_triage_max_candidates_per_scan
    capped_candidate_ids = candidate_ids[:cap]
    run = get_triage_run(db, scan_id)
    if run is None:
        run = LlmTriageRun(scan_id=scan_id, state="QUEUED")
        db.add(run)
    run.total_eligible = total
    run.skipped_count = max(0, total - cap)
    run.updated_at = utcnow()

    should_schedule = True
    if total == 0:
        run.state = "COMPLETED"
        run.completed_at = utcnow()
        should_schedule = False
    elif active:
        should_schedule = False
    elif retry_failed:
        failed_exists = db.query(LlmAdvisorySnapshot.id).filter(
            LlmAdvisorySnapshot.candidate_id.in_(candidate_ids[:cap]),
            LlmAdvisorySnapshot.capability == TRIAGE_CAPABILITY.value,
            LlmAdvisorySnapshot.state == "FAILED",
        ).first() is not None
        should_schedule = failed_exists
        if failed_exists:
            run.state = "QUEUED"
            run.completed_at = None
    elif run.state in RUN_TERMINAL_STATES:
        # A retry-failed run may finish successfully while candidates that were
        # never attempted still have no snapshot.  Treat Start/Resume as a real
        # continuation in that case instead of leaving the scan terminal at a
        # partial processed count.
        attempted_ids = {
            candidate_id
            for (candidate_id,) in db.query(LlmAdvisorySnapshot.candidate_id)
            .filter(
                LlmAdvisorySnapshot.candidate_id.in_(capped_candidate_ids),
                LlmAdvisorySnapshot.capability == TRIAGE_CAPABILITY.value,
            )
            .all()
        } if capped_candidate_ids else set()
        if any(candidate_id not in attempted_ids for candidate_id in capped_candidate_ids):
            run.state = "QUEUED"
            run.completed_at = None
        else:
            should_schedule = False
    else:
        run.state = "QUEUED"
        run.completed_at = None

    db.commit()
    db.refresh(run)
    return run, should_schedule


def triage_run_json(
    run: LlmTriageRun, failure_categories: dict[str, int] | None = None
) -> dict:
    completed_units = run.processed_count + run.skipped_count
    progress = (
        100.0
        if run.total_eligible == 0
        else min(100.0, round(completed_units * 100 / run.total_eligible, 2))
    )
    return {
        "state": run.state,
        "total_eligible": run.total_eligible,
        "processed_count": run.processed_count,
        "likely_duplicate_count": run.likely_duplicate_count,
        "downgraded_count": run.downgraded_count,
        "human_review_count": run.human_review_count,
        "failed_count": run.failed_count,
        "skipped_count": run.skipped_count,
        "progress_percent": progress,
        "started_at": format_utc_timestamp(run.started_at),
        "completed_at": format_utc_timestamp(run.completed_at),
        "updated_at": format_utc_timestamp(run.updated_at),
        "last_safe_error_category": run.last_safe_error_category,
        "failure_categories": failure_categories or {},
    }


class LlmTriageRunner:
    def __init__(
        self,
        *,
        session_factory,
        configuration: Settings,
        cache: LLMCache,
        audit: LLMAuditStore,
        provider_factory: Callable[[Settings], LLMProvider],
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
        jitter: Callable[[float, float], float] = random.uniform,
    ) -> None:
        self.session_factory = session_factory
        self.configuration = configuration
        self.cache = cache
        self.audit = audit
        self.provider_factory = provider_factory
        self.clock = clock
        self.sleeper = sleeper
        self.jitter = jitter

    def _service(self) -> CandidateAdvisoryService:
        return CandidateAdvisoryService(
            configuration=self.configuration,
            cache=self.cache,
            audit=self.audit,
            provider_factory=self.provider_factory,
        )

    def _set_running(self, scan_id: int) -> None:
        db = self.session_factory()
        try:
            run = get_triage_run(db, scan_id)
            if run is None:
                return
            run.state = "RUNNING"
            run.started_at = run.started_at or utcnow()
            run.completed_at = None
            run.updated_at = utcnow()
            db.commit()
        finally:
            db.close()

    def _candidate_ids(self, scan_id: int, retry_failed: bool) -> list[int]:
        db = self.session_factory()
        try:
            ids = eligible_candidate_ids(db, scan_id)[
                : self.configuration.llm_triage_max_candidates_per_scan
            ]
            snapshots = db.query(LlmAdvisorySnapshot).filter(
                LlmAdvisorySnapshot.candidate_id.in_(ids),
                LlmAdvisorySnapshot.capability == TRIAGE_CAPABILITY.value,
            ).all() if ids else []
            states = {snapshot.candidate_id: snapshot.state for snapshot in snapshots}
            if retry_failed:
                return [
                    candidate_id for candidate_id in ids
                    if states.get(candidate_id) == "FAILED"
                ][: self.configuration.llm_triage_retry_batch_size]
            return [candidate_id for candidate_id in ids if candidate_id not in states]
        finally:
            db.close()

    async def _wait_for_provider_slot(self, control: _RunControl) -> None:
        async with control.call_lock:
            if control.paused:
                raise _PauseBeforeAttempt()
            interval = self.configuration.llm_triage_min_interval_ms / 1000
            if control.last_call_at is not None:
                remaining = interval - (self.clock() - control.last_call_at)
                if remaining > 0:
                    await self.sleeper(remaining)
            if control.paused:
                raise _PauseBeforeAttempt()
            control.last_call_at = self.clock()

    async def _record_retryable_failure(
        self, control: _RunControl, category: str
    ) -> bool:
        async with control.state_lock:
            control.consecutive_retryable_failures += 1
            control.last_safe_error_category = category
            if (
                control.consecutive_retryable_failures
                >= self.configuration.llm_triage_consecutive_failure_limit
            ):
                control.paused = True
            return control.paused

    async def _record_success(self, control: _RunControl) -> None:
        async with control.state_lock:
            control.consecutive_retryable_failures = 0

    def _retry_delay(self, attempt: int, exc: Exception) -> float:
        base = min(8.0, 0.5 * (2 ** attempt))
        jitter = max(0.0, self.jitter(0.0, min(0.25, base / 2)))
        retry_after = getattr(exc, "retry_after_seconds", None)
        typed_retry_after = (
            min(300.0, max(0.0, float(retry_after)))
            if isinstance(retry_after, (int, float))
            else 0.0
        )
        return min(300.0, max(base + jitter, typed_retry_after))

    async def _advise_with_retries(
        self, candidate, control: _RunControl
    ):
        for attempt in range(self.configuration.llm_triage_max_retries + 1):
            await self._wait_for_provider_slot(control)
            try:
                result = await self._service().advise(
                    candidate, capability=TRIAGE_CAPABILITY
                )
            except Exception as exc:
                category = safe_error_category(exc)
                if category not in RETRYABLE_FAILURE_CATEGORIES:
                    async with control.state_lock:
                        control.consecutive_retryable_failures = 0
                    raise _AttemptFailure(exc) from None
                paused = await self._record_retryable_failure(control, category)
                if paused or attempt >= self.configuration.llm_triage_max_retries:
                    raise _AttemptFailure(exc) from None
                await self.sleeper(self._retry_delay(attempt, exc))
                continue
            await self._record_success(control)
            return result
        raise AssertionError("bounded retry loop exhausted unexpectedly")

    async def _process_candidate(
        self, candidate_id: int, control: _RunControl
    ) -> bool:
        db = self.session_factory()
        try:
            candidate = db.query(DuplicateCandidate).filter(
                DuplicateCandidate.id == candidate_id
            ).first()
            if candidate is None:
                return False
            try:
                result = await self._advise_with_retries(candidate, control)
                persist_candidate_advisory_result(
                    db, candidate.id, result, capability=TRIAGE_CAPABILITY
                )
            except _PauseBeforeAttempt:
                return False
            except _AttemptFailure as failure:
                persist_candidate_advisory_failure(
                    db,
                    candidate.id,
                    failure.cause,
                    self.configuration,
                    capability=TRIAGE_CAPABILITY,
                )
            except SnapshotPersistenceError:
                raise
            except Exception as exc:
                persist_candidate_advisory_failure(
                    db,
                    candidate.id,
                    exc,
                    self.configuration,
                    capability=TRIAGE_CAPABILITY,
                )
            return True
        finally:
            db.close()

    def _refresh_run(self, scan_id: int, *, hard_failures: int = 0) -> None:
        db = self.session_factory()
        try:
            run = get_triage_run(db, scan_id)
            if run is None:
                return
            ids = eligible_candidate_ids(db, scan_id)[
                : self.configuration.llm_triage_max_candidates_per_scan
            ]
            snapshots = db.query(LlmAdvisorySnapshot).filter(
                LlmAdvisorySnapshot.candidate_id.in_(ids),
                LlmAdvisorySnapshot.capability == TRIAGE_CAPABILITY.value,
            ).all() if ids else []
            available = [item for item in snapshots if item.state == "AVAILABLE"]
            failed = [item for item in snapshots if item.state == "FAILED"]
            run.processed_count = len(snapshots) + hard_failures
            run.likely_duplicate_count = sum(
                item.assessment == "SUPPORTS_DUPLICATE" for item in available
            )
            run.downgraded_count = sum(
                item.assessment == "SUPPORTS_NON_DUPLICATE" for item in available
            )
            run.human_review_count = sum(
                item.assessment == "INCONCLUSIVE" for item in available
            )
            run.failed_count = len(failed) + hard_failures
            last_failed = max(failed, key=lambda item: item.updated_at) if failed else None
            run.last_safe_error_category = (
                last_failed.safe_error_category if last_failed else (
                    "snapshot_persistence_failure" if hard_failures else None
                )
            )
            run.updated_at = utcnow()
            db.commit()
        finally:
            db.close()

    def _finish(self, scan_id: int, *, hard_failures: int = 0) -> None:
        self._refresh_run(scan_id, hard_failures=hard_failures)
        db = self.session_factory()
        try:
            run = get_triage_run(db, scan_id)
            if run is None:
                return
            run.state = (
                "COMPLETED_WITH_FAILURES" if run.failed_count else "COMPLETED"
            )
            run.completed_at = utcnow()
            run.updated_at = utcnow()
            db.commit()
        finally:
            db.close()

    def _pause(
        self,
        scan_id: int,
        category: str | None,
        *,
        hard_failures: int = 0,
    ) -> None:
        self._refresh_run(scan_id, hard_failures=hard_failures)
        db = self.session_factory()
        try:
            run = get_triage_run(db, scan_id)
            if run is None:
                return
            run.state = "PAUSED"
            run.last_safe_error_category = (category or "provider_failure")[:80]
            run.completed_at = None
            run.updated_at = utcnow()
            db.commit()
        finally:
            db.close()

    def mark_failed(self, scan_id: int, category: str = "runner_failure") -> None:
        db = self.session_factory()
        try:
            run = get_triage_run(db, scan_id)
            if run is None:
                return
            run.state = "FAILED"
            run.last_safe_error_category = category[:80]
            run.completed_at = utcnow()
            run.updated_at = utcnow()
            db.commit()
        finally:
            db.close()

    async def run(self, scan_id: int, *, retry_failed: bool = False) -> None:
        self._set_running(scan_id)
        candidate_ids = self._candidate_ids(scan_id, retry_failed)
        control = _RunControl()
        queue: asyncio.Queue[int] = asyncio.Queue()
        for candidate_id in candidate_ids:
            queue.put_nowait(candidate_id)
        counter_lock = asyncio.Lock()
        hard_failures = 0

        async def worker() -> None:
            nonlocal hard_failures
            while True:
                if control.paused:
                    return
                try:
                    candidate_id = queue.get_nowait()
                except asyncio.QueueEmpty:
                    return
                try:
                    await self._process_candidate(candidate_id, control)
                except Exception:
                    hard_failures += 1
                finally:
                    queue.task_done()
                async with counter_lock:
                    self._refresh_run(scan_id, hard_failures=hard_failures)

        workers = min(self.configuration.llm_triage_concurrency, len(candidate_ids))
        if workers:
            await asyncio.gather(*(worker() for _ in range(workers)))
        if control.paused:
            self._pause(
                scan_id,
                control.last_safe_error_category,
                hard_failures=hard_failures,
            )
        else:
            self._finish(scan_id, hard_failures=hard_failures)


class LlmTriageScheduler:
    def __init__(self, runner: LlmTriageRunner) -> None:
        self.runner = runner
        self._active_scan_ids: set[int] = set()
        self._lock = RLock()

    def is_active(self, scan_id: int) -> bool:
        with self._lock:
            return scan_id in self._active_scan_ids

    async def _execute(self, scan_id: int, retry_failed: bool) -> None:
        try:
            await self.runner.run(scan_id, retry_failed=retry_failed)
        except Exception:
            self.runner.mark_failed(scan_id)
        finally:
            with self._lock:
                self._active_scan_ids.discard(scan_id)

    def schedule(
        self,
        background_tasks: BackgroundTasks,
        scan_id: int,
        *,
        retry_failed: bool = False,
    ) -> bool:
        with self._lock:
            if scan_id in self._active_scan_ids:
                return False
            self._active_scan_ids.add(scan_id)
        try:
            background_tasks.add_task(self._execute, scan_id, retry_failed)
        except Exception:
            with self._lock:
                self._active_scan_ids.discard(scan_id)
            raise
        return True


_scheduler = LlmTriageScheduler(
    LlmTriageRunner(
        session_factory=SessionLocal,
        configuration=settings,
        cache=get_llm_cache(),
        audit=get_llm_audit(),
        provider_factory=get_llm_provider_factory(),
    )
)


def get_llm_triage_scheduler() -> LlmTriageScheduler:
    return _scheduler


def schedule_automatic_triage(
    db: Session,
    background_tasks: BackgroundTasks,
    scan_id: int,
    configuration: Settings,
    scheduler: LlmTriageScheduler,
) -> LlmTriageRun | None:
    if not automatic_triage_ready(configuration):
        return None
    run, should_schedule = prepare_triage_run(
        db,
        scan_id,
        configuration,
        active=scheduler.is_active(scan_id),
    )
    if should_schedule:
        scheduler.schedule(background_tasks, scan_id)
    return run
