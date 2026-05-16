from decimal import Decimal

from src.positions.service import apply_fill, filter_signals_for_positions, position_summary_from_rows


def test_apply_fill_buy_weighted_avg():
    qty, avg = apply_fill(None, "buy", Decimal("10"), Decimal("100"))
    assert qty == Decimal("10") and avg == Decimal("100")
    qty2, avg2 = apply_fill((qty, avg), "buy", Decimal("10"), Decimal("120"))
    assert qty2 == Decimal("20") and avg2 == Decimal("110")


def test_apply_fill_sell_partial():
    qty, avg = apply_fill((Decimal("20"), Decimal("100")), "sell", Decimal("5"), Decimal("110"))
    assert qty == Decimal("15") and avg == Decimal("100")


def test_filter_drops_buy_when_holding():
    positions = {"AAPL": Decimal("1")}
    signals = [{"symbol": "AAPL", "direction": "buy"}, {"symbol": "MSFT", "direction": "buy"}]
    out = filter_signals_for_positions(signals, positions)
    assert len(out) == 1 and out[0]["symbol"] == "MSFT"


def test_filter_drops_sell_when_flat():
    positions = {"AAPL": Decimal("1")}
    signals = [{"symbol": "AAPL", "direction": "sell"}, {"symbol": "MSFT", "direction": "sell"}]
    out = filter_signals_for_positions(signals, positions)
    assert len(out) == 1 and out[0]["symbol"] == "AAPL"


def test_position_summary():
    rows = [
        (Decimal("10"), Decimal("100"), Decimal("105")),
        (Decimal("0"), Decimal("50"), None),
    ]
    s = position_summary_from_rows(rows)
    assert s["open_symbols"] == 1
    assert s["total_shares"] == 10.0
    assert s["position_value"] == 1050.0
