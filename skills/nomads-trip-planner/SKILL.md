---
name: nomads-trip-planner
description: Plan where to stay next with Nomads.com data — trips, favorites, city facts, meetups. Use when the user asks where to go next, what's on in a city they're heading to, or to compare cities for remote work.
---
# Nomads trip planner

Tools come from the `nomads-planner` plugin. All are read-only.

## Pick the tool

| User asks | Call |
|---|---|
| "Where should I go next?", "what's on where I'm going?", compare upcoming stays | `nomads_next_stay_brief` (one call; pass `cities` to add options) |
| "Show my trips" / "where was I in March?" | `nomads_get_trips` with `from_date`/`to_date` |
| "Cities I saved" | `nomads_get_favorites` |
| "Cheap, fast-internet, warm places in Asia" | `nomads_search_cities` (filters, not names) |
| Facts for one city | `nomads_get_city` with a slug like `lisbon-portugal` |
| A country's best cities | `nomads_get_country` |
| Meetups in a city | `nomads_list_meetups` |

## Rules

1. Prefer `nomads_next_stay_brief` over chaining tools: it makes one meetups call and caps city lookups (public city data is limited to 60 requests/hour per IP).
2. Quote numbers as Nomads.com gives them (USD per month, Mbps, 0-5 scores). Never invent prices, scores or rankings; if a field is missing say "n/a".
3. Slugs come from search results, trips or favorites. `nomads_search_cities` cannot search by name; filter by `country` and pick the slug.
4. Trips and favorites are private. Summarize them; don't paste the raw list into group chats.
5. On `missing_key`: tell the user to create a personal key at https://nomads.com/settings and save it as `NOMADS_API_KEY`, plus the `username` setting. Public tools still work meanwhile.
6. This plugin cannot add, edit or delete trips, favorites or meetups. Send the user to nomads.com for that.
7. Credit "Data from Nomads.com" when you show city data.
