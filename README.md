# Nomads Planner — Nomads.com for Hermes

Ask Hermes *"where am I next month, what's on there, and is it cheaper than Chiang Mai?"* and get one answer built from your own [Nomads.com](https://nomads.com) trips plus live city data.

A native Hermes plugin (`plugin.yaml` + `register(ctx)`), not an MCP passthrough. It adds 7 read-only tools, a `/nomads` slash command and a bundled planning skill.

## What it does

| Tool | Needs key | What you get |
|---|---|---|
| `nomads_next_stay_brief` | optional | **One call that joins everything:** current and upcoming stays, unplanned gaps in the window, facts for each trip city (plus favorites and any cities you name), meetups that fall **inside each stay's dates**, how often you've been there before, and which candidate is cheapest / has the fastest internet / is safest / has the best air right now. Includes a ready-to-read markdown summary. |
| `nomads_get_trips` | yes | Your trip history (city, country, dates, nights), filterable by date |
| `nomads_get_favorites` | yes | Cities and countries you hearted |
| `nomads_search_cities` | no | Filter by budget, region, country, internet, safety, temperature (or the live top 100) |
| `nomads_get_city` | no | Curated facts for one city slug |
| `nomads_get_country` | no | A country's city count and top 10 cities |
| `nomads_list_meetups` | no | Upcoming in-person meetups (attendance is a count, never names) |

`/nomads` in any session: `/nomads brief [days]`, `/nomads trips`, `/nomads city <slug>`, `/nomads meetups <slug>`, `/nomads top`.

The bundled skill `nomads-planner:nomads-trip-planner` tells the model which tool to use and to quote Nomads.com numbers as given rather than inventing them.

### Why a plugin and not just the MCP server

- **Composition the model can't do reliably by chaining:** the brief makes one trips call, one favorites call and one meetups call for the whole window, then filters meetups to each stay's dates, computes gaps and past-visit counts from your own dates, and caps city lookups to respect Nomads.com's public limit (60 requests/hour per IP). Same inputs, same brief.
- **Works without an account:** pass `cities=[...]` for a public-data brief. City, country and meetup tools never need a key.
- **Read-only by construction:** the client only sends `GET`. Trip, favorite and meetup edits stay on nomads.com.
- **Profile-safe credentials:** the key is read per call through Hermes' `agent.secret_scope.get_secret`, so under a multi-profile gateway it never picks up another profile's key (it fails closed instead).
- **Clean failures:** every error is JSON with a code and a fix (`missing_key`, `missing_username`, `invalid_username_or_key`, `rate_limited`, `city_not_found`, `network_error`).

## Install

```bash
hermes plugins install nomads-planner        # once listed in the catalog
```

Optional, for trips, favorites and history in the brief:

```bash
# Personal key from https://nomads.com/settings
hermes config set NOMADS_API_KEY <your-key>
hermes config set plugins.entries.nomads-planner.settings.username <your-nomads-username>
```

You can also save the key as `username:key` and leave the username setting empty. Both fields are also in the plugin's settings form in Hermes Desktop.

## Example

> **You:** I'm in Tbilisi till the 15th, then Lisbon until 5 December. What's on, and how does Lisbon compare with Chiang Mai?
>
> **Hermes** (calls `nomads_next_stay_brief` with `days_ahead=30`, `cities=["chiang-mai-thailand"]`):
>
> | City | Why | Cost/mo (USD) | Internet | Temp now | Safety | Meetups |
> |---|---|---|---|---|---|---|
> | Tbilisi | current stay | 2449 | 16 Mbps | 7°C | 3.9 | 3 |
> | Lisbon | upcoming trip | 4740 | 95 Mbps | 20°C | 3.12 | 1 |
> | Chiang Mai | requested | 1567 | 25 Mbps | 26°C | 4 | 1 |
>
> Unplanned: 2026-12-06 → 2026-12-10 (5 days) · Lowest monthly cost: Chiang Mai (1567) · Fastest internet: Lisbon (95)

(These numbers are illustrative. Live values come from Nomads.com at call time.)

## Disclosure

- **Network:** HTTPS `GET` to `https://nomads.com/api/*` only (`/search`, `/top`, `/city/{slug}`, `/country/{slug}`, `/meetups`, `/trips`, `/favorites`). No other hosts.
- **Credentials:** `NOMADS_API_KEY` (optional), read through Hermes' secret scope and sent as `Authorization: Bearer <username>:<key>`. It never goes in a URL, a tool result or a log line. The plugin reads no files, `.env`, browser profiles or other credential stores.
- **Data:** trips and favorites are private to your account and are never cached. Public city data is cached in memory for 10 minutes to stay within Nomads.com's rate limits. Nothing is written to disk.
- **No** writes, shell commands, background processes or telemetry.
- Not affiliated with Nomads.com. Data © Nomads.com, credited in every brief.

## Development

```bash
python -m pytest tests -q                                  # 21 tests, mocked HTTP
hermes plugins validate . --install-deps                   # catalog CI check
hermes plugins doctor . --ci
```

No Python dependencies (stdlib `urllib` only). Requires Hermes ≥ 0.23.0. MIT licensed.
