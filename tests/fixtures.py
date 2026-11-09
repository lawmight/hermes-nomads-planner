CITY = {
    "lisbon-portugal": {"slug": "lisbon-portugal", "name": "Lisbon", "country": "Portugal", "region": "Europe",
                        "url": "https://nomads.com/lisbon", "overall_score": 3.94, "cost_for_nomad_usd_per_month": 4740,
                        "internet_mbps": 95, "temperature_c_now": 20, "safety_score_0_to_5": 3.12, "air_quality_now": 36,
                        "has_remote_work_visa": True, "neighborhoods": {"map_url": "x"}},
    "chiang-mai-thailand": {"slug": "chiang-mai-thailand", "name": "Chiang Mai", "country": "Thailand", "region": "Asia",
                            "url": "https://nomads.com/chiang-mai", "overall_score": 4.1, "cost_for_nomad_usd_per_month": 1300,
                            "internet_mbps": 60, "temperature_c_now": 28, "safety_score_0_to_5": 4.0, "air_quality_now": 80,
                            "has_remote_work_visa": False},
    "tbilisi-georgia": {"slug": "tbilisi-georgia", "name": "Tbilisi", "country": "Georgia", "region": "Europe",
                        "url": "https://nomads.com/tbilisi", "overall_score": 4.0, "cost_for_nomad_usd_per_month": 1800,
                        "internet_mbps": 40, "temperature_c_now": 12, "safety_score_0_to_5": 4.5, "air_quality_now": 50,
                        "has_remote_work_visa": True},
}

TRIPS = {"username": "alice", "total_trips": 5, "returned": 5, "order": "newest first", "trips": [
    {"trip_id": "t5", "city": "Chiang Mai", "city_slug": "chiang-mai-thailand", "country": "Thailand", "country_code": "TH",
     "date_start": "2026-12-20", "date_end": "2027-01-10"},
    {"trip_id": "t4", "city": "Lisbon", "city_slug": "lisbon-portugal", "country": "Portugal", "country_code": "PT",
     "date_start": "2026-11-20", "date_end": "2026-12-05"},
    {"trip_id": "t3", "city": "Tbilisi", "city_slug": "tbilisi-georgia", "country": "Georgia", "country_code": "GE",
     "date_start": "2026-11-01", "date_end": "2026-11-15"},
    {"trip_id": "t2", "city": "Somewhere", "city_slug": "", "country": "Nowhere", "country_code": "NW",
     "date_start": "2026-12-06", "date_end": "2026-12-08"},
    {"trip_id": "t1", "city": "Lisbon", "city_slug": "lisbon-portugal", "country": "Portugal", "country_code": "PT",
     "date_start": "2026-03-01", "date_end": "2026-03-31"},
]}

FAVS = {"username": "alice", "cities": [{"slug": "tbilisi-georgia", "name": "Tbilisi"}, {"slug": "bali-indonesia", "name": "Bali"}],
        "countries": []}

MEETUPS = {"returned": 3, "days_ahead": 60, "meetups": [
    {"meetup_id": "m1", "name": "Cowork day", "city": "Lisbon", "city_slug": "lisbon-portugal", "date": "2026-11-25",
     "local_time": "10:00", "venue": "Cafe A", "people_going": 4, "url": "https://nomads.com/meetups"},
    {"meetup_id": "m2", "name": "Too early", "city": "Lisbon", "city_slug": "lisbon-portugal", "date": "2026-11-12",
     "local_time": "10:00", "venue": "Cafe B", "people_going": 2, "url": "https://nomads.com/meetups"},
    {"meetup_id": "m3", "name": "Coffee", "city": "Tbilisi", "city_slug": "tbilisi-georgia", "date": "2026-11-12",
     "local_time": "11:00", "venue": "Tsvari", "people_going": 2, "url": "https://nomads.com/meetups"},
], "join": "noise", "sponsor": "noise"}


def city_route(req):
    slug = req.full_url.rsplit("/", 1)[1]
    if slug in CITY:
        return {"city": CITY[slug], "attribution": "Data from Nomads.com", "sponsor": "noise"}
    return {"error": "city_not_found", "hint": "Use search_cities first; pass its slug value."}
