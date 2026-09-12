"""Tests for the purchasing-power calculator feature."""
from __future__ import annotations

from decimal import Decimal

import pytest
from PIL import Image

from cogs.ppp_cog.calculator import calculate, display_amount, parse_amount
from cogs.ppp_cog.client import (
    MarketRate,
    parse_market_payload,
    parse_ppp_payload,
)
from cogs.ppp_cog.countries import resolve_location
from cogs.ppp_cog.main import parse_command_arguments
from cogs.ppp_cog.models import PPPDataError, PPPInputError, PPPObservation
from cogs.ppp_cog.renderer import render_ppp_card


def test_resolves_common_currency_defaults_and_country_override() -> None:
    assert resolve_location("ZAR").territory == "ZA"
    assert resolve_location("USD").territory == "US"
    assert resolve_location("EUR").territory == "DE"
    assert resolve_location("EUR:France").territory == "FR"
    assert resolve_location("South Africa").currency == "ZAR"
    assert resolve_location("usa").iso3 == "USA"


def test_rejects_country_currency_mismatch() -> None:
    with pytest.raises(PPPInputError, match="uses `EUR`"):
        resolve_location("USD:France")


def test_parses_amount_and_shell_quoted_arguments() -> None:
    assert parse_amount("7,000.50") == Decimal("7000.50")
    assert parse_command_arguments('7000 "South Africa" "United States"') == (
        "7000",
        "South Africa",
        "United States",
    )


@pytest.mark.parametrize("value", ["0", "-1", "nan", "hello"])
def test_rejects_invalid_amounts(value: str) -> None:
    with pytest.raises(PPPInputError):
        parse_amount(value)


def test_parses_real_api_payload_shapes() -> None:
    south_africa = resolve_location("ZAR")
    ppp = parse_ppp_payload(
        [
            {"total": 1},
            [{"date": "2025", "value": 7.73995922531757}],
        ],
        south_africa,
    )
    market = parse_market_payload(
        [{"date": "2026-09-13", "base": "ZAR", "quote": "USD", "rate": 0.06203}],
        "ZAR",
        "USD",
    )
    assert ppp.value == Decimal("7.73995922531757")
    assert ppp.year == 2025
    assert market.rate == Decimal("0.06203")


def test_rejects_missing_remote_observations() -> None:
    with pytest.raises(PPPDataError):
        parse_ppp_payload([{"total": 0}, []], resolve_location("ZAR"))
    with pytest.raises(PPPDataError):
        parse_market_payload([], "ZAR", "USD")


def sample_result():
    source_country = resolve_location("ZAR")
    target_country = resolve_location("USD")
    source = PPPObservation(source_country, Decimal("7.73995922531757"), 2025)
    target = PPPObservation(target_country, Decimal("1"), 2025)
    market = MarketRate(Decimal("0.06203"), "2026-09-13")
    return calculate(Decimal("7000"), source, target, market)


def test_calculates_market_and_ppp_equivalents() -> None:
    result = sample_result()
    assert result.market_amount == Decimal("434.21000")
    assert result.purchasing_power_amount.quantize(Decimal("0.01")) == Decimal("904.40")
    assert result.purchasing_power_ratio.quantize(Decimal("0.1")) == Decimal("2.1")
    assert display_amount(result.purchasing_power_amount, "USD") == "$904"


def test_renders_selected_comparison_card() -> None:
    buffer = render_ppp_card(sample_result())
    with Image.open(buffer) as image:
        assert image.format == "PNG"
        assert image.size == (1600, 1100)
