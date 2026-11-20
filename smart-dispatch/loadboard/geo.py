"""US freight cities and distance estimates for deadhead (DH-O / DH-D) and trip miles.

Distances are straight-line (great-circle) miles multiplied by a road circuity
factor, so they are estimates. A paid routing API would give exact road miles
(out of scope in the PID).
"""

import math

ROAD_FACTOR = 1.17  # typical ratio of road miles to straight-line miles in the US

# (city, state, latitude, longitude) for common freight markets.
CITIES = [
    ("Birmingham", "AL", 33.52, -86.80), ("Huntsville", "AL", 34.73, -86.59), ("Mobile", "AL", 30.69, -88.04),
    ("Montgomery", "AL", 32.37, -86.30), ("Phoenix", "AZ", 33.45, -112.07), ("Tucson", "AZ", 32.22, -110.97),
    ("Flagstaff", "AZ", 35.20, -111.65), ("Little Rock", "AR", 34.75, -92.29), ("Fort Smith", "AR", 35.39, -94.40),
    ("Los Angeles", "CA", 34.05, -118.24), ("Ontario", "CA", 34.06, -117.65), ("San Diego", "CA", 32.72, -117.16),
    ("Fresno", "CA", 36.74, -119.79), ("Sacramento", "CA", 38.58, -121.49), ("Stockton", "CA", 37.96, -121.29),
    ("Oakland", "CA", 37.80, -122.27), ("Bakersfield", "CA", 35.37, -119.02), ("Denver", "CO", 39.74, -104.99),
    ("Greeley", "CO", 40.42, -104.71), ("Grand Junction", "CO", 39.06, -108.55), ("Hartford", "CT", 41.77, -72.67),
    ("Wilmington", "DE", 39.74, -75.55), ("Miami", "FL", 25.76, -80.19), ("Orlando", "FL", 28.54, -81.38),
    ("Tampa", "FL", 27.95, -82.46), ("Jacksonville", "FL", 30.33, -81.66), ("Lakeland", "FL", 28.04, -81.95),
    ("Tallahassee", "FL", 30.44, -84.28), ("Atlanta", "GA", 33.75, -84.39), ("Savannah", "GA", 32.08, -81.09),
    ("Macon", "GA", 32.84, -83.63), ("Dalton", "GA", 34.77, -84.97), ("Boise", "ID", 43.62, -116.20),
    ("Twin Falls", "ID", 42.56, -114.46), ("Chicago", "IL", 41.88, -87.63), ("Joliet", "IL", 41.53, -88.08),
    ("Rockford", "IL", 42.27, -89.09), ("Peoria", "IL", 40.69, -89.59), ("Indianapolis", "IN", 39.77, -86.16),
    ("Fort Wayne", "IN", 41.08, -85.14), ("Evansville", "IN", 37.97, -87.57), ("Des Moines", "IA", 41.59, -93.62),
    ("Cedar Rapids", "IA", 41.98, -91.67), ("Wichita", "KS", 37.69, -97.34), ("Kansas City", "KS", 39.11, -94.63),
    ("Hugoton", "KS", 37.18, -101.35), ("Garden City", "KS", 37.97, -100.87), ("Louisville", "KY", 38.25, -85.76),
    ("Lexington", "KY", 38.04, -84.50), ("New Orleans", "LA", 29.95, -90.07), ("Baton Rouge", "LA", 30.45, -91.19),
    ("Shreveport", "LA", 32.53, -93.75), ("Portland", "ME", 43.66, -70.26), ("Baltimore", "MD", 39.29, -76.61),
    ("Boston", "MA", 42.36, -71.06), ("Worcester", "MA", 42.26, -71.80), ("Detroit", "MI", 42.33, -83.05),
    ("Grand Rapids", "MI", 42.96, -85.67), ("Lansing", "MI", 42.73, -84.56), ("Minneapolis", "MN", 44.98, -93.27),
    ("Saint Cloud", "MN", 45.56, -94.16), ("Jackson", "MS", 32.30, -90.18), ("Gulfport", "MS", 30.37, -89.09),
    ("Kansas City", "MO", 39.10, -94.58), ("St. Louis", "MO", 38.63, -90.20), ("Springfield", "MO", 37.21, -93.29),
    ("Joplin", "MO", 37.08, -94.51), ("Billings", "MT", 45.78, -108.50), ("Omaha", "NE", 41.26, -95.93),
    ("Lincoln", "NE", 40.81, -96.70), ("Grand Island", "NE", 40.93, -98.34), ("Las Vegas", "NV", 36.17, -115.14),
    ("Reno", "NV", 39.53, -119.81), ("Manchester", "NH", 42.99, -71.46), ("Newark", "NJ", 40.74, -74.17),
    ("Edison", "NJ", 40.52, -74.41), ("Albuquerque", "NM", 35.08, -106.65), ("Las Cruces", "NM", 32.32, -106.76),
    ("New York", "NY", 40.71, -74.01), ("Buffalo", "NY", 42.89, -78.88), ("Albany", "NY", 42.65, -73.76),
    ("Syracuse", "NY", 43.05, -76.15), ("Charlotte", "NC", 35.23, -80.84), ("Raleigh", "NC", 35.78, -78.64),
    ("Greensboro", "NC", 36.07, -79.79), ("Wilmington", "NC", 34.23, -77.94), ("Fargo", "ND", 46.88, -96.79),
    ("Bismarck", "ND", 46.81, -100.78), ("Columbus", "OH", 39.96, -83.00), ("Cleveland", "OH", 41.50, -81.69),
    ("Cincinnati", "OH", 39.10, -84.51), ("Toledo", "OH", 41.65, -83.54), ("Oklahoma City", "OK", 35.47, -97.52),
    ("Tulsa", "OK", 36.15, -95.99), ("Portland", "OR", 45.52, -122.68), ("Eugene", "OR", 44.05, -123.09),
    ("Philadelphia", "PA", 39.95, -75.17), ("Pittsburgh", "PA", 40.44, -80.00), ("Harrisburg", "PA", 40.27, -76.88),
    ("Allentown", "PA", 40.60, -75.49), ("Providence", "RI", 41.82, -71.41), ("Columbia", "SC", 34.00, -81.03),
    ("Charleston", "SC", 32.78, -79.93), ("Greenville", "SC", 34.85, -82.40), ("Sioux Falls", "SD", 43.55, -96.73),
    ("Rapid City", "SD", 44.08, -103.23), ("Nashville", "TN", 36.16, -86.78), ("Memphis", "TN", 35.15, -90.05),
    ("Knoxville", "TN", 35.96, -83.92), ("Chattanooga", "TN", 35.05, -85.31), ("Dallas", "TX", 32.78, -96.80),
    ("Fort Worth", "TX", 32.76, -97.33), ("Houston", "TX", 29.76, -95.37), ("San Antonio", "TX", 29.42, -98.49),
    ("Austin", "TX", 30.27, -97.74), ("El Paso", "TX", 31.76, -106.49), ("Laredo", "TX", 27.51, -99.51),
    ("McAllen", "TX", 26.20, -98.23), ("Amarillo", "TX", 35.22, -101.83), ("Lubbock", "TX", 33.58, -101.86),
    ("Salt Lake City", "UT", 40.76, -111.89), ("Ogden", "UT", 41.22, -111.97), ("Burlington", "VT", 44.48, -73.21),
    ("Richmond", "VA", 37.54, -77.44), ("Norfolk", "VA", 36.85, -76.29), ("Roanoke", "VA", 37.27, -79.94),
    ("Seattle", "WA", 47.61, -122.33), ("Tacoma", "WA", 47.25, -122.44), ("Spokane", "WA", 47.66, -117.43),
    ("Yakima", "WA", 46.60, -120.51), ("Charleston", "WV", 38.35, -81.63), ("Milwaukee", "WI", 43.04, -87.91),
    ("Green Bay", "WI", 44.51, -88.01), ("Madison", "WI", 43.07, -89.40), ("Cheyenne", "WY", 41.14, -104.82),
    ("Casper", "WY", 42.87, -106.31),
]

_LOOKUP = {f"{city}, {state}".lower(): (city, state, lat, lon) for city, state, lat, lon in CITIES}
CITY_LABELS = sorted(f"{city}, {state}" for city, state, _, _ in CITIES)


def find_city(text):
    """'Dallas, TX' (any case or spacing) -> (city, state, lat, lon), or None."""
    if not text:
        return None
    parts = [p.strip() for p in text.split(",")]
    if len(parts) != 2:
        return None
    return _LOOKUP.get(f"{parts[0]}, {parts[1]}".lower())


def straight_miles(lat1, lon1, lat2, lon2):
    radius = 3958.8  # Earth radius in miles
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def road_miles(lat1, lon1, lat2, lon2):
    return round(straight_miles(lat1, lon1, lat2, lon2) * ROAD_FACTOR)


def bounding_box(lat, lon, road_radius):
    """Lat/lon box that contains every point within `road_radius` road miles (for a fast SQL prefilter)."""
    straight = road_radius / ROAD_FACTOR
    dlat = straight / 69.0
    dlon = straight / max(1.0, 69.0 * math.cos(math.radians(lat)))
    return lat - dlat, lat + dlat, lon - dlon, lon + dlon
