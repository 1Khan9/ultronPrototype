"""StreamElementsLedger -- the SE-points-backed economy adapter (2026-06-26).

Drives the adapter against a FAKE SE client (an in-memory points dict) so the
ledger semantics -- uid->login mapping, idempotency (no double-apply on replay),
and InsufficientFunds -- are verified without touching the live API.
"""
import pytest

from kenning.twitch.economy.ledger import InsufficientFunds
from kenning.twitch.economy.streamelements import (
    StreamElementsLedger, SEPointsError,
)


class _FakeSE:
    """Mimics SEPointsClient: points keyed by lowercase login."""

    def __init__(self):
        self.points: dict[str, int] = {}
        self.calls: list[tuple] = []

    def get_points(self, login: str) -> int:
        self.calls.append(("get", login.lower()))
        return int(self.points.get(login.lower(), 0))

    def add_points(self, login: str, delta: int) -> int:
        self.calls.append(("add", login.lower(), int(delta)))
        new = int(self.points.get(login.lower(), 0)) + int(delta)
        self.points[login.lower()] = new
        return new

    def top(self, limit: int = 100) -> list:
        ranked = sorted(self.points.items(), key=lambda kv: kv[1], reverse=True)
        return ranked[:limit]


@pytest.fixture
def led(tmp_path):
    client = _FakeSE()
    ledger = StreamElementsLedger(client, str(tmp_path / "se.db"))
    return ledger, client


def test_register_then_balance(led):
    ledger, client = led
    assert ledger.balance("uid1") == 0           # unregistered -> 0, no API call
    ledger.register("uid1", "Viewer1")
    client.points["viewer1"] = 250
    assert ledger.balance("uid1") == 250         # resolves uid->login (lowercased)


def test_credit_then_debit(led):
    ledger, client = led
    ledger.register("u", "bob")
    assert ledger.credit("u", 100, "earn", "k1") == 100
    assert ledger.balance("u") == 100
    assert ledger.debit("u", 30, "gamble", "k2") == 70
    assert client.points["bob"] == 70


def test_credit_is_idempotent_on_key(led):
    ledger, _ = led
    ledger.register("u", "bob")
    assert ledger.credit("u", 100, "earn", "dup") == 100
    # A replay of the SAME key must NOT double-apply (EventSub-replay safety).
    assert ledger.credit("u", 100, "earn", "dup") == 100
    assert ledger.balance("u") == 100


def test_debit_is_idempotent_on_key(led):
    ledger, _ = led
    ledger.register("u", "bob")
    ledger.credit("u", 100, "earn", "k1")
    assert ledger.debit("u", 40, "bet", "dupd") == 60
    assert ledger.debit("u", 40, "bet", "dupd") == 60   # replay -> no second debit
    assert ledger.balance("u") == 60


def test_debit_insufficient_funds_writes_nothing(led):
    ledger, client = led
    ledger.register("u", "bob")
    ledger.credit("u", 50, "earn", "k1")
    with pytest.raises(InsufficientFunds):
        ledger.debit("u", 100, "bet", "k2")
    assert ledger.balance("u") == 50          # unchanged
    assert client.points["bob"] == 50


def test_credit_without_register_raises(led):
    ledger, _ = led
    with pytest.raises(SEPointsError):
        ledger.credit("ghost", 10, "earn", "k1")


def test_register_is_idempotent_and_updates_login(led):
    ledger, client = led
    ledger.register("u", "OldName")
    ledger.register("u", "NewName")              # renamed viewer
    client.points["newname"] = 5
    assert ledger.balance("u") == 5

    ledger.close()


def test_rebuild_balances_returns_se_leaderboard(led):
    ledger, client = led
    client.points.update({"alice": 300, "bob": 100, "carol": 200})
    board = ledger.rebuild_balances()            # !leaderboard source
    # login-keyed, all present; the chat-game cmd sorts + renders the top.
    assert board == {"alice": 300, "carol": 200, "bob": 100}
