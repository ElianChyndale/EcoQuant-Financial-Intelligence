from __future__ import annotations

import pytest

from ecoquant.research.commercial_eval.metrics import (
    debt_to_equity,
    fcff,
    gross_margin,
    operating_margin,
    reinvestment_rate,
    roic,
    working_capital,
)


def test_gross_margin() -> None:
    assert gross_margin(40.0, 100.0) == pytest.approx(0.40)
    assert gross_margin(None, 100.0) is None
    assert gross_margin(40.0, None) is None


def test_operating_margin() -> None:
    assert operating_margin(20.0, 100.0) == pytest.approx(0.20)
    assert operating_margin(None, 100.0) is None


def test_working_capital() -> None:
    assert working_capital(100.0, 60.0) == pytest.approx(40.0)
    assert working_capital(None, 60.0) is None


def test_fcff() -> None:
    assert fcff(150.0, 50.0) == pytest.approx(100.0)
    assert fcff(None, 50.0) is None


def test_roic() -> None:
    # ROIC = net_income / (equity + debt - cash)
    assert roic(30.0, equity=100.0, total_debt=50.0, cash=20.0) == pytest.approx(30.0 / 130.0)
    assert roic(None, equity=100.0, total_debt=50.0, cash=20.0) is None
    # Zero invested capital → None (division by zero, no fabrication)
    assert roic(30.0, equity=10.0, total_debt=0.0, cash=10.0) is None


def test_reinvestment_rate() -> None:
    assert reinvestment_rate(50.0, 150.0) == pytest.approx(1.0 / 3.0)
    assert reinvestment_rate(None, 150.0) is None
    # Zero operating cash flow → None
    assert reinvestment_rate(50.0, 0.0) is None


def test_debt_to_equity() -> None:
    assert debt_to_equity(50.0, 100.0) == pytest.approx(0.5)
    assert debt_to_equity(None, 100.0) is None
    assert debt_to_equity(50.0, 0.0) is None
