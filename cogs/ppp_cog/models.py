"""Typed values and domain errors for purchasing-power calculations."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


class PPPError(Exception):
    """Base class for expected purchasing-power errors."""


class PPPInputError(PPPError):
    """Raised when command input cannot be resolved safely."""


class PPPDataError(PPPError):
    """Raised when a remote source has no usable observation."""


@dataclass(frozen=True)
class Country:
    """A supported country and its primary tender currency."""

    territory: str
    iso3: str
    name: str
    currency: str


@dataclass(frozen=True)
class PPPObservation:
    """One annual household PPP observation."""

    country: Country
    value: Decimal
    year: int


@dataclass(frozen=True)
class PPPResult:
    """Complete market and purchasing-power comparison."""

    amount: Decimal
    source: PPPObservation
    target: PPPObservation
    market_amount: Decimal
    market_rate: Decimal
    market_date: str
    purchasing_power_amount: Decimal

    @property
    def purchasing_power_ratio(self) -> Decimal:
        """Return PPP equivalent divided by the market conversion."""
        return self.purchasing_power_amount / self.market_amount
