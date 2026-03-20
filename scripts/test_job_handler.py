"""Local simulation of ACP job handling — no Butler, no on-chain calls.

Validates the full code path:
  router.on_new_task() → handler → job.deliver()

Run with: PYTHONPATH=. uv run python scripts/test_job_handler.py
"""

import json
import sys
from dataclasses import dataclass, field

from virtuals_acp.models import ACPJobPhase, ACPMemoStatus

from src.data.cache import DataCache
from src.data.models import MarketDataCache
from src.intelligence.fear_and_greed import handle_fear_and_greed
from src.intelligence.market_analysis import handle_market_sentiment


# ---------------------------------------------------------------------------
# Minimal mock objects matching the real ACP SDK interface
# ---------------------------------------------------------------------------


@dataclass
class MockMemo:
    id: int
    status: ACPMemoStatus
    next_phase: ACPJobPhase
    type: str = "negotiation"
    sender: str = "butler"
    receiver: str = "mafia"
    signed: bool = False
    signed_approved: bool | None = None
    signed_reason: str | None = None

    def sign(self, approved: bool, reason: str) -> None:
        self.signed = True
        self.signed_approved = approved
        self.signed_reason = reason
        print(f"  ✓ memo {self.id} signed: approved={approved} reason={reason!r}")


@dataclass
class MockJob:
    id: int
    phase: ACPJobPhase
    name: str | None = None
    context: dict | None = None
    memos: list = field(default_factory=list)

    # Tracking
    accepted: bool = False
    accepted_reason: str | None = None
    rejected: bool = False
    rejected_reason: str | None = None
    deliveries: list[str] = field(default_factory=list)
    requirements_created: list[str] = field(default_factory=list)

    def get_service_name(self) -> str | None:
        return self.name

    def accept(self, reason: str) -> None:
        self.accepted = True
        self.accepted_reason = reason
        print(f"  ✓ job {self.id} accepted: {reason!r}")

    def reject(self, reason: str) -> None:
        self.rejected = True
        self.rejected_reason = reason
        print(f"  ✗ job {self.id} rejected: {reason!r}")

    def deliver(self, payload: str) -> None:
        self.deliveries.append(payload)
        data = json.loads(payload)
        print(f"  ✓ job {self.id} delivered ({len(payload)} bytes)")
        print(f"    keys: {list(data.keys())}")

    def create_requirement(self, message: str) -> None:
        self.requirements_created.append(message)
        print(f"  ✓ job {self.id} requirement created: {message!r}")


class MockAcpClient:
    """Minimal stand-in for VirtualsACP — just needs to survive getattr calls."""
    def get_job_by_onchain_id(self, job_id: int) -> MockJob:
        raise NotImplementedError("Not needed in simulation")


# ---------------------------------------------------------------------------
# Simulation helpers
# ---------------------------------------------------------------------------


def _make_cache_with_data() -> DataCache:
    """Return a DataCache pre-loaded with realistic market data."""
    cache = DataCache()
    cache._data = MarketDataCache(
        fg_value=32,
        fg_classification="fear",
        fg_change_24h=-3.5,
        fg_change_7d=-8.0,
        fg_change_30d=-15.0,
        btc_price=82000.0,
        btc_change_24h=-2.1,
        btc_change_7d=-5.4,
        btc_dominance=58.2,
        btc_dominance_change_24h=0.4,
        btc_dominance_change_7d=1.8,
        btc_volume_24h=28_500_000_000,
        btc_volume_change_24h=12.0,
        eth_price=1800.0,
        eth_change_24h=-3.2,
        eth_change_7d=-7.1,
        eth_volume_24h=9_200_000_000,
        eth_volume_change_24h=8.5,
        sol_price=120.0,
        sol_change_24h=-4.0,
        sol_change_7d=-9.3,
        sol_volume_24h=3_100_000_000,
        sol_volume_change_24h=5.2,
        total_market_cap=2_800_000_000_000,
        total_market_cap_change_24h=-2.5,
        total_market_cap_change_7d=-6.0,
        total_volume_24h=85_000_000_000,
    )
    cache._initialized = True
    return cache


def _check(label: str, condition: bool) -> None:
    icon = "✓" if condition else "✗"
    status = "PASS" if condition else "FAIL"
    print(f"  {icon} [{status}] {label}")
    if not condition:
        sys.exit(1)


# ---------------------------------------------------------------------------
# Test: fear_and_greed — REQUEST → accept (no polling since no real ACP client)
# ---------------------------------------------------------------------------


def test_fear_and_greed_request():
    print("\n=== fear_and_greed | REQUEST phase ===")
    cache = _make_cache_with_data()
    job = MockJob(
        id=9001,
        phase=ACPJobPhase.REQUEST,
        name="fear_and_greed",
    )
    memo = MockMemo(
        id=1001,
        status=ACPMemoStatus.PENDING,
        next_phase=ACPJobPhase.NEGOTIATION,
    )

    handle_fear_and_greed(job, memo, cache, MockAcpClient())

    _check("job was accepted", job.accepted)
    _check("memo not signed (accept is separate from signing)", not memo.signed)
    _check("job not rejected", not job.rejected)


# ---------------------------------------------------------------------------
# Test: fear_and_greed — NEGOTIATION (pending memo → sign)
# ---------------------------------------------------------------------------


def test_fear_and_greed_negotiation():
    print("\n=== fear_and_greed | NEGOTIATION phase ===")
    cache = _make_cache_with_data()
    job = MockJob(id=9002, phase=ACPJobPhase.NEGOTIATION, name="fear_and_greed")
    memo = MockMemo(
        id=1002,
        status=ACPMemoStatus.PENDING,
        next_phase=ACPJobPhase.TRANSACTION,
    )

    handle_fear_and_greed(job, memo, cache, MockAcpClient())

    _check("memo was signed", memo.signed)
    _check("memo approved=True", memo.signed_approved is True)


# ---------------------------------------------------------------------------
# Test: fear_and_greed — TRANSACTION → deliver
# ---------------------------------------------------------------------------


def test_fear_and_greed_transaction():
    print("\n=== fear_and_greed | TRANSACTION phase ===")
    cache = _make_cache_with_data()
    job = MockJob(id=9003, phase=ACPJobPhase.TRANSACTION, name="fear_and_greed")

    handle_fear_and_greed(job, None, cache, MockAcpClient())

    _check("delivery was made", len(job.deliveries) == 1)
    payload = json.loads(job.deliveries[0])
    _check("has fear_and_greed field", "fear_and_greed" in payload)
    _check("has classification", "classification" in payload)
    _check("has regime", "regime" in payload)
    _check("has source=coinmarketcap", payload.get("source") == "coinmarketcap")
    _check("f&g value is int", isinstance(payload["fear_and_greed"], int))
    print(f"    fear_and_greed={payload['fear_and_greed']} ({payload['classification']})")
    print(f"    regime={payload['regime']}")


# ---------------------------------------------------------------------------
# Test: fear_and_greed — TRANSACTION deduplication
# ---------------------------------------------------------------------------


def test_fear_and_greed_dedup():
    print("\n=== fear_and_greed | TRANSACTION deduplication ===")
    cache = _make_cache_with_data()
    job = MockJob(id=9004, phase=ACPJobPhase.TRANSACTION, name="fear_and_greed")

    handle_fear_and_greed(job, None, cache, MockAcpClient())
    handle_fear_and_greed(job, None, cache, MockAcpClient())

    _check("delivered exactly once (not twice)", len(job.deliveries) == 1)


# ---------------------------------------------------------------------------
# Test: market_sentiment — TRANSACTION → deliver (no LLM)
# ---------------------------------------------------------------------------


def test_market_sentiment_transaction():
    print("\n=== market_sentiment | TRANSACTION phase (include_analysis=False) ===")
    cache = _make_cache_with_data()
    job = MockJob(
        id=9005,
        phase=ACPJobPhase.TRANSACTION,
        name="market_sentiment",
        context={"requirement": {"include_analysis": False, "focus_assets": ["BTC", "ETH", "SOL"]}},
    )

    handle_market_sentiment(job, None, cache, MockAcpClient())

    _check("delivery was made", len(job.deliveries) == 1)
    payload = json.loads(job.deliveries[0])
    for key in ("fear_and_greed", "btc_dominance", "rotation_signal", "assets", "regimes", "source"):
        _check(f"has '{key}' field", key in payload)
    _check("source=mafia_terminal", payload.get("source") == "mafia_terminal")
    _check("has 3 assets", len(payload["assets"]) == 3)
    _check("analysis=None (excluded)", payload.get("analysis") is None)
    print(f"    f&g={payload['fear_and_greed']['value']} ({payload['fear_and_greed']['classification']})")
    print(f"    rotation={payload['rotation_signal']['type']}")


# ---------------------------------------------------------------------------
# Test: market_sentiment — EVALUATION (sign memo)
# ---------------------------------------------------------------------------


def test_market_sentiment_evaluation():
    print("\n=== market_sentiment | EVALUATION phase ===")
    cache = _make_cache_with_data()
    job = MockJob(id=9006, phase=ACPJobPhase.EVALUATION, name="market_sentiment")
    memo = MockMemo(
        id=1006,
        status=ACPMemoStatus.PENDING,
        next_phase=ACPJobPhase.COMPLETED,
    )

    handle_market_sentiment(job, memo, cache, MockAcpClient())

    _check("memo was signed", memo.signed)
    _check("memo approved=True", memo.signed_approved is True)


# ---------------------------------------------------------------------------
# Run all tests
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    print("=" * 60)
    print("MAFIA ACP — Local Job Handler Simulation")
    print("=" * 60)

    test_fear_and_greed_request()
    test_fear_and_greed_negotiation()
    test_fear_and_greed_transaction()
    test_fear_and_greed_dedup()
    test_market_sentiment_transaction()
    test_market_sentiment_evaluation()

    print("\n" + "=" * 60)
    print("All simulations passed ✓")
    print("=" * 60)
