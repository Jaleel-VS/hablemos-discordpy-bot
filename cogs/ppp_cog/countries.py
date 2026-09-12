"""Country and currency resolution for the PPP command."""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import UTC, datetime

from babel import Locale
from babel.numbers import get_territory_currencies

from cogs.ppp_cog.models import Country, PPPInputError

# Friendly defaults make the conversational three-argument form useful while
# still allowing an explicit country for shared currencies.
CURRENCY_DEFAULTS = {
    "AUD": "AU",
    "BRL": "BR",
    "CAD": "CA",
    "CHF": "CH",
    "CLP": "CL",
    "CNY": "CN",
    "COP": "CO",
    "EUR": "DE",
    "GBP": "GB",
    "INR": "IN",
    "JPY": "JP",
    "KRW": "KR",
    "MXN": "MX",
    "NZD": "NZ",
    "USD": "US",
    "ZAR": "ZA",
}

# Common names that differ from Babel or World Bank display names.
ALIASES = {
    "america": "US",
    "bolivia": "BO",
    "britain": "GB",
    "china": "CN",
    "czech republic": "CZ",
    "england": "GB",
    "iran": "IR",
    "russia": "RU",
    "south korea": "KR",
    "uk": "GB",
    "united states of america": "US",
    "usa": "US",
}

# ISO mapping for World Bank coverage. Python has no stdlib ISO-3166 alpha-3
# table, so keep this compact generated mapping local rather than add pycountry.
_ISO3_CODES = ["AFG", "ALB", "DZA", "ASM", "AND", "AGO", "ATG", "ARG", "ARM", "ABW", "AUS", "AUT", "AZE", "BHS", "BHR", "BGD", "BRB", "BLR", "BEL", "BLZ", "BEN", "BMU", "BTN", "BOL", "BIH", "BWA", "BRA", "VGB", "BRN", "BGR", "BFA", "BDI", "CPV", "KHM", "CMR", "CAN", "CYM", "CAF", "TCD", "CHL", "CHN", "COL", "COM", "COD", "COG", "CRI", "CIV", "HRV", "CUW", "CYP", "CZE", "DNK", "DJI", "DMA", "DOM", "ECU", "EGY", "SLV", "GNQ", "ERI", "EST", "SWZ", "ETH", "FRO", "FJI", "FIN", "FRA", "PYF", "GAB", "GMB", "GEO", "DEU", "GHA", "GRC", "GRL", "GRD", "GUM", "GTM", "GIN", "GNB", "GUY", "HTI", "HND", "HKG", "HUN", "ISL", "IND", "IDN", "IRN", "IRQ", "IRL", "ISR", "ITA", "JAM", "JPN", "JOR", "KAZ", "KEN", "KIR", "KOR", "XKX", "KWT", "KGZ", "LAO", "LVA", "LBN", "LSO", "LBR", "LBY", "LTU", "LUX", "MAC", "MDG", "MWI", "MYS", "MDV", "MLI", "MLT", "MHL", "MRT", "MUS", "MEX", "FSM", "MDA", "MCO", "MNG", "MNE", "MAR", "MOZ", "MMR", "NAM", "NRU", "NPL", "NLD", "NCL", "NZL", "NIC", "NER", "NGA", "MKD", "MNP", "NOR", "OMN", "PAK", "PLW", "PAN", "PNG", "PRY", "PER", "PHL", "POL", "PRT", "PRI", "QAT", "ROU", "RUS", "RWA", "WSM", "SMR", "STP", "SAU", "SEN", "SRB", "SYC", "SLE", "SGP", "SXM", "SVK", "SVN", "SLB", "SOM", "ZAF", "SSD", "ESP", "LKA", "KNA", "LCA", "VCT", "SDN", "SUR", "SWE", "CHE", "SYR", "TJK", "TZA", "THA", "TLS", "TGO", "TON", "TTO", "TUN", "TUR", "TKM", "TCA", "TUV", "UGA", "UKR", "ARE", "GBR", "USA", "URY", "UZB", "VUT", "VEN", "VNM", "VIR", "PSE", "YEM", "ZMB", "ZWE"]

# Alpha-2 can be derived reliably from Babel locale territory data only for
# names/currencies, not alpha-3. This explicit aligned table is ISO 3166.
_ISO2_CODES = ["AF", "AL", "DZ", "AS", "AD", "AO", "AG", "AR", "AM", "AW", "AU", "AT", "AZ", "BS", "BH", "BD", "BB", "BY", "BE", "BZ", "BJ", "BM", "BT", "BO", "BA", "BW", "BR", "VG", "BN", "BG", "BF", "BI", "CV", "KH", "CM", "CA", "KY", "CF", "TD", "CL", "CN", "CO", "KM", "CD", "CG", "CR", "CI", "HR", "CW", "CY", "CZ", "DK", "DJ", "DM", "DO", "EC", "EG", "SV", "GQ", "ER", "EE", "SZ", "ET", "FO", "FJ", "FI", "FR", "PF", "GA", "GM", "GE", "DE", "GH", "GR", "GL", "GD", "GU", "GT", "GN", "GW", "GY", "HT", "HN", "HK", "HU", "IS", "IN", "ID", "IR", "IQ", "IE", "IL", "IT", "JM", "JP", "JO", "KZ", "KE", "KI", "KR", "XK", "KW", "KG", "LA", "LV", "LB", "LS", "LR", "LY", "LT", "LU", "MO", "MG", "MW", "MY", "MV", "ML", "MT", "MH", "MR", "MU", "MX", "FM", "MD", "MC", "MN", "ME", "MA", "MZ", "MM", "NA", "NR", "NP", "NL", "NC", "NZ", "NI", "NE", "NG", "MK", "MP", "NO", "OM", "PK", "PW", "PA", "PG", "PY", "PE", "PH", "PL", "PT", "PR", "QA", "RO", "RU", "RW", "WS", "SM", "ST", "SA", "SN", "RS", "SC", "SL", "SG", "SX", "SK", "SI", "SB", "SO", "ZA", "SS", "ES", "LK", "KN", "LC", "VC", "SD", "SR", "SE", "CH", "SY", "TJ", "TZ", "TH", "TL", "TG", "TO", "TT", "TN", "TR", "TM", "TC", "TV", "UG", "UA", "AE", "GB", "US", "UY", "UZ", "VU", "VE", "VN", "VI", "PS", "YE", "ZM", "ZW"]
ISO2_TO_ISO3 = dict(zip(_ISO2_CODES, _ISO3_CODES, strict=True))
ISO3_TO_ISO2 = {iso3: iso2 for iso2, iso3 in ISO2_TO_ISO3.items()}


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def build_country_catalog() -> tuple[dict[str, Country], dict[str, list[Country]]]:
    """Build country lookup and currency indexes from bundled Babel data."""
    locale = Locale("en")
    today = datetime.now(UTC).date()
    by_name: dict[str, Country] = {}
    by_currency: defaultdict[str, list[Country]] = defaultdict(list)

    for territory, iso3 in ISO2_TO_ISO3.items():
        name = locale.territories.get(territory)
        currencies = get_territory_currencies(territory, today, tender=True)
        if not name or not currencies:
            continue
        primary = Country(territory, iso3, name, currencies[0])
        by_name[_normalize(name)] = primary
        by_name[territory.casefold()] = primary
        by_name[iso3.casefold()] = primary
        for currency in currencies:
            by_currency[currency].append(Country(territory, iso3, name, currency))

    for alias, territory in ALIASES.items():
        country = next((c for c in by_name.values() if c.territory == territory), None)
        if country is not None:
            by_name[_normalize(alias)] = country

    return by_name, dict(by_currency)


COUNTRIES_BY_NAME, COUNTRIES_BY_CURRENCY = build_country_catalog()


def resolve_country(value: str) -> Country:
    """Resolve a country name or ISO code, raising a friendly input error."""
    country = COUNTRIES_BY_NAME.get(_normalize(value))
    if country is None:
        raise PPPInputError(
            f"I don't recognize the country `{value}`. Use a country name, "
            "two-letter code, three-letter code, or a supported currency."
        )
    return country


def resolve_currency(value: str) -> Country:
    """Resolve a currency using a documented conversational default."""
    currency = value.upper()
    countries = COUNTRIES_BY_CURRENCY.get(currency, [])
    if not countries:
        raise PPPInputError(f"I don't recognize the currency `{value}`.")

    default_territory = CURRENCY_DEFAULTS.get(currency)
    if default_territory:
        match = next(
            (country for country in countries if country.territory == default_territory),
            None,
        )
        if match is not None:
            return match

    if len(countries) == 1:
        return countries[0]

    examples = ", ".join(country.name for country in countries[:4])
    raise PPPInputError(
        f"`{currency}` is used by multiple countries ({examples}). "
        f"Specify one with `{currency}:Country`, for example `{currency}:{countries[0].name}`."
    )


def resolve_location(value: str) -> Country:
    """Resolve `CURRENCY`, `country`, or `CURRENCY:country` input."""
    if ":" in value:
        currency, country_name = value.split(":", 1)
        resolved = resolve_country(country_name)
        country = next(
            (
                candidate
                for candidate in COUNTRIES_BY_CURRENCY.get(currency.upper(), [])
                if candidate.territory == resolved.territory
            ),
            None,
        )
        if country is None:
            raise PPPInputError(
                f"{resolved.name} uses `{resolved.currency}`, not `{currency.upper()}`."
            )
        return country

    normalized = _normalize(value)
    if normalized in COUNTRIES_BY_NAME:
        return resolve_country(value)
    if len(value) == 3 and value.isalpha():
        return resolve_currency(value)
    return resolve_country(value)
