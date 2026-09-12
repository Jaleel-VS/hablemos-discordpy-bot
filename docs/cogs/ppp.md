# Purchasing Power (`ppp_cog`)

Compares ordinary currency conversion with a country-level household purchasing-power estimate.

## Command

| Command | Description | Permissions | Cooldown |
|---------|-------------|-------------|----------|
| `$ppp <amount> <from> <to>` or `$ppp <from> <to> <amount>` | Render a dark comparison card with market value and household PPP equivalent. Alias: `$purchasingpower`. | None | 2 uses / 15 seconds / user |

Examples:

```text
$ppp 7000 ZAR USD
$ppp Bolivia Germany 1000
$ppp "South Africa" "United States" 7000
$ppp 1000 EUR:France USD
```

Currency codes use a conversational default country: for example, `USD` means the United States and `EUR`
means Germany. Specify `CURRENCY:Country` when the country matters. Country names containing spaces must be
quoted. The amount may be placed first or last.

## Method and data

The purchasing-power amount uses the World Bank household/private-consumption PPP indicator
`PA.NUS.PRVT.PP`:

```text
amount / source PPP factor * target PPP factor
```

The market amount comes from Frankfurter. Both services require no API key. Responses are cached in memory
for six hours, API requests time out after 12 seconds, and image rendering runs off the event loop. The
command immediately posts a fetching status because uncached comparisons can take several seconds, then
edits that message in place with either the finished card or a friendly error.

The image deliberately calls the result an estimate. PPP is a national household-price comparison, not a
personal budget, quality-of-life score, or exchange rate. Below the disclaimer, it translates the ratio into
a directional national price-level sentence (lower, higher, or broadly similar). The card displays the older
observation year when the two countries' latest World Bank observations differ.

## Configuration

No environment variables are required. Country/currency names and number formatting use the pinned Babel
package. The renderer reuses the bundled Inter variable font and returns a `BytesIO`; no temporary files are
created.

## Known edge cases

- Some countries have older World Bank observations or no household PPP observation.
- Shared currencies can represent countries with different PPP values. Common codes have documented defaults;
  `CURRENCY:Country` overrides them.
- Frankfurter may not support every currency represented in World Bank data. The command reports that the
  market rate is unavailable rather than showing only half a comparison.
- Data is cached only for the current bot process.

## Related

- [`../commands.md`](../commands.md) — user command reference.
- [World Bank indicator](https://data.worldbank.org/indicator/PA.NUS.PRVT.PP)
- [Frankfurter API](https://frankfurter.dev/)
