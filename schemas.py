"""Tool schemas (OpenAI function format) for the nomads-planner plugin."""

_MEMBER_NOTE = (" Reads the user's own Nomads.com account (needs NOMADS_API_KEY from https://nomads.com/settings"
                " and a username setting). Private data: summarize, do not dump it into shared chats.")

SEARCH_CITIES = {
    "name": "nomads_search_cities",
    "description": ("Find cities to live and work remotely on Nomads.com, filtered by budget, region, country, "
                    "internet, safety and temperature; sorted by Nomads.com overall score (max 100). Returns curated "
                    "facts per city (monthly costs, rent, coworking, internet Mbps, weather now, 0-5 scores). "
                    "With no filters returns the live top 100. Use the returned slug with nomads_get_city. "
                    "Cannot search by city name: filter by country instead."),
    "parameters": {"type": "object", "properties": {
        "region": {"type": "string", "enum": ["Europe", "Asia", "North America", "Latin America", "Africa", "Middle East", "Oceania"]},
        "country": {"type": "string", "description": "Country name, e.g. Portugal"},
        "max_cost_usd": {"type": "integer", "description": "Max monthly cost for a nomad, USD"},
        "min_internet_mbps": {"type": "number"},
        "min_safety": {"type": "number", "description": "0 to 5"},
        "min_temperature_c": {"type": "number"},
        "max_temperature_c": {"type": "number"},
        "limit": {"type": "integer", "description": "1-100, default 10"},
    }},
}

GET_CITY = {
    "name": "nomads_get_city",
    "description": "Get Nomads.com curated facts for one city by slug (e.g. lisbon-portugal, from search or a trip).",
    "parameters": {"type": "object", "properties": {"slug": {"type": "string"}}, "required": ["slug"]},
}

GET_COUNTRY = {
    "name": "nomads_get_country",
    "description": "Get one country on Nomads.com by slug (e.g. portugal, united-kingdom): city count and its top 10 cities by overall score.",
    "parameters": {"type": "object", "properties": {"slug": {"type": "string"}}, "required": ["slug"]},
}

LIST_MEETUPS = {
    "name": "nomads_list_meetups",
    "description": ("Upcoming in-person Nomads.com meetups: name, date, local time, venue and how many people are going "
                    "(never who). Filter by city slug or country."),
    "parameters": {"type": "object", "properties": {
        "city": {"type": "string", "description": "City slug, e.g. lisbon-portugal"},
        "country": {"type": "string"},
        "days_ahead": {"type": "integer", "description": "1-365, default 90"},
        "limit": {"type": "integer", "description": "1-100, default 20"},
    }},
}

GET_TRIPS = {
    "name": "nomads_get_trips",
    "description": "Get the user's own Nomads.com trip history (city, country, dates, nights), newest first." + _MEMBER_NOTE,
    "parameters": {"type": "object", "properties": {
        "from_date": {"type": "string", "description": "Only trips ending on/after YYYY-MM-DD"},
        "to_date": {"type": "string", "description": "Only trips starting on/before YYYY-MM-DD"},
        "limit": {"type": "integer", "description": "1-1000, default 50"},
    }},
}

GET_FAVORITES = {
    "name": "nomads_get_favorites",
    "description": "Get the cities and countries the user hearted on Nomads.com (places they want to go or return to)." + _MEMBER_NOTE,
    "parameters": {"type": "object", "properties": {}},
}

NEXT_STAY_BRIEF = {
    "name": "nomads_next_stay_brief",
    "description": ("Build a next-stay planning brief in one call: the user's current and upcoming Nomads.com trips, "
                    "unplanned gaps in the window, then for each trip city (plus favorites and any cities passed in) "
                    "the Nomads.com facts, meetups that fall inside the stay dates, past visits, and which candidate is "
                    "cheapest / fastest internet / safest. Every number comes from Nomads.com or the user's own trip "
                    "dates. Works without a key if you pass cities (public data only). Prefer this over chaining the "
                    "other nomads_* tools when the user asks 'where next', 'what's on where I'm going', or to compare stays."),
    "parameters": {"type": "object", "properties": {
        "days_ahead": {"type": "integer", "description": "Planning window in days, 7-365, default 60"},
        "cities": {"type": "array", "items": {"type": "string"}, "description": "Extra city slugs to consider"},
        "include_favorites": {"type": "boolean", "description": "Add hearted cities as candidates, default true"},
        "max_cities": {"type": "integer", "description": "1-8, default 4 (each city costs one rate-limited lookup)"},
        "today": {"type": "string", "description": "Override today's date, YYYY-MM-DD (default: local date)"},
    }},
}

ALL = [SEARCH_CITIES, GET_CITY, GET_COUNTRY, LIST_MEETUPS, GET_TRIPS, GET_FAVORITES, NEXT_STAY_BRIEF]
