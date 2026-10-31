"""Pre-picked demo disruptions shared by app.py and make_cache.py (DOT 2015, 24 Apr)."""

# row_id -> identifies one flights.csv row (month/day fixed to 2015-04-24)
# Order = selectbox order: consensus cases first, then the no-valid-plan cases (visible failure).
DEMO_ROWS = {
    "AA36_SAN_DFW_weather": {"airline": "AA", "flight_number": "36", "origin": "SAN", "label": "AA36 SAN→DFW (weather 47)"},
    "AA96_STL_DFW_late": {"airline": "AA", "flight_number": "96", "origin": "STL", "label": "AA96 STL→DFW (late aircraft 62)"},
    "AA1480_MCI_DFW_weather": {"airline": "AA", "flight_number": "1480", "origin": "MCI", "label": "AA1480 MCI→DFW (weather, DFW 24 Apr)"},
    "AA98_MSY_DFW_late": {"airline": "AA", "flight_number": "98", "origin": "MSY", "label": "AA98 MSY→DFW (late aircraft 90)"},
}
MONTH, DAY, SEED = 4, 24, 7
