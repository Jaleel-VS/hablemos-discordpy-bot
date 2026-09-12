"""Pure calculations and display formatting for purchasing power."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from babel.numbers import format_currency, format_decimal

from cogs.ppp_cog.client import MarketRate
from cogs.ppp_cog.models import (
    Country,
    PPPInputError,
    PPPObservation,
    PPPResult,
)

MAX_AMOUNT = Decimal("1000000000000000")


def parse_amount(value: str) -> Decimal:
    """Parse a positive command amount without accepting ambiguous separators."""
    normalized = value.replace(",", "").replace("_", "").strip()
    try:
        amount = Decimal(normalized)
    except InvalidOperation as exc:
        raise PPPInputError(f"`{value}` is not a valid amount.") from exc
    if not amount.is_finite() or amount <= 0:
        raise PPPInputError("The amount must be greater than zero.")
    if amount > MAX_AMOUNT:
        raise PPPInputError("That amount is too large to compare meaningfully.")
    return amount


def calculate(
    amount: Decimal,
    source: PPPObservation,
    target: PPPObservation,
    market: MarketRate,
) -> PPPResult:
    """Calculate market and household purchasing-power equivalents."""
    purchasing_power = amount / source.value * target.value
    return PPPResult(
        amount=amount,
        source=source,
        target=target,
        market_amount=amount * market.rate,
        market_rate=market.rate,
        market_date=market.date,
        purchasing_power_amount=purchasing_power,
    )


def display_amount(value: Decimal, currency: str) -> str:
    """Format a currency amount compactly and consistently in English."""
    absolute = abs(value)
    if absolute >= Decimal("1000000000"):
        return f"{currency} {format_decimal(value / Decimal('1000000000'), '#,##0.##', locale='en')}B"
    if absolute >= Decimal("1000000"):
        return f"{currency} {format_decimal(value / Decimal('1000000'), '#,##0.##', locale='en')}M"
    fraction = "#,##0" if absolute >= 100 else "#,##0.00"
    return format_currency(
        value,
        currency,
        format=f"¤{fraction}",
        locale="en_US",
        currency_digits=False,
    )


def country_label(country: Country) -> str:
    """Return a compact country label for prose."""
    return country.name
