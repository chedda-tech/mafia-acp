"""Regression tests for router service resolution and memo-optional handling."""

from __future__ import annotations

import json

from virtuals_acp.models import ACPJobPhase, ACPMemoStatus

from src.agent.router import JobRouter
from src.data.cache import DataCache
from src.intelligence.fear_and_greed import handle_fear_and_greed
from src.intelligence.market_analysis import handle_market_sentiment


class DummyJob:
    def __init__(
        self,
        *,
        job_id: int = 1,
        phase: ACPJobPhase = ACPJobPhase.REQUEST,
        name: str | None = None,
        context: dict | None = None,
        service_name_from_method: str | None = None,
    ) -> None:
        self.id = job_id
        self.phase = phase
        self.name = name
        self.context = context
        self._service_name_from_method = service_name_from_method
        self.rejected_reason: str | None = None
        self.deliveries: list[str] = []

    def get_service_name(self) -> str | None:
        return self._service_name_from_method

    def reject(self, reason: str) -> None:
        self.rejected_reason = reason

    def accept(self, reason: str) -> None:
        _ = reason

    def deliver(self, payload: str) -> None:
        self.deliveries.append(payload)


class DummyMemo:
    def __init__(
        self,
        *,
        memo_id: int = 1,
        status: ACPMemoStatus = ACPMemoStatus.PENDING,
        next_phase: ACPJobPhase = ACPJobPhase.NEGOTIATION,
    ) -> None:
        self.id = memo_id
        self.status = status
        self.next_phase = next_phase
        self.signed = False

    def sign(self, approved: bool, reason: str) -> None:
        _ = approved
        _ = reason
        self.signed = True


def _make_router() -> JobRouter:
    router = JobRouter(data_cache=DataCache())
    router.set_acp_client(object())
    return router


def test_router_uses_get_service_name_when_available() -> None:
    router = _make_router()
    calls: list[str] = []

    def handler(job, memo_to_sign, cache, client):
        _ = memo_to_sign
        _ = cache
        _ = client
        calls.append(str(job.id))

    router.register_handler("fear_and_greed", handler)

    job = DummyJob(
        job_id=101,
        phase=ACPJobPhase.TRANSACTION,
        name=None,
        service_name_from_method="fear_and_greed",
    )

    router.on_new_task(job, memo_to_sign=None)

    assert calls == ["101"]
    assert job.rejected_reason is None


def test_router_unknown_service_non_actionable_does_not_reject() -> None:
    router = _make_router()

    job = DummyJob(job_id=102, phase=ACPJobPhase.TRANSACTION, name=None)
    memo = DummyMemo(status=ACPMemoStatus.APPROVED, next_phase=ACPJobPhase.EVALUATION)

    router.on_new_task(job, memo_to_sign=memo)

    assert job.rejected_reason is None


def test_router_unknown_service_actionable_request_rejects() -> None:
    router = _make_router()

    job = DummyJob(job_id=103, phase=ACPJobPhase.REQUEST, name=None)
    memo = DummyMemo(status=ACPMemoStatus.PENDING, next_phase=ACPJobPhase.NEGOTIATION)

    router.on_new_task(job, memo_to_sign=memo)

    assert job.rejected_reason == "Unknown service: unknown"


def test_router_unknown_service_actionable_non_request_does_not_reject() -> None:
    router = _make_router()

    job = DummyJob(job_id=106, phase=ACPJobPhase.TRANSACTION, name=None)
    memo = DummyMemo(status=ACPMemoStatus.PENDING, next_phase=ACPJobPhase.EVALUATION)

    router.on_new_task(job, memo_to_sign=memo)

    assert job.rejected_reason is None


def test_market_sentiment_handles_none_memo_in_transaction() -> None:
    cache = DataCache()
    job = DummyJob(
        job_id=104,
        phase=ACPJobPhase.TRANSACTION,
        context={"requirement": {"include_analysis": False, "focus_assets": ["BTC"]}},
    )

    handle_market_sentiment(job, None, cache, object())

    assert len(job.deliveries) == 1
    delivered = json.loads(job.deliveries[0])
    assert "fear_and_greed" in delivered


def test_market_sentiment_handles_none_memo_non_transaction() -> None:
    cache = DataCache()
    job = DummyJob(job_id=105, phase=ACPJobPhase.REQUEST, context={})

    handle_market_sentiment(job, None, cache, object())

    assert job.deliveries == []


def test_fear_and_greed_signs_pending_negotiation_memo() -> None:
    cache = DataCache()
    job = DummyJob(job_id=107, phase=ACPJobPhase.NEGOTIATION, context={})
    memo = DummyMemo(status=ACPMemoStatus.PENDING, next_phase=ACPJobPhase.TRANSACTION)

    handle_fear_and_greed(job, memo, cache, object())

    assert memo.signed is True


def test_actionable_memo_dedupes_across_router_instances() -> None:
    cache = DataCache()
    router_a = JobRouter(data_cache=cache)
    router_b = JobRouter(data_cache=cache)
    router_a.set_acp_client(object())
    router_b.set_acp_client(object())

    calls: list[int] = []

    def handler(job, memo_to_sign, cache_arg, client_arg):
        _ = memo_to_sign
        _ = cache_arg
        _ = client_arg
        calls.append(int(job.id))

    router_a.register_handler("fear_and_greed", handler)
    router_b.register_handler("fear_and_greed", handler)

    job = DummyJob(job_id=108, phase=ACPJobPhase.REQUEST, name="fear_and_greed")
    memo = DummyMemo(memo_id=2001, status=ACPMemoStatus.PENDING, next_phase=ACPJobPhase.NEGOTIATION)

    router_a.on_new_task(job, memo_to_sign=memo)
    router_b.on_new_task(job, memo_to_sign=memo)

    assert calls == [108]
