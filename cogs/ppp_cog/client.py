"""HTTP client for World Bank PPP data and Frankfurter market rates."""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

import aiohttp

from cogs.ppp_cog.models import Country, PPPDataError, PPPObservation

WORLD_BANK_URL = (
    "https://api.worldbank.org/v2/country/{countries}/indicator/"
    "PA.NUS.PRVT.PP?format=json&mrnev=1&per_page=10"
)
FRANKFURTER_URL = "https://api.frankfurter.dev/v2/rates"


@dataclass(frozen=True)
class MarketRate:
    """One current market exchange-rate observation."""

    rate: Decimal
    date: str


class PPPClient:
    """Fetch and briefly cache external purchasing-power inputs."""

    def __init__(self, *, cache_ttl: int = 21_600, timeout_seconds: int = 12):
        self.cache_ttl = cache_ttl
        self.timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        self._ppp_cache: dict[str, tuple[float, PPPObservation]] = {}
        self._rate_cache: dict[tuple[str, str], tuple[float, MarketRate]] = {}
        self._request_locks: dict[object, asyncio.Lock] = {}
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=self.timeout,
                headers={"User-Agent": "Hablemos-Discord-Bot/PPP"},
            )
        return self._session

    async def close(self) -> None:
        """Close the shared HTTP session."""
        if self._session is not None and not self._session.closed:
            await self._session.close()

    def _fresh[T](self, entry: tuple[float, T] | None) -> T | None:
        if entry is None or time.monotonic() - entry[0] >= self.cache_ttl:
            return None
        return entry[1]

    async def get_ppp(self, country: Country) -> PPPObservation:
        """Return the latest available household PPP for a country."""
        cached = self._fresh(self._ppp_cache.get(country.iso3))
        if cached is not None:
            return cached

        lock = self._request_locks.setdefault(("ppp", country.iso3), asyncio.Lock())
        async with lock:
            cached = self._fresh(self._ppp_cache.get(country.iso3))
            if cached is not None:
                return cached
            session = await self._get_session()
            url = WORLD_BANK_URL.format(countries=country.iso3)
            try:
                async with session.get(url) as response:
                    response.raise_for_status()
                    payload = await response.json(content_type=None)
            except (aiohttp.ClientError, TimeoutError) as exc:
                raise PPPDataError("The World Bank data service is unavailable right now.") from exc

            observation = parse_ppp_payload(payload, country)
            self._ppp_cache[country.iso3] = (time.monotonic(), observation)
            return observation

    async def get_market_rate(self, source: str, target: str) -> MarketRate:
        """Return the latest market rate from source to target currency."""
        if source == target:
            return MarketRate(Decimal(1), "same currency")
        key = (source, target)
        cached = self._fresh(self._rate_cache.get(key))
        if cached is not None:
            return cached

        lock = self._request_locks.setdefault(("rate", *key), asyncio.Lock())
        async with lock:
            cached = self._fresh(self._rate_cache.get(key))
            if cached is not None:
                return cached
            session = await self._get_session()
            try:
                async with session.get(
                    FRANKFURTER_URL,
                    params={"base": source, "quotes": target},
                ) as response:
                    response.raise_for_status()
                    payload = await response.json(content_type=None)
            except (aiohttp.ClientError, TimeoutError) as exc:
                raise PPPDataError("The market exchange-rate service is unavailable right now.") from exc

            rate = parse_market_payload(payload, source, target)
            self._rate_cache[key] = (time.monotonic(), rate)
            return rate


def parse_ppp_payload(payload: object, country: Country) -> PPPObservation:
    """Parse a World Bank response into a concrete observation."""
    if not isinstance(payload, list) or len(payload) < 2 or not isinstance(payload[1], list):
        raise PPPDataError(f"No household purchasing-power data is available for {country.name}.")
    row = next((item for item in payload[1] if isinstance(item, dict) and item.get("value") is not None), None)
    if row is None:
        raise PPPDataError(f"No household purchasing-power data is available for {country.name}.")
    try:
        value = Decimal(str(row["value"]))
        year = int(row["date"])
    except (InvalidOperation, KeyError, TypeError, ValueError) as exc:
        raise PPPDataError("The World Bank returned an unexpected data format.") from exc
    if value <= 0:
        raise PPPDataError("The World Bank returned an invalid PPP value.")
    return PPPObservation(country=country, value=value, year=year)


def parse_market_payload(payload: object, source: str, target: str) -> MarketRate:
    """Parse a Frankfurter v2 response into a concrete market rate."""
    if not isinstance(payload, list):
        raise PPPDataError(f"No market rate is available for {source} to {target}.")
    row = next(
        (
            item for item in payload
            if isinstance(item, dict)
            and item.get("base") == source
            and item.get("quote") == target
        ),
        None,
    )
    if row is None:
        raise PPPDataError(f"No market rate is available for {source} to {target}.")
    try:
        rate = Decimal(str(row["rate"]))
        date = str(row["date"])
    except (InvalidOperation, KeyError, TypeError) as exc:
        raise PPPDataError("The exchange-rate service returned an unexpected format.") from exc
    if rate <= 0:
        raise PPPDataError("The exchange-rate service returned an invalid rate.")
    return MarketRate(rate=rate, date=date)
