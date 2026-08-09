

import json
import streamlit as st
import requests
import pandas as pd
from serpapi import GoogleSearch
import re
import time


API_KEY = "ba89ba1cfa8384472ff340113a545c2c2a18e92ea7898c029509a63be7f0876a"    # replace with your key

class TravelPlanner:
    def __init__(self, opencage_key):
        self.opencage_key = opencage_key

    def geocode_location(self, query, language=None, countrycode=None, limit=3):
        url = "https://api.opencagedata.com/geocode/v1/json"
        params = {"q": query, "key": self.opencage_key, "limit": limit}
        if language:
            params["language"] = language
        if countrycode:
            params["countrycode"] = countrycode
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        return [
            (r["geometry"]["lat"], r["geometry"]["lng"], r["formatted"])
            for r in data.get("results", [])
        ]



# --- Hotels via SerpAPI ---
    def search_google_hotels(self, lat, lng, check_in, check_out, currency="USD"):
        params = {
            "engine": "google_hotels",
            "lat": lat,
            "lng": lng,
            "check_in_date": check_in,
            "check_out_date": check_out,
            "currency": currency,
            "api_key": API_KEY,
        }
        search = GoogleSearch(params)
        results = search.get_dict()
        st.expander("Raw Hotel API Response").json(results)
        return results.get("properties", [])

    def get_highest_rated_hotel(self, hotels, currency="USD"):
        def parse_rating(h):
            try:
                return float(h.get("overall_rating", 0))
            except Exception:
                return 0

        if not hotels:
            return None

        best_hotel = max(hotels, key=parse_rating)
        return {
            "name": best_hotel.get("name", "Unknown"),
            "rating": best_hotel.get("overall_rating", "N/A"),
            "reviews": best_hotel.get("reviews", "N/A"),
            "price": f"{best_hotel.get('rate_per_night', {}).get('lowest', 'N/A')} "
                    f"{best_hotel.get('rate_per_night', {}).get('currency', currency)}",
            "address": best_hotel.get("address", ""),
            "link": best_hotel.get("link", "")
        }

# --- Activities ---
def search_activities(self, latitude, longitude, radius=5):
    # Construct the Amadeus API endpoint for activities
    url = f"{self.base_url}/v1/shopping/activities"
    params = {
        "latitude": latitude,   # latitude of the location
        "longitude": longitude, # longitude of the location
        "radius": radius        # search radius in km
    }
    try:
        # Send GET request with authorization headers
        response = requests.get(url, headers=self._headers(), params=params)
        response.raise_for_status()  # raise error if status != 200

        # Extract the "data" field which contains the list of activities
        return response.json().get("data", [])
    except requests.exceptions.HTTPError as e:
        # Show error in Streamlit if the API call fails
        st.error(f"Activity search failed: {e}")
        return []


def activities_by_place(self, place_name, language=None, countrycode=None, limit=1, radius=5):
    # Use geocoding to convert place name into coordinates
    coords = self.geocode_location(place_name, language, countrycode, limit)
    # If geocoding fails, return empty list
    if not coords:
        return []
    # Take the first result (lat, lng, formatted address)
    lat, lng, formatted = coords[0]
    # Display resolved location in Streamlit
    st.write(f"Resolved '{place_name}' to: {formatted} ({lat}, {lng})")
    # Call search_activities with the coordinates
    activities = self.search_activities(lat, lng, radius)
    # Return the list of activities (unsorted by default)
    return activities



# --- Airport Code Lookup ---

def get_airports(city):
    params = {
        "engine": "google_flights_autocomplete",
        "q": city,
        "api_key": API_KEY
    }
    search = GoogleSearch(params)
    results = search.get_dict()


    codes = []
    if "suggestions" in results and len(results["suggestions"]) > 0:
        # Only take the first suggestion
        first_suggestion = results["suggestions"][0]
        if "airports" in first_suggestion:
            for airport in first_suggestion["airports"]:
                if "Airport" in airport.get("name", ""):
                    codes.append(airport.get("id"))
    return codes if codes else None



def parse_best_flights(results):
    """Parse the best_flights list into a cleaner structure with a single route column."""
    options = []
    for option in results.get("best_flights", []):
        for leg in option.get("flights", []):
            options.append({
                "price": option.get("price"),
                "total_duration": option.get("total_duration"),
                "type": option.get("type"),
                "airline": leg.get("airline"),
                "flight_number": leg.get("flight_number"),
                "travel_class": leg.get("travel_class"),
                "route": f"{leg['departure_airport']['name']} ({leg['departure_airport']['id']}) "
                         f"→ {leg['arrival_airport']['name']} ({leg['arrival_airport']['id']})",
                "departure_time": leg["departure_airport"]["time"],
                "arrival_time": leg["arrival_airport"]["time"],
                "duration": leg["duration"],
                "airplane": leg.get("airplane", ""),
                "legroom": leg.get("legroom", ""),
            })
    return options



from datetime import datetime, timedelta

def search_best_flight(origin, destination, outbound_date,
                       currency="USD", trip_type="oneway", return_date=None):
    normalized_type = trip_type.strip().lower().replace(" ", "").replace("-", "")
    type_map = {"oneway": 2, "roundtrip": 1}
    trip_type_value = type_map.get(normalized_type, 2)

    outbound_options, return_options = [], []

    # --- Outbound roundtrip search ---
    params_outbound = {
        "engine": "google_flights",
        "departure_id": origin,
        "arrival_id": destination,
        "outbound_date": outbound_date,
        "currency": currency,
        "type": trip_type_value,
        "api_key": API_KEY,
    }
    if trip_type_value == 1 and return_date:
        params_outbound["return_date"] = return_date

    results_outbound = GoogleSearch(params_outbound).get_dict()
    outbound_options = parse_best_flights(results_outbound)

    # --- Return roundtrip search (based on return_date) ---
    if trip_type_value == 1 and return_date:
        # ensure return_date >= outbound_date
        return_date_obj = datetime.strptime(return_date, "%Y-%m-%d")
        adjusted_return_date = (return_date_obj + timedelta(days=1)).strftime("%Y-%m-%d")

        params_return = {
            "engine": "google_flights",
            "departure_id": destination,
            "arrival_id": origin,
            "outbound_date": return_date,          # traveler leaves destination on return date
            "return_date": adjusted_return_date,   # valid later date
            "currency": currency,
            "type": 1,  # roundtrip
            "api_key": API_KEY,
        }

        results_return = GoogleSearch(params_return).get_dict()
        return_options = parse_best_flights(results_return)

    return {
        "trip_type": "Round trip" if trip_type_value == 1 else "One way",
        "outbound_options": outbound_options,
        "return_options": return_options
    }

    
# --- Activities via Google Maps (SerpApi) ---
def search_activities(self, latitude, longitude, query, radius=5000):
    params = {
        "engine": "google_maps",
        "q": query,   # use the location name or keyword
        "ll": f"@{latitude},{longitude},15z",
        "type": "search",
        "api_key": API_KEY
    }
    try:
        search = GoogleSearch(params)
        results = search.get_dict()
        return results.get("local_results", [])
    except Exception as e:
        st.error(f"Activity search failed: {e}")
        return []

def activities_by_place(self, place_name, language=None, countrycode=None, limit=1, radius=5000):
    coords = self.geocode_location(place_name, language, countrycode, limit)
    if not coords:
        return []
    lat, lng, formatted = coords[0]
    st.write(f"Resolved '{place_name}' to: {formatted} ({lat}, {lng})")
    return self.search_activities(lat, lng, query=place_name, radius=radius)

import requests

def get_directions_raw(origin, destination, mode="transit"):
    url = "https://serpapi.com/search"
    params = {
        "engine": "google_maps_directions",
        "start_addr": origin,        # use city name or full address
        "end_addr": destination,     # use city name or full address
        "mode": mode,                # driving, walking, bicycling, transit
        "api_key": API_KEY
    }
    response = requests.get(url, params=params)
    return response.json()


import math

def haversine(lat1, lon1, lat2, lon2):
    # Calculate great-circle distance between two points
    R = 6371  # Earth radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat/2)**2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

import itertools
import streamlit as st

def kruskal_mst(locations, coords, haversine_fn):
    edges = []
    for a, b in itertools.combinations(locations, 2):
        if a in coords and b in coords:
            lat1, lon1 = coords[a]
            lat2, lon2 = coords[b]
            d = haversine_fn(lat1, lon1, lat2, lon2)
            edges.append((d, a, b))
    edges.sort(key=lambda x: x[0])

    # Show all edges in Streamlit
    st.write("### All edges (sorted by weight)")
    for d, a, b in edges:       
        st.write(f"{a} -- {b} (weight={d:.2f})")

    parent = {loc: loc for loc in locations}
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    mst = []
    for d, a, b in edges:
        root_a, root_b = find(a), find(b)
        if root_a != root_b:
            mst.append((a, b, d))
            parent[root_a] = root_b

    # Show MST edges separately
    st.write("### MST edges")
    for a, b, d in mst:
        st.write(f"{a} -- {b} (weight={d:.2f})")

    return mst

# Traverse MST to get linear order
def traverse_mst(mst, start):
    graph = {}
    for a, b, d in mst:
        graph.setdefault(a, []).append((b, d))
        graph.setdefault(b, []).append((a, d))

    visited = set()
    order = []

    def dfs(node):
        visited.add(node)
        order.append(node)
        for neighbor, _ in graph.get(node, []):
            if neighbor not in visited:
                dfs(neighbor)

    dfs(start)
    return order


def search_hotels_overall_recommendation(hotels):
    """
    Query Google AI Mode API for an overall recommendation
    across multiple hotels.
    Always return in the fixed format with Best Option, Why It Stands Out,
    Pros, Cons, Suitability.
    Also provide alternative options for each hotel in the list.
    """
    hotel_names = ", ".join([h.get("name", "Unknown") for h in hotels])

    params = {
        "engine": "google_ai_mode",
        "q": (
            f"Compare the following hotels: {hotel_names}. "
            f"Provide a balanced comparison across all hotels. "
            f"For each hotel, include:\n\n"
            f"🏨 Best Option:\n"
            f"<Hotel Name>\n\n"
            f"✨ Why It Stands Out:\n"
            f"<One or two sentences explaining why this hotel is notable>\n\n"
            f"✅ Pros:\n"
            f"<List of pros>\n\n"
            f"⚠️ Cons:\n"
            f"<List of cons>\n\n"
            f"👥 Suitability:\n"
            f"<Who this hotel is best for>\n\n"
            f"Repeat this structure for every hotel in the list, so each one is presented as an alternative option. "
            f"Only deliver the recommendations in this format. Do not include tables, references, or follow-up prompts."
        ),
        "api_key": API_KEY
    }

    response = requests.get("https://serpapi.com/search", params=params)
    return response.json()


def search_activity_recommendation(place, activities, weather_summary=None):
    """
    Query Google AI Mode API for an overall recommendation
    across multiple activities near a place, grouped by type.
    Loop through ALL activities and return them in a clean structured format.
    Activity types are derived dynamically from the activities list.
    """
    # Collect all activity names
    activity_names = ", ".join([a.get("title", "Unnamed") for a in activities])

    # Collect unique activity types from the activities list
    # Make sure each activity dict has a "type" key
    activity_types = sorted(set([a.get("type", "General") for a in activities]))

    # Add weather context if available
    weather_context = f" The expected weather is: {weather_summary}." if weather_summary else ""

    params = {
        "engine": "google_ai_mode",
        "q": (
            f"Compare the following activities near {place}: {activity_names}.{weather_context} "
            f"Group the comparison by activity type {activity_names}. "
            f"Loop through ALL activities and for each one, return:\n"
            f"- Name\n\n(with double line separate)- Why it stands out\n- Pros\n- Cons\n- Suitability\n\n"
            f"Always return the result in this exact format with explicit line breaks:\n\n"
            f"Only deliver the recommendations in this format. "
            f"Do not include tables, references, follow-up prompts, or links."
        ),
        "api_key": API_KEY
    }

    response = requests.get("https://serpapi.com/search", params=params)
    return response.json()



from serpapi import GoogleSearch

def search_weather(place, trip_date):
    """
    Query Google AI Mode API for a concise weather summary
    for the given place on a specific trip date.
    Returns the AI response dict.
    """
    trip_date_str = trip_date.strftime("%d-%m-%Y")

    params = {
        "engine": "google_ai_mode",
        "q": (
            f"Write exactly one plain sentence describing the expected weather in {place} "
            f"on {trip_date_str}. "
            f"The sentence must explicitly mention both the place name and the date ({trip_date_str}). "
            "Do not include references, headings, or markdown. "
            "Example: Weather in Kyoto on 09-07-2026 will be sunny with highs around 28°C."
        ),
        "api_key": API_KEY
    }

    search = GoogleSearch(params)
    return search.get_dict()

def ai_select_best_direction(transit_options, flight_data, travel_date, prev_formatted, curr_formatted):
    """
    Use AI to compare transit and flight direction results and select the best option.
    Handles cases where only transit or only flight data is available.
    If no parameters are received, return just the best option line.
    """

    # ✅ Guard clause: if no transit and no flight data
    if not transit_options and not flight_data:
        return "📝 AI Direction Recommendation\nBest Option: N/A\nReason: No travel options provided."

    # Collect transit summaries
    transit_summaries = []
    if transit_options:
        for option_no, d in enumerate(transit_options, start=1):
            transit_summaries.append(
                f"Transit Option {option_no}: {d.get('formatted_duration','N/A')} "
                f"({d.get('formatted_distance','N/A')}) "
                f"from {d.get('start_time','N/A')} to {d.get('end_time','N/A')}"
            )

    # Flight summary
    cleaned_flight = None
    if flight_data:
        flight_summary = flight_data.get("reconstructed_markdown", "")
        if flight_summary:
            cleaned_flight = flight_summary.split("### References")[0].strip()

    # Build AI query
    query_text = (
        f"Compare the following direction options for travel on {travel_date.strftime('%Y-%m-%d')} "
        f"from {prev_formatted} to {curr_formatted}.\n\n"
    )
    if transit_summaries:
        query_text += "Transit options:\n" + "\n".join(transit_summaries) + "\n\n"
    else:
        query_text += "No transit options available.\n\n"

    if cleaned_flight:
        query_text += f"Flight option:\n{cleaned_flight}\n\n"
    else:
        query_text += "No flight option available.\n\n"

    query_text += (
        "List ALL options clearly with their pros and cons. "
        "Explain what makes each option good or useful. "
        "Then select the single best option overall and explain why, "
        "but make sure to emphasize that the other options are also valid choices. "
        "Return ONLY in this exact format:\n\n"
        "📝 AI Direction Recommendation\n"
        "Options:\n"
        "- Transit Option X: Pros <...>, Cons <...>\n"
        "- Transit Option Y: Pros <...>, Cons <...>\n"
        "- Flight: Pros <...>, Cons <...> (or 'No flight option available')\n\n"
        "Best Option: <Transit X or Flight>\n"
        "Reason: <one clear reason while acknowledging others are also good>"
    )

    params = {
        "engine": "google_ai_mode",
        "q": query_text,
        "api_key": API_KEY,
    }

    try:
        response = requests.get("https://serpapi.com/search", params=params, timeout=30).json()
    except Exception as e:
        return f"📝 AI Direction Recommendation\nBest Option: N/A\nReason: API error: {e}"

    # Return only the formatted recommendation text
    if isinstance(response, dict):
        if response.get("answer"):
            return response["answer"].strip()
        if response.get("reconstructed_markdown"):
            return response["reconstructed_markdown"].strip()

    return "📝 AI Direction Recommendation\nBest Option: N/A\nReason: No recommendation available."




def search_flight_recommendation(origin, destination, flights, currency="USD", trip_type="roundtrip"):
    flight_summaries = []
    for f in flights:
        summary = (
            f"{f.get('airline', 'Unknown')} {f.get('flight_number', '')}, "
            f"Price: {currency} {f.get('price', 'N/A')}, "
            f"Dep: {f.get('departure_time', 'N/A')}, "
            f"Arr: {f.get('arrival_time', 'N/A')}, "
            f"Duration: {f.get('total_duration', 'N/A')} min"
        )
        flight_summaries.append(summary)

    flight_list = "; ".join(flight_summaries)

    query_text = (
        f"Compare the following {trip_type} flights from {origin} to {destination}: {flight_list}. "
        f"If trip_type is 'oneway', provide one clear recommendation for the best outbound flight only "
        f"and do NOT include any return flight recommendation. "
        f"If trip_type is 'roundtrip', provide one clear recommendation for both the best outbound flight "
        f"and the best return flight. "
        f"Strictly follow this format and do not add any other text, questions, or suggestions:\n\n"
        f"📝 AI Flight Recommendation\n"
        f"<One sentence overall recommendation>\n\n"
        f"🛫 Best Outbound Flight:\n<Name>\n\nWhy it is best: <reason>\n\n"
        f"🛬 Best Return Flight (only if roundtrip):\n<Name>\n\nWhy it is best: <reason>\n\n"
    )

    params = {"engine": "google_ai_mode", "q": query_text, "api_key": API_KEY}
    response = requests.get("https://serpapi.com/search", params=params)
    return response.json()


def build_itinerary_best_flight(origin, destination, flights, currency="USD"):
    """
    Build an itinerary prompt that asks the AI to select the single best flight overall.
    """

    flight_summaries = []
    for f in flights:
        summary = (
            f"{f.get('airline', 'Unknown')} {f.get('flight_number', '')}, "
            f"Price: {currency} {f.get('price', 'N/A')}, "
            f"Dep: {f.get('departure_time', 'N/A')}, "
            f"Arr: {f.get('arrival_time', 'N/A')}, "
            f"Duration: {f.get('total_duration', 'N/A')} min"
        )
        flight_summaries.append(summary)

    flight_list = "; ".join(flight_summaries)

    query_text = (
        f"Here are flights from {origin} to {destination}: {flight_list}. "
        f"Select the single best flight overall based on value, duration, and convenience. "
        f"Do NOT include separate outbound or return sections. "
        f"Strictly follow this format and do not add any other text, questions, or suggestions:\n\n"
        f"📝 AI Flight Recommendation\n"
        f"<One sentence overall recommendation>\n\n"
        f"✈️ Best Flight:\n<Name>\n\nWhy it is best: <reason>\n\n"
    )

    params = {"engine": "google_ai_mode", "q": query_text, "api_key": API_KEY}
    response = requests.get("https://serpapi.com/search", params=params)
    return response.json()


from serpapi import GoogleSearch

def get_autocomplete_suggestions(query: str, api_key: str):
    search = GoogleSearch({
        "engine": "google_autocomplete",
        "q": query,
        "hl": "en",
        "gl": "us",
        "api_key": api_key
    })
    results = search.get_dict()
    return results.get("suggestions", [])


import streamlit as st

# --- Custom Background (Japan themed via Imgur, h1 black only, widened content, white background for all tab panels) ---
page_bg_img = """
<style>
.stApp {
    background-image: url("https://i.ibb.co/JWgkvNcY/YOUR_IMAGE.jpg");
    background-size: cover !important;
    background-repeat: no-repeat !important;
    background-attachment: fixed !important;
}

/* Headings */
h1 {
    color: black !important;
    font-size: 2.4rem !important;
}

/* Widen main content area */
.block-container {
    max-width: 70% !important;
    padding-left: 2rem !important;
    padding-right: 2rem !important;
}

/* Apply white background to ALL tab panels */
div[id^="tabs-"][id$="-tabpanel-"] {
    background-color: white !important;
    border-radius: 8px !important;
    padding: 1.5rem !important;
    box-shadow: 0 0 10px rgba(0,0,0,0.1) !important;
    font-size: 1.5rem !important;
}

div[data-testid="stMarkdownContainer"] h1 {
    margin-top: 450px;   /* push title down */
    }
    
</style>
"""



# Apply background and width override
st.markdown(page_bg_img, unsafe_allow_html=True)


# --- Streamlit Frontend ---
st.title("Travel Planner ✈️")

planner = TravelPlanner("0dc318e5ab4947c89de4974f87dac201")

page_bg_img = """
<style>
/* Sidebar header */
section[data-testid="stSidebar"] h2 {
    font-size: 3rem !important;
    font-weight: bold !important;
    color: black !important;
    text-transform: uppercase;
    border-bottom: 2px solid #444 !important;
    padding-bottom: 0.5rem !important;
    margin-bottom: 1rem !important;
}

/* Sidebar input fields */
section[data-testid="stSidebar"] div[data-baseweb="input"] input {
    font-size: 20px !important;
    font-weight: 500 !important;
    color: white !important;
    padding: 0.5rem !important;
    background-color: #333 !important;
}

/* Sidebar background */
div[data-testid="stSidebarContent"] {
    background-image: url("https://i.ibb.co/JWgkvNcY/YOUR_IMAGE.jpg") !important;
    background-size: cover !important;
    background-position: center center !important;
    background-repeat: no-repeat !important;
    border-radius: 12px !important;
    padding: 1.5rem !important;
}

/* App background */
.stApp {
    background-color: #ffffff !important;
    background-image: none !important;
}

/* Search Flights button text */
button[data-testid="stBaseButton-secondary"] p {
    color: white !important;
    font-size: 18px !important;
    font-weight: 600 !important;
    margin: 0 !important;
}

/* Headings and labels */
h1, h2, h3, h4, h5, h6,
label, .stMarkdown,
.stRadio label, .stSelectbox label,
.stNumberInput label {
    color: black !important;
}

/* Origin City label */
div[data-testid="stMarkdownContainer"] p {
    color: black !important;
    font-size: 18px !important;
    font-weight: 600 !important;
    margin: 0.3rem 0 !important;
}

/* Search Flights button */
button[data-testid="stBaseButton-secondary"] {
    background-color: white !important;
    border: 2px solid #000 !important;
    border-radius: 5px !important;
    padding: 0.6rem 1.2rem !important;
}

/* Build Itinerary button */
button[data-testid="stBaseButton-primary"] {
    background-color: red !important;
    border: 2px solid #000 !important;
    border-radius: 6px !important;
    padding: 0.6rem 1.2rem !important;
}

/* Main content paragraphs */
div[data-testid="stMainBlockContainer"] p {
    font-size: 30px !important;
    font-weight: bold !important;
    color: #000 !important;
    margin: 0.5rem 0 !important;
}

/* Sidebar paragraphs */
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] h3 {
    font-size: 30px !important;
}
</style>
"""


st.markdown(page_bg_img, unsafe_allow_html=True)


# --- Sidebar Controls ---
with st.sidebar:
    st.header("Trip Settings")

    # Origin / Destination
    origin_city = st.text_input("Origin City", "hong kong")
    destination_city = st.text_input("Destination City", "Osaka")
    d1 = destination_city
    
    origin_codes = get_airports(origin_city)
    destination_codes = get_airports(destination_city)

    if origin_codes:
        origin_code = st.selectbox("Select Origin Airport Code", origin_codes)
    else:
        origin_code = origin_city       

    if destination_codes:
        destination_code = st.selectbox("Select Destination Airport Code", destination_codes)
    else:
        destination_code = destination_city

    st.write(f"Origin Airport Code: {origin_code}")
    st.write(f"Destination Airport Code: {destination_code}")

    # Itinerary builder inputs
    st.subheader("Build Itinerary")
    origins = origin_code
    destinations = destination_code
    check_in = st.date_input("Departure Date")
    check_out = st.date_input("Return Date")
    currency = st.selectbox("Currency", ["USD", "JPY", "EUR", "HKD"])
    trip_type = st.radio("Trip Type", ["oneway", "roundtrip"])
    budget = st.number_input("Budget per night(hotel)", min_value=50, max_value=3000, value=1000)
    activity_keywords = st.text_input("Activity Keywords", "temple ,park,restaurant,museum")

    # Location Query
    location_query = st.text_input(
        "Search location (one per day)",
        "Kyoto, Osaka Castle, Yokohama, Tokyo Tower"
    )

    # Transportation Selection
    transport_modes = st.multiselect(
            "Select Transportation Modes",
            ["Transit", "Flight"],
            default=["Transit"]
        )

    # ✅ AI enrichment toggle
    enable_ai = st.checkbox("AI Recommendations", value=True)
    
    # ✅ Map toggle button
    show_map = st.checkbox("Show Map of Results", value=True)
    
# --- Main Page Output ---
st.header("Results")
st.write("Flights, hotels, and activities will be displayed here based on your sidebar inputs.")



# --- Sidebar controls ---
#st.sidebar.header("Advanced Options")
#language = st.sidebar.text_input("Language code (optional)", "")
#countrycode = st.sidebar.text_input("Country code (optional)", "")
#limit = st.sidebar.number_input("Geocode result limit", min_value=1, max_value=5, value=1)
#radius = st.sidebar.number_input("Activity search radius (km)", min_value=1, max_value=50, value=5)



if st.sidebar.button("Search Flights"):
    
        # --- Custom CSS applied only after button click ---
    st.markdown("""
        <style>
        /* Sidebar */
        section:nth-of-type(2) > div:first-child {
            width: 2000px;             /* Reasonable fixed sidebar width */
            background-color: white;  /* White background */
            flex-shrink: 0;           /* Prevent shrinking */
            padding: 20px;            /* Spacing inside sidebar */
            position: sticky;         /* Sidebar stays visible when scrolling */
            top: 0;                   /* Stick to top of viewport */
            align-self: flex-start;   /* Align to top of parent */
        }

        /* Main content */
        section:nth-of-type(2) > div:nth-child(2) {
            flex: 1;                  /* Fill remaining space */
            padding: 35px;            /* Spacing inside content */
            margin-left: 20px;        /* Gap between sidebar and content */
            overflow-y: auto;         /* Allow vertical scrolling */
        }

        /* Global text styling */
        p, li {
            font-size: 35px !important;
            line-height: 1.5 !important;
            color: #000 !important;
        }

        /* Dataframe text */
        .stDataFrame div {
            font-size: 35px !important;
            color: #000 !important;
        }
        
        /* Target that exact <p> element */
        #root > div:nth-of-type(1) > div:nth-of-type(1) > div > div > section:nth-of-type(2) 
        > div:nth-of-type(1) > div > div > div:nth-of-type(14) > div > div > p:nth-of-type(1) {
            font-size: 35px !important;   /* change font size */
            font-weight: bold;            /* make text bold */
            color: #000000;               /* set text color */
            line-height: 1.6;             /* improve readability */
            margin: 12px 0;               /* spacing above/below */
        }

        /* Apply to ALL <p> elements inside the container at div[14] */
        #root > div:nth-of-type(1) > div:nth-of-type(1) > div > div > section:nth-of-type(2) 
        > div:nth-of-type(1) > div > div > div:nth-of-type(14) > div > div p {
            font-size: 35px !important;   /* change font size */
            font-weight: bold;            /* make text bold */
            color: #000000;               /* set text color */
            line-height: 1.6;             /* improve readability */
            margin: 12px 0;               /* spacing above/below */
        }
        /* Target ALL Markdown containers */
            div[data-testid="stMarkdownContainer"] p {
                font-size: 35px !important;   /* enlarge text */
                font-weight: bold;            /* optional */
                line-height: 1.6;             /* improve readability */
                color: #000000;               /* black text */
                margin: 12px 0;               /* spacing */
            }
            /* Target the specific h3 by id */
        h3#ai-flight-recommendation {
            font-size: 35px !important;   /* enlarge font size */
            font-weight: bold;            /* keep it bold */
            color: #000000;               /* black text */
            line-height: 1.4;             /* adjust spacing */
            margin: 16px 0;               /* spacing above/below */
        }

        /* Optionally, style all h3 headers globally */
        h3 {
            font-size: 35px !important;
            color: #000000 !important;
    }

        </style>
    """, unsafe_allow_html=True)
            
    # --- Flight Results Section ---
    with st.spinner("Finding the best flights..."):
        results = search_best_flight(
            origin_code,
            destination_code,
            str(check_in),
            currency,
            trip_type,
            return_date=str(check_out)
        )

    if not results.get("outbound_options") and not results.get("return_options"):
        st.warning("No flights found for these criteria.")
    else:
        st.subheader(f"✈️ {results.get('trip_type', 'Trip')} Results")

        # Define display settings
        column_settings = {
            "trip_label": "Trip Type",
            "price": st.column_config.NumberColumn("Price", format=f"{currency} %d"),
            "airline": "Carrier",
            "flight_number": "Flight No.",
            "route": "Route (Origin → Destination)",
            "departure_time": "Departure",
            "arrival_time": "Arrival",
            "total_duration": "Duration (min)",
            "travel_class": "Class"
        }

        display_columns = [
            "trip_label", "airline", "flight_number", "price", "route",
            "departure_time", "arrival_time", "total_duration"
        ]

        outbound_filtered, return_filtered = [], []

        # --- Outbound Section ---
        if results.get("outbound_options"):
            st.markdown("### 🛫 Outbound Flights")
            for opt in results["outbound_options"]:
                try:
                    if opt.get("price") is not None and float(opt["price"]) <= budget:
                        outbound_filtered.append(opt)
                except (TypeError, ValueError):
                    continue

            if not outbound_filtered:
                st.info("No outbound flights within your budget.")
            else:
                df_out = pd.DataFrame(outbound_filtered)
                df_out["trip_label"] = results.get("trip_type", "Trip")
                safe_cols = [c for c in display_columns if c in df_out.columns]
                st.dataframe(
                    df_out[safe_cols],
                    column_config=column_settings,
                    hide_index=True,
                    use_container_width=True
                )

        # --- Return Section ---
        if results.get("return_options"):
            st.markdown("🛬 **Return Flights**")
            for opt in results["return_options"]:
                try:
                    if opt.get("price") is not None and float(opt["price"]) <= budget:
                        return_filtered.append(opt)
                except (TypeError, ValueError):
                    continue

            if not return_filtered:
                st.info("No return flights within your budget.")
            else:
                df_ret = pd.DataFrame(return_filtered)
                df_ret["trip_label"] = results.get("trip_type", "Trip")
                safe_cols = [c for c in display_columns if c in df_ret.columns]
                st.dataframe(
                    df_ret[safe_cols],
                    column_config=column_settings,
                    hide_index=True,
                    use_container_width=True
                )

        # --- AI Recommendation (works for one-way and roundtrip) ---
        if enable_ai and (outbound_filtered or return_filtered):
            all_flights = outbound_filtered + return_filtered
            ai_data = search_flight_recommendation(
                origin_code,
                destination_code,
                all_flights,
                currency,
                trip_type=results["trip_type"]
            )

            st.markdown("### 📝 AI Flight Recommendation")
            ai_md = ai_data.get("reconstructed_markdown", "")
            if ai_md:
                cutoff_marker = "### References"
                extracted_text = ai_md.split(cutoff_marker)[0].strip() if cutoff_marker in ai_md else ai_md.strip()
                st.markdown(extracted_text, unsafe_allow_html=True)
            else:
                st.info("No AI flight recommendation available.")


import streamlit as st
import pandas as pd
import pydeck as pdk
from serpapi import GoogleSearch


# --- Search Hotels Button ---
if st.sidebar.button("Search Hotels"):
    # Split the input into multiple queries
    queries = [q.strip() for q in location_query.split(",") if q.strip()]

    if not queries:
        st.warning("Please enter at least one location query.")
    else:
        # 🎨 Inject CSS to transform tabs into a fixed vertical sidebar on the right
        st.markdown(
        """
        <style>
            /* Tabs container */
            div[data-testid="stTabs"] {
                margin-right: 220px !important;
            }
            /* 📄 Main content paragraphs */
            div[data-testid="stMainBlockContainer"] p {
                font-size: 35px !important;
                font-weight: bold !important;
            }
            /* 📄 Main content paragraphs */
            div[data-testid="stMainBlockContainer"] li {
                font-size: 40px !important;
            }
            
            
            div[data-baseweb="tab-list"][role="tablist"] {
                position: fixed !important;
                right: 30px;
                top: 600px;
                width: 350px !important;
                height: 350px !important;
                overflow-y: auto !important;
                z-index: 99999;
                border-left: 2px solid #e0e0e0;
                padding-left: 12px;
                background-color: white !important;
            }

            button[data-baseweb="tab"] {
                display: block !important;
                width: 100% !important;
                text-align: left !important;
                padding: 10px 14px !important;
                border-bottom: none !important;
            }

            div[data-baseweb="tab-highlight"] {
                display: none !important;
            }

            div[data-testid="stTabs"] div[data-testid="stTabContent"] {
                width: 100% !important;
            }

            /* DeckGL chart */
            div[data-testid="stDeckGlJsonChart"] {
                position: fixed !important;
                right: 0;
                top: 50px;
                width: 700px !important;
                height: 200px !important;
                z-index: 9999;
                border: 2px solid #000;
                border-radius: 8px;
                background-color: white;
            }

            /* Book Hotel link button */
            a[data-testid="stBaseLinkButton-secondary"] {
                background-color: white !important;
                color: black !important;
                border: 1px solid #ccc !important;
                padding: 8px 16px !important;
                border-radius: 4px !important;
                text-decoration: none !important;
            }

            /* Images */
            img {
                width: 500px !important;
                height: auto !important;
            }

            /* Sidebar + main content layout */
            section:nth-of-type(2) {
                display: flex;
                flex-direction: row;
                height: auto;
            }

            section:nth-of-type(2) > div:first-child {
                width: 4000px;
                background-color: white;
                flex-shrink: 0;
                padding: 20px;
                position: sticky;
                top: 0;
                align-self: flex-start;
            }

            /* Tab container flex layout */
            section:nth-of-type(2) > div:nth-of-type(1) > div > div > div:nth-of-type(7) > div > div:nth-of-type(1) > div {
                display: flex !important;
                flex-direction: column !important;
                align-items: flex-start !important;
                gap: 10px;
            }

            /* Button <p> text inside tab container */
            section:nth-of-type(2) > div:nth-of-type(1) > div > div > div:nth-of-type(7) > div > div:nth-of-type(1) > div > button > div > p {
                font-size: 2.5rem !important;
                line-height: 1.6 !important;
                color: #000 !important;
                font-weight: 600 !important;
            }
        </style>
        """,
        unsafe_allow_html=True
    )

        
        # --- Sidebar Sorting Option ---
        sort_option = st.sidebar.selectbox(
            "Sort Hotels By",
            [
                "Overall Rating (High → Low)",
                "Price (Low → High)",
                "Price (High → Low)"
            ],
            key="search_hotels_sort"
        )

        tabs = st.tabs(queries)

        # ✅ Start timer before processing all queries
        global_start = time.time()
        
        # --- Hotel Search Tabs ---
        for q, tab in zip(queries, tabs):
            with tab:
                hotel_params = {
                    "engine": "google_hotels",
                    "q": q,
                    "check_in_date": str(check_in),
                    "check_out_date": str(check_out),
                    "currency": currency,
                    "api_key": API_KEY,
                }

                # Spinner around the API call
                with st.spinner(f"Searching hotels near {q}..."):
                    raw_response = GoogleSearch(hotel_params).get_dict()
                    hotels = raw_response.get("properties", [])

                if not hotels:
                    st.warning(f"No hotels found for {q}.")
                else:
                    # ✅ Apply budget filter
                    budget_filtered = [
                        h for h in hotels
                        if h.get("rate_per_night", {}).get("extracted_lowest") is not None
                        and float(h["rate_per_night"]["extracted_lowest"]) <= budget
                    ]
                    # … continue with sorting and display logic …


                    # ✅ Apply sorting based on sidebar choice
                    if sort_option == "Overall Rating (High → Low)":
                        sorted_hotels = sorted(
                            budget_filtered,
                            key=lambda h: float(h.get("overall_rating", 0)),
                            reverse=True
                        )
                    elif sort_option == "Overall Rating (Low → High)":
                        sorted_hotels = sorted(
                            budget_filtered,
                            key=lambda h: float(h.get("overall_rating", 0))
                        )
                    elif sort_option == "Price (Low → High)":
                        sorted_hotels = sorted(
                            budget_filtered,
                            key=lambda h: float(h["rate_per_night"]["extracted_lowest"])
                        )
                    elif sort_option == "Price (High → Low)":
                        sorted_hotels = sorted(
                            budget_filtered,
                            key=lambda h: float(h["rate_per_night"]["extracted_lowest"]),
                            reverse=True
                        )
                    else:
                        sorted_hotels = budget_filtered


                    # --- Hotel Results Section ---
                    st.subheader(f"🏨 Hotels near {q} (Sorted by {sort_option})")

                    map_points = []  # collect hotel coordinates

                    for hotel in sorted_hotels[:5]:
                        st.markdown("---")
                        hotel_images = hotel.get("images", [])
                        if hotel_images and isinstance(hotel_images, list):
                            img_url = hotel_images[0].get("original_image") or hotel_images[0].get("thumbnail")
                            if img_url:
                                st.image(img_url, use_container_width=True)

                        hotel_name = hotel.get("name", "Unknown")
                        st.write(f"**{hotel_name}**")
                        st.write(f"⭐ Overall Rating: {hotel.get('overall_rating', 'N/A')} "
                                f"({hotel.get('reviews', 'N/A')} reviews)")
                        st.write(f"💰 Price per night: {hotel.get('rate_per_night', {}).get('lowest', 'N/A')} {currency}")
                        st.write(f"📍 Address: {hotel.get('address', '')}")
                        if hotel.get("link"):
                            st.link_button("Book Hotel", hotel["link"])

                        # ✅ Collect coordinates for map
                        if hotel.get("gps_coordinates"):
                            lat = hotel["gps_coordinates"].get("latitude")
                            lon = hotel["gps_coordinates"].get("longitude")
                            if lat and lon:
                                map_points.append({"lat": lat, "lon": lon, "name": hotel_name})

                    # ✅ AI enrichment step: overall recommendation
                    if enable_ai:   # only run if user enabled AI
                        ai_data = search_hotels_overall_recommendation(sorted_hotels[:5])

                        ai_md = ai_data.get("reconstructed_markdown", "")
                        if ai_md:
                            # Cut the text at the "### References" marker
                            cutoff_marker = "### References"
                            if cutoff_marker in ai_md:
                                extracted_text = ai_md.split(cutoff_marker)[0].strip()
                            else:
                                extracted_text = ai_md.strip()

                            st.markdown("### 📝 AI Overall Hotel Recommendation")
                            st.write(extracted_text)
                        else:
                            st.info("No AI overall recommendation available.")

                    # ✅ Show map if points exist
                    if show_map and map_points:   # only run if user enabled map
                        df = pd.DataFrame(map_points)
                        st.pydeck_chart(pdk.Deck(
                            map_style="mapbox://styles/mapbox/streets-v11",
                            initial_view_state=pdk.ViewState(
                                latitude=df["lat"].mean(),
                                longitude=df["lon"].mean(),
                                zoom=12,
                                pitch=0,
                            ),
                            layers=[
                                pdk.Layer(
                                    "ScatterplotLayer",
                                    data=df,
                                    get_position='[lon, lat]',
                                    get_color='[0, 100, 200, 160]',
                                    get_radius=100,
                                ),
                                pdk.Layer(
                                    "TextLayer",
                                    data=df,
                                    get_position='[lon, lat]',
                                    get_text="name",
                                    get_size=14,
                                    get_color=[0, 0, 0],
                                )
                            ],
                        ))
                    elif show_map:
                        st.info("No hotels available to display on the map.")
                        
        # ✅ End timer after loop finishes
        global_elapsed = time.time() - global_start
        st.success(f"⏱ All hotel searches completed in {global_elapsed:.2f} seconds")




                        
import streamlit as st
import pandas as pd
import pydeck as pdk
from serpapi import GoogleSearch

# --- Search Activities Button ---
if st.sidebar.button("Search Activities"):
    queries = [q.strip() for q in location_query.split(",") if q.strip()]
    keywords = [kw.strip() for kw in activity_keywords.split(",") if kw.strip()]

    st.subheader("🎯 Optimized Activity Itinerary")

    # Geocode destination airport explicitly with full name
    airport_query = f"{destination_code}"  # or use ICAO like "RJFF" if supported
    airport_coords = planner.geocode_location(airport_query, limit=1)

    if not airport_coords:
        st.error("Could not resolve destination airport.")
    else:   
        origin_lat, origin_lng, origin_fmt = airport_coords[0]

        # ✅ Give airport a unique node name
        airport_node = f"{destination_code} Airport"

        # Geocode each location
        coords = {}
        formatted_names = {}
        for q in queries:
            loc = planner.geocode_location(q, limit=1)
            if loc:
                lat, lng, formatted = loc[0]
                coords[q] = (lat, lng)
                formatted_names[q] = formatted

        # --- Add airport with unique node key ---
        airport_node = f"{destination_code} Airport"

        # ✅ Store actual airport coordinates under airport_node
        coords[airport_node] = (origin_lat, origin_lng)

        # ✅ Store a clear display string for UI
        formatted_names[airport_node] = f"{airport_node} ({origin_fmt})"

        # Build node list including airport
        all_nodes = [airport_node] + queries

        # Build MST + itinerary order with spinner
        with st.spinner("Building optimized itinerary..."):
            mst = kruskal_mst(all_nodes, coords, haversine)
            itinerary_order = traverse_mst(mst, airport_node)


        # 🎨 Inject the precise CSS target block for your tab-list structure
        st.markdown(
            """
            <style>
                /* 1. Prevent your main tab contents from running underneath the fixed menu */
                div[data-testid="stTabs"] {
                    margin-right: 250px !important;
                }

                /* 2. Target your exact 'tab-list' HTML wrapper element and anchor it to the window viewport */
                div[data-baseweb="tab-list"][role="tablist"] {
                    position: fixed !important;
                    right: 30px;
                    top: 600px;
                    flex-direction: column !important;
                    width: 250px;
                    height: 250px;                 /* Explicit fixed height */
                    overflow-y: auto;              /* Scroll if content exceeds height */
                    z-index: 99999;
                    border-bottom: none !important;
                    border-left: 2px solid #e0e0e0;
                    padding-left: 12px;
                    background-color: White;
                }
                
                /* Markdown container paragraphs */
                div[data-testid="stMarkdownContainer"] p {
                    font-size: 2rem !important; /* adjust globally */
                    font-weight: 600 !important;
                    color: black !important;
                }
                /* Markdown container paragraphs */
                div[data-testid="stMarkdownContainer"] li, h3, h4 {
                    font-size: 2.5rem !important; /* adjust globally */
                    font-weight: 600 !important;
                    color: black !important;
                }
                    border-bottom: none !important;     /* Removes the native horizontal underline layout */
                    border-left: 2px solid #e0e0e0;     /* Replaces it with a clean vertical divider line */
                    padding-left: 14px;
                    background-color: White;
                }

                /* 3. Force individual buttons inside your element to act like vertical row block tags */
                button[data-baseweb="tab"] {
                    display: block !important;
                    width: 100% !important;
                    text-align: left !important;        /* Align your locations (Kushida Shrine, Busan, etc.) to the left */
                    padding: 10px 14px !important;
                    border-bottom: none !important;     /* Eliminates individual bottom borders */
                }

                /* 4. Kill the native horizontal moving indicator bar that causes visual styling breaks when vertical */
                div[data-baseweb="tab-highlight"] {
                    display: none !important;
                }

                /* 5. Keep content container boundaries fluid */
                div[data-testid="stTabs"] div[data-testid="stTabContent"] {
                    width: 100% !important;
                }
                
                /* 🎨 Make the 'View Activity' link button white */
                a[data-testid="stBaseLinkButton-secondary"] {
                    background-color: white !important;   /* button background white */
                    border: 2px solid #000 !important;    /* optional: black border for contrast */
                    border-radius: 6px !important;        /* rounded corners */
                    padding: 0.6rem 1.2rem !important;    /* spacing inside button */
                    display: inline-block !important;     /* ensure proper button-like rendering */
                    text-decoration: none !important;     /* remove underline */
                }
                div[data-testid="stDeckGlJsonChart"] {
                    position: fixed !important;
                    right: 0;             /* distance from right edge */
                    top: 50px;               /* distance from top edge */
                    width: 700px !important;
                    height: 400px !important;
                    z-index: 9999;
                    border: 2px solid #000;
                    border-radius: 8px;
                    background-color: white;
                }
                /* Target strong tags inside your activity containers */
                div[data-testid="stMarkdownContainer"] strong {
                    font-size: 28px !important;   /* make it larger */
                    font-weight: 700 !important;  /* ensure boldness */
                    color: #000000 !important;    /* keep it black for clarity */
                }


                /* Shrink all images */
                img {
                    width: 500px !important;   /* fixed smaller width */
                    height: auto !important;   /* keep aspect ratio */
                }
                /* Target the container at /html/body/div[1]/div[1]/div[1]/div/div/section[2]/div[1] */
                html body > div:nth-of-type(1) > div:nth-of-type(1) > div:nth-of-type(1) > div > div > section:nth-of-type(2) > div:nth-of-type(1) {
                background-color: white;
                padding: 15px;        /* optional: add spacing */
                border-radius: 6px;   /* optional: rounded corners */
                }

                
                /* Target the container at /html/body/div[1]/div[1]/div[1]/div/div/section[2]/div[1] */
                html body > div:nth-of-type(1) > div:nth-of-type(1) > div:nth-of-type(1) > div > div > section:nth-of-type(2) > div:nth-of-type(1) {
                background-color: white;            
                padding: 15px;        /* optional: add spacing */
                border-radius: 6px;   /* optional: rounded corners */
                }

                /* Parent container: sidebar + main content */
                section:nth-of-type(2) {
                    display: flex;              /* Horizontal layout */
                    flex-direction: row;
                    height: auto;               /* Let content define height */
                }

                /* Sidebar */
                section:nth-of-type(2) > div:first-child {
                    width: 2000px;               /* Fixed sidebar width */
                    background-color: white;    /* White background */
                    flex-shrink: 0;             /* Prevent shrinking */
                    padding: 20px;              /* Optional spacing */
                    position: sticky;           /* Sidebar stays visible when scrolling */
                    top: 0;                     /* Stick to top of viewport */
                    align-self: flex-start;     /* Align to top of parent */
                }



            </style>
            """,
            unsafe_allow_html=True
        )

        st.write("### Optimized Itinerary (via Kruskal MST):")
        for day in range(1, len(itinerary_order)):
            prev_place = itinerary_order[day-1]
            curr_place = itinerary_order[day]
            dist = haversine(*coords[prev_place], *coords[curr_place])
            prev_fmt = formatted_names.get(prev_place, prev_place)
            curr_fmt = formatted_names.get(curr_place, curr_place)
            st.write(f"Day {day}: {curr_fmt} ({dist:.1f} km from {prev_fmt})")

        # ✅ Create tabs for each location (skip airport)
        itinerary_places = itinerary_order[1:]
        if not itinerary_places:
            st.warning("No destinations found in the generated route.")
        else:
            tabs = st.tabs(itinerary_places)
                    
        # --- Activity Tabs ---
        for day, (place, tab) in enumerate(zip(itinerary_places, tabs), start=1):
            with tab:
                lat, lng = coords[place]
                st.markdown(f"### 🏛️ Activities near {place}")

                map_points = []
                collected_activities = []  # store activities for AI recommendation

                for kw in keywords:
                    st.markdown(f"#### 🔎 Searching for {kw} near {place}")
                    activity_params = {
                        "engine": "google_maps",
                        "q": f"{kw} near {place}",
                        "ll": f"@{lat},{lng},14z",
                        "type": "search",
                        "api_key": API_KEY
                    }
                    
                    # Spinner around the API call
                    with st.spinner(f"Searching {kw} near {place}..."):
                        try:
                            act_search = GoogleSearch(activity_params)
                            act_response = act_search.get_dict()
                            act_data = act_response.get("local_results", [])
                        except Exception as e:
                            st.error(f"Error calling Maps API: {e}")
                            act_data = []

                    if act_data:
                        for idx, act in enumerate(act_data[:3], start=1):
                            collected_activities.append(act)  # save for recommendation
                            with st.container(border=True):
                                if act.get("thumbnail"):
                                    st.image(act["thumbnail"], use_container_width=True)
                                st.write(f"**#{idx} {act.get('title', 'Unnamed')}**")
                                st.write(f"⭐ {act.get('rating', 'N/A')} | {act.get('type', 'N/A')}")
                                if act.get("address"):
                                    st.write(f"📍 {act['address']}")

                                description = act.get("description") or act.get("snippet")
                                if description:
                                    st.markdown(f"_{description}_")

                                comment = act.get("user_review")
                                if not comment and act.get("data_id"):
                                    try:
                                        review_params = {
                                            "engine": "google_maps_reviews",
                                            "data_id": act["data_id"],
                                            "api_key": API_KEY
                                        }
                                        review_search = GoogleSearch(review_params)
                                        reviews_data = review_search.get_dict().get("reviews", [])
                                        if reviews_data and reviews_data[0].get("snippet"):
                                            comment = reviews_data[0]["snippet"]
                                    except Exception:
                                        comment = None
                                        
                                if comment:
                                    st.markdown(f"> 💬 *\"{comment}\"*")
                                if act.get("website"):
                                    st.link_button("View Activity", act["website"])

                            # ✅ Collect coordinates for map
                            if act.get("gps_coordinates"):
                                lat_act = act["gps_coordinates"].get("latitude")
                                lng_act = act["gps_coordinates"].get("longitude")
                                if lat_act and lng_act:
                                    map_points.append({
                                        "lat": lat_act,
                                        "lon": lng_act,
                                        "name": act.get("title", f"Activity {idx}")
                                    })
                    else:
                        st.write(f"No {kw} found near {place}.")
                        

                from datetime import timedelta
                import streamlit as st

                # ✅ AI enrichment step: separate weather + activities
                if collected_activities:    
                    # Calculate the actual date for this itinerary day
                    trip_date = check_in + timedelta(days=day-1)
                    trip_date_str = trip_date.strftime("%d-%m-%Y")

                    # Weather AI call (include actual date)
                    if enable_ai:   # only run if user enabled AI
                        weather_data = search_weather(place, trip_date)
                        st.markdown("### 🌤️ Weather Summary")
                        weather_md = weather_data.get("reconstructed_markdown", "")
                        if weather_md:
                            st.markdown(weather_md.strip(), unsafe_allow_html=True)
                        else:
                            st.info("No AI weather summary available.")
                    else:
                        weather_md = ""  # skip AI call if disabled
                                            
                    # Activity AI call (pass weather context)
                    if enable_ai:   # only run if user enabled AI
                        ai_data = search_activity_recommendation(
                            place,
                            collected_activities,
                            weather_summary=weather_md.strip() if weather_md else None
                        )


                        # ✅ Retrieve reconstructed_markdown and strip references
                        st.markdown("### 📝 AI Activity Recommendation")
                        ai_md = ai_data.get("reconstructed_markdown", "")
                        if ai_md:
                            cutoff_marker = "### References"
                            if cutoff_marker in ai_md:
                                extracted_text = ai_md.split(cutoff_marker)[0].strip()
                            else:
                                extracted_text = ai_md.strip()

                            # Show the markdown exactly as returned, minus references
                            st.markdown(extracted_text, unsafe_allow_html=True)
                        else:
                            st.info("No AI activity recommendation available.")


                # ✅ Show map if points exist
                if show_map and map_points:   # only run if user enabled map
                    df = pd.DataFrame(map_points)
                    st.pydeck_chart(pdk.Deck(
                        map_style="mapbox://styles/mapbox/streets-v11",
                        initial_view_state=pdk.ViewState(
                            latitude=df["lat"].mean(),
                            longitude=df["lon"].mean(),
                            zoom=12,
                            pitch=0,
                        ),
                        layers=[
                            pdk.Layer(
                                "ScatterplotLayer",
                                data=df,
                                get_position='[lon, lat]',
                                get_color='[200, 30, 0, 160]',
                                get_radius=80,
                            ),
                            pdk.Layer(
                                "TextLayer",
                                data=df,
                                get_position='[lon, lat]',
                                get_text="name",
                                get_size=14,
                                get_color=[0, 0, 0],
                            )
                        ],
                    ))
                elif show_map:
                    st.info("No activities available to display on the map.")


import requests
import streamlit as st 
from datetime import timedelta


def search_flights_google_ai(origin_code, destination_code, travel_date):
    """
    Query Google AI Mode API for flights between origin and destination on a given date.
    """
    params = {
        "engine": "google_ai_mode",
        "q": f"flights from {origin_code} to {destination_code} at {travel_date.strftime('%Y-%m-%d')}",
        "api_key": API_KEY
    }
    response = requests.get("https://serpapi.com/search", params=params)
    return response.json()



# --- Search Directions Button ---
if st.sidebar.button("Search Directions"):
    queries = [q.strip() for q in location_query.split(",") if q.strip()]
    st.subheader("🚍 Transportation Advice for Itinerary")

    # Geocode destination airport explicitly with full name
    airport_query = f"{destination_code}"  # use ICAO like "RJFF" if supported
    airport_coords = planner.geocode_location(airport_query, limit=1)

    if not airport_coords:
        st.error("Could not resolve destination airport.")
    else:   
        origin_lat, origin_lng, origin_fmt = airport_coords[0]

        # ✅ Give airport a unique node name
        airport_node = f"{destination_code} Airport"

        # Geocode each location
        coords = {}
        formatted_names = {}
        for q in queries:
            loc = planner.geocode_location(q, limit=1)
            if loc:
                lat, lng, formatted = loc[0]
                coords[q] = (lat, lng)
                formatted_names[q] = formatted
                
                
                
# 🎨 Inject CSS to isolate and fix the dynamic Day tabs to the right side of the page
        st.markdown(
            """
            <style>
                /* 1. Shift the main content container to the left so it clears the fixed right menu */
                div[data-testid="stTabs"] {
                    margin-right: 240px !important;
                }

                        /* Markdown container paragraphs */
                div[data-testid="stMarkdownContainer"] p, h3, h4, li {
                    font-size: 35px !important;
                    line-height: 1.6 !important;

                }
                /* 2. Target your exact 'tab-list' HTML wrapper element and anchor it to the window viewport */
                div[data-baseweb="tab-list"][role="tablist"] {
                    position: fixed !important;
                    right: 30px;
                    top: 600px;
                    flex-direction: column !important;
                    width: 180px;
                    height: 250px;                 /* Explicit fixed height */
                    overflow-y: auto;              /* Scroll if content exceeds height */
                    z-index: 99999;
                    border-bottom: none !important;
                    border-left: 2px solid #e0e0e0;
                    padding-left: 12px;
                    background-color: White;
                }

                /* 3. Force the individual Day buttons to expand to the container width */
                button[data-baseweb="tab"] {
                    display: block !important;
                    width: 100% !important;
                    text-align: left !important;        /* Left-aligns your 'Day 1', 'Day 2' labels cleanly */
                    padding: 10px 14px !important;
                    border-bottom: none !important;     /* Eliminates default bottom highlights */
                }

                /* 4. Kill the active 'tab-highlight' accent element which goes sideways when turned vertical */
                div[data-baseweb="tab-highlight"] {
                    display: none !important;
                }

                /* 5. Force the main display cards canvas layer to stretch out properly */
                div[data-testid="stTabs"] div[data-testid="stTabContent"] {
                    width: 100% !important;
                }
                
                div[data-testid="stDeckGlJsonChart"] {
                    position: fixed !important;
                    right: 0;             /* distance from right edge */
                    top: 50px;               /* distance from top edge */
                    width: 700px !important;
                    height: 200px !important;
                    z-index: 9999;
                    border: 2px solid #000;
                    border-radius: 8px;
                    background-color: white;
                }
                

                /* Target the container at /html/body/div[1]/div[1]/div[1]/div/div/section[2]/div[1] */
                html body > div:nth-of-type(1) > div:nth-of-type(1) > div:nth-of-type(1) > div > div > section:nth-of-type(2) > div:nth-of-type(1) {
                background-color: white;            
                padding: 15px;        /* optional: add spacing */
                border-radius: 6px;   /* optional: rounded corners */
                }

                /* Parent container: sidebar + main content */
                section:nth-of-type(2) {
                    display: flex;              /* Horizontal layout */
                    flex-direction: row;
                    height: auto;               /* Let content define height */
                }

                /* Sidebar */
                section:nth-of-type(2) > div:first-child {
                    width: 2000px;               /* Fixed sidebar width */
                    background-color: white;    /* White background */
                    flex-shrink: 0;             /* Prevent shrinking */
                    padding: 20px;              /* Optional spacing */
                    position: sticky;           /* Sidebar stays visible when scrolling */
                    top: 0;                     /* Stick to top of viewport */
                    align-self: flex-start;     /* Align to top of parent */
                }


                /Apply font styling to ALL <p> elements inside ANY tab panel */
                [id^="tabs-bui16-tabpanel"] p,
                [id^="tabs-bui16-tabpanel"] p * {
                    font-size: 30px !important;   /* Adjust to your preferred size */
                    line-height: 1.5 !important;  /* Optional readability */
                    color: #000 !important;       /* Ensure visible text */
                }



            </style>
            """,
            unsafe_allow_html=True
        )
        from datetime import timedelta

        # --- Add airport with unique node key ---
        airport_node = f"{destination_code} Airport"

        # ✅ Store actual airport coordinates under airport_node
        coords[airport_node] = (origin_lat, origin_lng)

        # ✅ Store a clear display string for UI
        formatted_names[airport_node] = f"{airport_node} ({origin_fmt})"

        # Build node list including airport
        all_nodes = [airport_node] + queries

        # Build MST + itinerary order with spinner
        with st.spinner("Building optimized itinerary..."):
            mst = kruskal_mst(all_nodes, coords, haversine)
            itinerary_order = traverse_mst(mst, airport_node)

        # --- Create tabs for each travel day ---
        day_tabs = st.tabs([f"Day {i+1}" for i in range(len(itinerary_order) - 1)])

        # Loop through MST edges
        for i in range(len(itinerary_order) - 1):
            prev_place = itinerary_order[i]
            curr_place = itinerary_order[i+1]

            # ✅ Direct coordinate lookup
            prev_lat, prev_lng = coords[prev_place]
            curr_lat, curr_lng = coords[curr_place]
            dist = haversine(prev_lat, prev_lng, curr_lat, curr_lng)

            # Travel date
            travel_date = check_in + timedelta(days=i)

            # Use stored formatted names (with fallback)
            prev_formatted = formatted_names.get(prev_place, prev_place)
            curr_formatted = formatted_names.get(curr_place, curr_place)

            # Render inside the correct tab
            with day_tabs[i]:
                st.markdown(
                    f"### Day {i+1}: Travel from {prev_formatted} → {curr_formatted} "
                    f"({dist:.1f} km) on {travel_date.strftime('%Y-%m-%d')}"
                )

                # Spinner around directions API call
                with st.spinner(f"Fetching transit directions from {prev_formatted} to {curr_formatted}..."):
                    try:
                        raw_data = get_directions_raw(prev_formatted, curr_formatted, mode="transit")
                        directions = raw_data.get("directions", [])
                        transit_options = [d for d in directions if d.get("travel_mode") == "Transit"]
                    except Exception as e:
                        st.error(f"Error fetching directions: {e}")
                        transit_options = []


                # --- Case 1: Both Flight + Transit ---
                if "Flight" in transport_modes and "Transit" in transport_modes:  
                    # Call your flight search function
                    flight_data = search_flights_google_ai(prev_formatted, curr_formatted, travel_date)

                    # Show raw API response for debugging
                    st.markdown("**Raw Flight API Response:**")

                    # --- Show AI narrative (structured Markdown without References) ---
                    reconstructed_md = flight_data.get("reconstructed_markdown", "")
                    if reconstructed_md:
                        cleaned_md = reconstructed_md.split("### References")[0].strip()
                        st.markdown("### 📝 AI Flight Summary")
                        st.markdown(cleaned_md, unsafe_allow_html=True)
                    else:
                        st.warning("No reconstructed_markdown found in response.")

                    # Transit options
                    for option_no, d in enumerate(transit_options, start=1):
                        st.markdown(
                            f"#### 🚇 Transit Option {option_no} "
                            f"(Itinerary Date: {travel_date.strftime('%Y-%m-%d')}, API Date: {d.get('date','N/A')})"
                        )
                        st.write(f"🕓 Departure: {d.get('start_time','N/A')} → Arrival: {d.get('end_time','N/A')}")
                        st.write(f"📏 Total Distance: {d.get('formatted_distance','N/A')}")
                        st.write(f"⌛ Estimated Duration: {d.get('formatted_duration','N/A')}")
                        if d.get("icon"):
                            st.image(d["icon"], width=40)

                        for trip in d.get("trips", []):
                            st.markdown(f"**{trip.get('title','Unnamed')}** ({trip.get('formatted_duration','N/A')})")
                            if trip.get("start_stop") and trip.get("end_stop"):
                                st.write(
                                    f"From {trip['start_stop'].get('name','Unknown')} at {trip['start_stop'].get('time','N/A')} → "
                                    f"{trip['end_stop'].get('name','Unknown')} at {trip['end_stop'].get('time','N/A')}"
                                )
                            for stop in trip.get("stops", []):
                                st.write(f"- Stop: {stop.get('name','Unknown')} ({stop.get('time','N/A')})")
                            if trip.get("service_run_by"):
                                st.write(f"Operated by: {trip['service_run_by'].get('name','Unknown')}")
                                if trip['service_run_by'].get("link"):
                                    st.write(f"Website: {trip['service_run_by']['link']}")
                            if trip.get("icon"):
                                st.image(trip["icon"], width=40)
                            if trip.get("travel_mode") == "Walking":
                                st.write("🚶 Walking Segment:")
                                for step in trip.get("details", []):
                                    st.write(f"- {step.get('title','Step')} ({step.get('formatted_duration','N/A')})")
                                    if step.get("geo_photo"):
                                        st.image(step["geo_photo"], width=200)

                    # --- AI Best Direction Recommendation ---
                    if enable_ai:   # only run if user enabled AI
                        ai_answer = ai_select_best_direction(
                            transit_options,
                            flight_data,
                            travel_date,
                            prev_formatted,
                            curr_formatted
                        )
                        st.markdown("### 🧠 AI Best Direction Recommendation")
                        st.write(ai_answer)
                    else:
                        st.info("AI Best Direction Recommendation disabled.")

                # --- Case 2: Transit only ---
                elif "Transit" in transport_modes:  
                    for option_no, d in enumerate(transit_options, start=1):
                        st.markdown(
                            f"#### 🚇 Transit Option {option_no} "
                            f"(Itinerary Date: {travel_date.strftime('%Y-%m-%d')}, API Date: {d.get('date','N/A')})"
                        )
                        st.write(f"🕓 Departure: {d.get('start_time','N/A')} → Arrival: {d.get('end_time','N/A')}")
                        st.write(f"📏 Total Distance: {d.get('formatted_distance','N/A')}")
                        st.write(f"⌛ Estimated Duration: {d.get('formatted_duration','N/A')}")
                        if d.get("icon"):
                            st.image(d["icon"], width=40)

                        for trip in d.get("trips", []):
                            st.markdown(f"**{trip.get('title','Unnamed')}** ({trip.get('formatted_duration','N/A')})")
                            if trip.get("start_stop") and trip.get("end_stop"):
                                st.write(
                                    f"From {trip['start_stop'].get('name','Unknown')} at {trip['start_stop'].get('time','N/A')} → "
                                    f"{trip['end_stop'].get('name','Unknown')} at {trip['end_stop'].get('time','N/A')}"
                                )
                            for stop in trip.get("stops", []):
                                st.write(f"- Stop: {stop.get('name','Unknown')} ({stop.get('time','N/A')})")
                            if trip.get("service_run_by"):
                                st.write(f"Operated by: {trip['service_run_by'].get('name','Unknown')}")
                                if trip['service_run_by'].get("link"):
                                    st.write(f"Website: {trip['service_run_by']['link']}")
                            if trip.get("icon"):
                                st.image(trip["icon"], width=40)
                            if trip.get("travel_mode") == "Walking":
                                st.write("🚶 Walking Segment:")
                                for step in trip.get("details", []):
                                    st.write(f"- {step.get('title','Step')} ({step.get('formatted_duration','N/A')})")
                                    if step.get("geo_photo"):
                                        st.image(step["geo_photo"], width=200)

                    # --- AI Transit Recommendation ---
                    if enable_ai:   # only run if user enabled AI
                        # Call the function
                        ai_answer = ai_select_best_direction(
                            transit_options,
                            None,  # no flight data
                            travel_date,
                            prev_formatted,
                            curr_formatted
                        )

                        # Show the formatted AI answer
                        st.markdown("### 🧠 AI Transit Recommendation")
                        st.write(ai_answer)

                        # 🔎 Show the entire API response for debugging
                        try:
                            params = {
                                "engine": "google_ai_mode",
                                "q": "Debugging full response",  # you can reuse the same query_text
                                "api_key": API_KEY,
                            }
                            response = requests.get("https://serpapi.com/search", params=params, timeout=30).json()
                        except Exception as e:
                            st.error(f"Error retrieving full API response: {e}")
                    else:
                        st.info("AI Transit Recommendation disabled.")

                # --- Case 3: Flight only ---
                else:
                    # Call your flight search function
                    flight_data = search_flights_google_ai(prev_formatted, curr_formatted, travel_date)

                    # Show raw API response for debugging
                    st.markdown("**Raw Flight API Response:**")

                    # --- Show AI narrative (structured Markdown without References) ---
                    reconstructed_md = flight_data.get("reconstructed_markdown", "")
                    if reconstructed_md:
                        # Remove trailing "### References" section if present
                        cleaned_md = reconstructed_md.split("### References")[0].strip()
                        st.markdown("### 📝 AI Flight Summary")
                        st.markdown(cleaned_md, unsafe_allow_html=True)
                    else:
                        st.warning("No reconstructed_markdown found in response.")

                    # --- AI Flight Recommendation ---
                    if enable_ai:   # only run if user enabled AI
                        ai_answer = ai_select_best_direction(
                            None,
                            flight_data,
                            travel_date,
                            prev_formatted,
                            curr_formatted
                        )
                        st.markdown("### 🧠 AI Flight Recommendation")
                        st.write(ai_answer)
                    else:
                        st.info("AI Flight Recommendation disabled.")

                    # ✅ Map visualization for this leg

                # 重新 geocode，確保座標正確
                geo_prev = planner.geocode_location(prev_formatted, limit=1)
                if geo_prev and len(geo_prev) > 0:
                    prev_lat, prev_lng, _ = geo_prev[0]

                geo_curr = planner.geocode_location(curr_formatted, limit=1)
                if geo_curr and len(geo_curr) > 0:
                    curr_lat, curr_lng, _ = geo_curr[0]

                map_points = [
                    {"lat": prev_lat, "lon": prev_lng, "name": prev_formatted},
                    {"lat": curr_lat, "lon": curr_lng, "name": curr_formatted}
                ]

                if show_map and map_points:   # only run if user enabled map
                    df = pd.DataFrame(map_points)

                    st.pydeck_chart(
                        pdk.Deck(
                            map_style="mapbox://styles/mapbox/streets-v11",
                            initial_view_state=pdk.ViewState(
                                latitude=df["lat"].mean(),
                                longitude=df["lon"].mean(),
                                zoom=10,
                                pitch=0,
                            ),
                            layers=[
                                pdk.Layer(
                                    "ScatterplotLayer",
                                    data=df,
                                    get_position='[lon, lat]',
                                    get_color='[200, 30, 0, 160]',
                                    get_radius=120
                                ),
                                pdk.Layer(
                                    "TextLayer",
                                    data=df,
                                    get_position='[lon, lat]',
                                    get_text="name",
                                    get_size=14,
                                    get_color=[0, 0, 0]
                                ),
                                pdk.Layer(
                                    "LineLayer",
                                    data=pd.DataFrame([{
                                        "lon_start": prev_lng, "lat_start": prev_lat,
                                        "lon_end": curr_lng, "lat_end": curr_lat
                                    }]),
                                    get_source_position='[lon_start, lat_start]',
                                    get_target_position='[lon_end, lat_end]',
                                    get_color=[0, 128, 255],
                                    get_width=4
                                )
                            ],
                        )
                    )
                elif show_map:
                    st.info("No route coordinates available to display on the map.")


        
from datetime import datetime, timedelta

# --- Declare global sorting option once (always visible) ---
if 'hotel_sort_option' not in st.session_state:
    st.session_state['hotel_sort_option'] = "Overall Rating (High → Low)"  # default

global_sort_option = st.sidebar.selectbox(
    "Sort Hotels By (Build Itinerary)",
    [
        "Overall Rating (High → Low)",
        "Price (Low → High)",
        "Price (High → Low)"
    ],
    key="hotel_sort_global",
    index=[
        "Overall Rating (High → Low)",
        "Price (Low → High)",
        "Price (High → Low)"
    ].index(st.session_state['hotel_sort_option'])  # keep last choice
)

# Save back to session_state so it persists
st.session_state['hotel_sort_option'] = global_sort_option
# --- Build Itinerary Button ---
if st.sidebar.button("Build Itinerary", type="primary"):
    # Split queries into a list

    day_queries = [q.strip() for q in location_query.split(",") if q.strip()]
    keywords = [kw.strip() for kw in activity_keywords.split(",") if kw.strip()]
    origin_list = [o.strip() for o in origins.split(",")]
    dest_list = [d.strip() for d in destinations.split(",")]
    
    dates = [{"check_in": str(check_in), "check_out": str(check_out)} for _ in dest_list]

    # Shared formatting for all flight tables
    column_settings = {
        "trip_label": "Trip Type",
        "price": st.column_config.NumberColumn("Price", format=f"{currency} %d"),
        "airline": "Carrier",
        "flight_number": "Flight No.",   # ✅ Added flight number
        "route": "Route (Origin → Destination)",
        "departure_time": "Departure",
        "arrival_time": "Arrival",
        "total_duration": "Duration (min)",
    }


    display_columns = [
        "trip_label",
        "airline",
        "flight_number",   # ✅ Added flight number
        "price",
        "route",
        "departure_time",
        "arrival_time",
        "total_duration"
    ]
    
    for origin, destination_city, date in zip(origin_list, dest_list, dates):
        st.header(f"📍 Trip: {origin} → {destination_city}")

        # Fetch flights once per trip
        with st.spinner(f"Searching flights for {destination_city}..."):
            results = search_best_flight(
                origin,
                destination_city,
                date["check_in"],
                currency,
                trip_type,
                return_date=date["check_out"]
            )

        # Setup timeline
        start_date = datetime.strptime(date["check_in"], "%Y-%m-%d")
        end_date = datetime.strptime(date["check_out"], "%Y-%m-%d")
        num_days = max(1, (end_date - start_date).days + 1)
        
        # Airport node setup
        airport_node = f"{destination_code} Airport"
        airport_coords = planner.geocode_location(airport_node, limit=1)

        if not airport_coords:
            st.error(f"Could not geocode airport {destination_code}.")
            base_date = datetime.strptime(date["check_in"], "%Y-%m-%d")
            location_distances = [
                (q, q, None, None, None, base_date + timedelta(days=i))
                for i, q in enumerate(day_queries)  # ensure day_queries is defined earlier
            ]
        else:
            # Normalize geocode result
            first = airport_coords[0]
            if isinstance(first, dict):
                origin_lat = first.get("lat")
                origin_lng = first.get("lng")
                origin_fmt = first.get("formatted_address")
            else:
                origin_lat, origin_lng, origin_fmt = first

            # --- Add airport with unique node key ---
            airport_node_d1 = f"{destination_code}"

            # Initialize dicts
            coords = {airport_node: (origin_lat, origin_lng)}
            formatted_names = {airport_node: f"{airport_node} ({origin_fmt})"}

            # Geocode each itinerary location
            for q in day_queries:
                loc = planner.geocode_location(q, limit=1)
                if loc:
                    first_loc = loc[0]
                    if isinstance(first_loc, dict):
                        lat = first_loc.get("lat")
                        lng = first_loc.get("lng")
                        formatted = first_loc.get("formatted_address")
                    else:
                        lat, lng, formatted = first_loc
                    coords[q] = (lat, lng)
                    formatted_names[q] = formatted

            # Build MST + itinerary order starting at airport
            all_nodes = [airport_node] + day_queries
            with st.spinner("Building optimized itinerary..."):
                mst = kruskal_mst(all_nodes, coords, haversine)
                itinerary_order = traverse_mst(mst, airport_node)

            # Build distances with travel dates
            location_distances = []
            base_date = datetime.strptime(date["check_in"], "%Y-%m-%d")
            for day in range(1, len(itinerary_order)):
                prev_place = itinerary_order[day - 1]
                curr_place = itinerary_order[day]
                dist = haversine(*coords[prev_place], *coords[curr_place])
                travel_date = base_date + timedelta(days=day - 1)
                curr_fmt = formatted_names.get(curr_place, curr_place)
                location_distances.append(
                    (curr_place, curr_fmt, *coords[curr_place], dist, travel_date)
                )


        # --- Custom Background (Japan themed via Imgur, h1 black only, widened content, white background for section containers) ---
        page_bg_img = """
        <style>
        /* 🎨 Enlarge all <p> elements inside the main content */
        section[data-testid="stMain"] div[data-testid="stMarkdownContainer"] p, h3, h4 {
            font-size: 35px !important;   /* adjust size */
            font-weight: 600 !important;  /* optional emphasis */

        }
                /* 🎨 Enlarge all <p> elements inside the main content */
        section[data-testid="stMain"] div[data-testid="stMarkdownContainer"] li {
            font-size: 35px !important;   /* adjust size */
        }
        /* 🎨 Apply white background to the second section */
        section[data-testid="stAppViewContainer"] > div:nth-child(2) {
            background-color: white !important;
            color: black !important;
            border-radius: 12px !important;
            padding: 1.5rem !important;
            box-shadow: 0 4px 12px rgba(0,0,0,0.1) !important;
        }

        /* ✅ Ensure all text inside is black */
        section[data-testid="stAppViewContainer"] > div:nth-child(2) h1,
        section[data-testid="stAppViewContainer"] > div:nth-child(2) h2,
        section[data-testid="stAppViewContainer"] > div:nth-child(2) h3,
        section[data-testid="stAppViewContainer"] > div:nth-child(2) p,
        section[data-testid="stAppViewContainer"] > div:nth-child(2) label {
            color: black !important;
        }

        
        /* 🎨 Tab list container background */
        div[data-baseweb="tab-list"][role="tablist"] {
            background-color: black !important;   /* make tab list background black */
            border-radius: 8px !important;
            padding: 8px !important;
        }

        /* ✅ Tab button text styling */
        button[data-baseweb="tab"] div[data-testid="stMarkdownContainer"] p {
            color: white !important;              /* keep text visible on black background */
            font-size: 24px !important;           /* larger font size */
            font-weight: 700 !important;          /* bold text */
            margin: 0 !important;                 /* remove extra spacing */
        }

        /* 🎨 Target the deep nested container */
        section[data-testid="stVerticalBlock"] > div:nth-child(2) 
            > div > div > div:nth-child(25) > div > div:nth-child(2) 
            > div > div:nth-child(3) > div > div > div:nth-child(9) > div > div:nth-child(3) {
            
            background-color: white !important;   /* set background to white */
            color: black !important;              /* force text to black */
            font-size: 30px !important;           /* adjust font size */
            font-weight: 600 !important;          /* bold text */
            border-radius: 8px !important;        /* rounded corners */
            padding: 1rem !important;             /* spacing inside */
            box-shadow: 0 4px 12px rgba(0,0,0,0.1) !important; /* subtle shadow */
        }


        /* ⭐ Style rating, price, address lines */
        div.stVerticalBlock[data-testid="stVerticalBlock"] p {
            font-size: 22px !important;           /* medium size for details */
            font-weight: 500 !important;
            color: #333 !important;               /* dark gray text */
            margin: 0.3rem 0 !important;
        }
        
        /* 🔗 Style the "Book Hotel" link button */
        div.stVerticalBlock[data-testid="stVerticalBlock"] a {
            font-size: 18px !important;
            font-weight: 600 !important;
            color: white !important;
            background-color: #0072ce !important; /* blue button */
            padding: 0.6rem 1rem !important;
            border-radius: 6px !important;
            text-decoration: none !important;
            display: inline-block !important;
        }
        div.stVerticalBlock[data-testid="stVerticalBlock"] a:hover {
            background-color: #005fa3 !important; /* darker blue on hover */
        }
        
        div[data-testid="stDeckGlJsonChart"] {
                    position: fixed !important;
                    right: 0;             /* distance from right edge */
                    top: 50px;               /* distance from top edge */
                    width: 700px !important;
                    height: 400px !important;
                    z-index: 9999;
                    border: 2px solid #000;
                    border-radius: 8px;
                    background-color: white;
                }
                
        p {
        padding: 10px;             /* adds spacing inside the box */
        border-radius: 4px;        /* optional: rounded corners */
        }
        li {
        font-size: 2rem;   /* larger font size */
        line-height: 1.6;    /* optional: improves readability */
        }
        /* Target the container at /html/body/div[1]/div[1]/div[1]/div/div/section[2]/div[1] */
        html body > div:nth-of-type(1) > div:nth-of-type(1) > div:nth-of-type(1) > div > div > section:nth-of-type(2) > div:nth-of-type(1) {
        background-color: white;            
        padding: 15px;        /* optional: add spacing */
        border-radius: 6px;   /* optional: rounded corners */
        }

        /* Parent container: sidebar + main content */
        section:nth-of-type(2) {
            display: flex;              /* Horizontal layout */
            flex-direction: row;
            height: auto;               /* Let content define height */
        }

        /* Sidebar */
        section:nth-of-type(2) > div:first-child {
            width: 2000px;               /* Fixed sidebar width */
            background-color: white;    /* White background */
            flex-shrink: 0;             /* Prevent shrinking */
            padding: 20px;              /* Optional spacing */
            position: sticky;           /* Sidebar stays visible when scrolling */
            top: 0;                     /* Stick to top of viewport */
            align-self: flex-start;     /* Align to top of parent */
        }

        /* Main content */
        section:nth-of-type(2) > div:nth-child(2) {
            flex: 1;                    /* Fill remaining space */
            padding: 20px;              /* Optional spacing */
            overflow-y: auto;           /* Allow vertical scrolling */
        }

                /* Optional: enlarge list items too */
                div[data-testid="stMarkdownContainer"] ul li {
                    font-size: 30px;
                    margin-bottom: 6px;
                }
                

        </style>
        """
        st.markdown(page_bg_img, unsafe_allow_html=True)


        # 🛠️ CREATE THE TABS BY DATE FOR THE CURRENT TRIP
        tab_labels = []
        for day_index in range(num_days):
            day_date = start_date + timedelta(days=day_index)
            tab_labels.append(f"📅 Day {day_index+1}: {day_date.strftime('%b %d')}")

        with st.container():
            st.markdown('<div id="day-tabs-marker"></div>', unsafe_allow_html=True)
            trip_tabs = st.tabs(tab_labels)

        itinerary_start = time.time()
        
        # Build itinerary days inside their respective date tabs
        for day_index, tab in enumerate(trip_tabs):
            day_date = start_date + timedelta(days=day_index)
            if day_index < len(location_distances):
                current_sight = location_distances[day_index][1]
            else:
                current_sight = d1
            
            display_columns = [
            "trip_label", "airline", "flight_number", "price", "route",
            "departure_time", "arrival_time", "total_duration"
        ]
                        
            # Scope all output rules to render inside the active tab
            with tab:
                st.subheader(f"📅 Itinerary for {day_date.strftime('%A, %b %d')}")
                st.write(f"**Exploring:** {current_sight}")

                # ✅ Always initialize lists so they exist
                outbound_filtered = []
                return_filtered = []

                # --- Outbound Flights (Day 1 only) ---
                if day_index == 0 and results.get("outbound_options"):
                    st.divider()
                    st.markdown("### 🛫 Outbound Flights")

                    try:
                        outbound_filtered = [
                            opt for opt in results["outbound_options"]
                            if opt.get("price") is not None and float(opt["price"]) <= float(budget)
                        ]
                    except Exception as e:
                        st.error(f"Budget filter failed: {e}")
                        outbound_filtered = results["outbound_options"]  # fallback: show all

                    if outbound_filtered:
                        df_out = pd.DataFrame(outbound_filtered)
                        df_out["trip_label"] = results.get("trip_type", "Outbound")

                        if "price" in df_out.columns:
                            df_out["price"] = pd.to_numeric(df_out["price"], errors="coerce")
                            df_out["price"] = df_out["price"].fillna(float("inf"))

                        st.dataframe(
                            df_out[display_columns],
                            column_config=column_settings,
                            hide_index=True,
                            use_container_width=True
                        )
                    else:
                        st.info("No outbound flights within your budget.")

                # --- Return Flights (last day only) ---
                if day_index == num_days - 1 and results.get("return_options"):
                    st.divider()
                    st.markdown("### 🛬 Return Flights")

                    st.write(f"Found {len(results['return_options'])} return options before filtering.")

                    try:
                        return_filtered = [
                            opt for opt in results["return_options"]
                            if opt.get("price") is not None and float(opt["price"]) <= float(budget)
                        ]
                    except Exception as e:
                        st.error(f"Budget filter failed: {e}")
                        return_filtered = results["return_options"]  # fallback: show all

                    if return_filtered:
                        df_ret = pd.DataFrame(return_filtered)

                        df_ret["trip_label"] = results.get("trip_type", "Return")
                        st.dataframe(
                            df_ret[display_columns],
                            column_config=column_settings,
                            hide_index=True,
                            use_container_width=True
                        )
                    else:
                        st.info("No return flights within your budget.")
                else:
                    st.write("No return flights to display for this day.")

                # --- AI Recommendation ---
                if enable_ai:   # only run if user enabled AI
                    if outbound_filtered or return_filtered:
                        all_flights = outbound_filtered + return_filtered
                        ai_data = search_flight_recommendation(
                            origin_code,
                            destination_code,
                            all_flights,
                            currency,
                            trip_type=results.get("trip_type", "Trip")
                        )

                        st.markdown("### 📝 AI Flight Recommendation")

                        ai_md = ai_data.get("reconstructed_markdown", "")
                        if ai_md and isinstance(ai_md, str) and ai_md.strip():
                            cutoff_marker = "### References"
                            extracted_text = ai_md.split(cutoff_marker)[0].strip() if cutoff_marker in ai_md else ai_md.strip()
                            st.markdown(extracted_text, unsafe_allow_html=True)
                        else:
                            st.info("No AI flight recommendation available.")
                    else:
                        st.info("No flights available to generate AI recommendation.")
                else:
                    st.info("AI Flight Recommendation disabled.")

                # --- Hotels & Activities ---
                coords = planner.geocode_location(current_sight, limit=1)
                if coords:
                    lat, lng, formatted_addr = coords[0]

                    # Define hotel queries (adjust as needed)
                    queries = [
                        f"hotels near {current_sight}",
                        f"hotels near {destination_city}"
                    ]

                    # Create sub-tabs under the current day tab
                    subtabs = st.tabs(["Hotels", "Activities", "Transportation"])
                    
                    # --- HOTELS TAB ---
                    with subtabs[0]:
                        if day_index == num_days - 1:
                            st.markdown("#### 🏨 Stay Nearby (Final Night)")
                            query = f"hotels near {d1}"
                            check_out = end_date.strftime("%Y-%m-%d")
                        else:
                            st.markdown("#### 🏨 Stay Nearby")
                            query = f"hotels near {current_sight}"
                            check_out = (day_date + timedelta(days=1)).strftime("%Y-%m-%d")

                        hotel_params = {
                            "engine": "google_hotels",
                            "q": query,
                            "check_in_date": day_date.strftime("%Y-%m-%d"),
                            "check_out_date": check_out,
                            "currency": currency,
                            "api_key": API_KEY,
                            "lat": lat,
                            "lng": lng,
                        }

                        with st.spinner(f"Searching hotels near {query}..."):
                            raw_response = GoogleSearch(hotel_params).get_dict()
                            hotels = raw_response.get("properties", [])

                        if not hotels:
                            st.warning(f"No hotels found for {query}.")
                        else:
                            # ✅ Apply budget filter
                            budget_filtered = [
                                h for h in hotels
                                if h.get("rate_per_night", {}).get("extracted_lowest") is not None
                                and float(h["rate_per_night"]["extracted_lowest"]) <= budget
                            ]

                            # ✅ Apply sorting
                            if global_sort_option == "Overall Rating (High → Low)":
                                sorted_hotels = sorted(budget_filtered, key=lambda h: float(h.get("overall_rating", 0)), reverse=True)
                            elif global_sort_option == "Overall Rating (Low → High)":
                                sorted_hotels = sorted(budget_filtered, key=lambda h: float(h.get("overall_rating", 0)))
                            elif global_sort_option == "Price (Low → High)":
                                sorted_hotels = sorted(budget_filtered, key=lambda h: float(h["rate_per_night"]["extracted_lowest"]))
                            elif global_sort_option == "Price (High → Low)":
                                sorted_hotels = sorted(budget_filtered, key=lambda h: float(h["rate_per_night"]["extracted_lowest"]), reverse=True)
                            else:
                                sorted_hotels = budget_filtered

                            # --- Hotel Results Section ---
                            st.subheader(f"🏨 Hotels near {query} (Sorted by {global_sort_option})")

                            map_points = []

                            if sorted_hotels:
                                for hotel in sorted_hotels[:5]:
                                    st.markdown("---")
                                    col_img, col_info = st.columns([1, 2])

                                    with col_img:
                                        hotel_images = hotel.get("images", [])
                                        if hotel_images and isinstance(hotel_images, list):
                                            img_url = hotel_images[0].get("original_image") or hotel_images[0].get("thumbnail")
                                            if img_url:
                                                st.image(img_url, use_container_width=True)

                                    with col_info:
                                        hotel_name = hotel.get("name", "Unknown")
                                        st.write(f"**{hotel_name}**")
                                        st.write(f"⭐ {hotel.get('overall_rating', 'N/A')} "
                                                f"({hotel.get('reviews', 'N/A')} reviews)")
                                        st.write(f"💰 {hotel.get('rate_per_night', {}).get('lowest', 'N/A')} {currency}")
                                        st.write(f"📍 {hotel.get('address', '')}")
                                        if hotel.get("link"):
                                            st.link_button("Book Hotel", hotel["link"])

                                    if hotel.get("gps_coordinates"):
                                        lat = hotel["gps_coordinates"].get("latitude")
                                        lon = hotel["gps_coordinates"].get("longitude")
                                        if lat and lon:
                                            map_points.append({"lat": lat, "lon": lon, "name": hotel_name})

                                # ✅ AI enrichment step with retry
                                if sorted_hotels:   # first check if hotels exist
                                    if enable_ai:   # only run if user enabled AI
                                        try:
                                            ai_data = search_hotels_overall_recommendation(sorted_hotels[:5])
                                            ai_md = ai_data.get("reconstructed_markdown", "")
                                        except Exception as e:
                                            st.error(f"AI call failed: {e}")
                                            ai_md = ""

                                        if ai_md:
                                            cutoff_marker = "### References"
                                            extracted_text = ai_md.split(cutoff_marker)[0].strip() if cutoff_marker in ai_md else ai_md.strip()
                                            st.markdown("### 📝 AI Overall Hotel Recommendation")
                                            st.write(extracted_text)
                                        else:
                                            st.info("No AI overall recommendation available.")
                                    else:
                                        st.info("AI Overall Hotel Recommendation disabled.")
                                else:
                                    st.warning("No hotels found to display.")

                            # ✅ Map visualization for this section
                            if show_map and map_points:   # only run if user enabled map
                                df = pd.DataFrame(map_points)
                                st.pydeck_chart(
                                    pdk.Deck(
                                        map_style="mapbox://styles/mapbox/streets-v11",
                                        initial_view_state=pdk.ViewState(
                                            latitude=df["lat"].mean(),
                                            longitude=df["lon"].mean(),
                                            zoom=12,
                                            pitch=0,
                                        ),
                                        layers=[
                                            pdk.Layer(
                                                "ScatterplotLayer",
                                                data=df,
                                                get_position='[lon, lat]',
                                                get_color='[0, 100, 200, 160]',
                                                get_radius=100,
                                            ),
                                            pdk.Layer(
                                                "TextLayer",
                                                data=df,
                                                get_position='[lon, lat]',
                                                get_text="name",
                                                get_size=14,
                                                get_color=[0, 0, 0],
                                            )
                                        ],
                                    )
                                )
                            elif show_map:
                                st.info("No points available to display on the map.")
                            else:
                                st.info("Map display disabled.")
                                
                    
                    # --- ACTIVITIES TAB ---
                    with subtabs[1]:
                        st.markdown("#### 🏛️ Activities")

                        map_points = []              # collect activity coordinates
                        collected_activities = []    # collect activities for AI recommendation
                        
                        # ✅ Take only the first part before the comma
                        first_part = current_sight.split(",")[0].strip()

                        for kw in keywords:
                            st.markdown(f"**🔎 {kw.title()}**")
                            
                            activity_params = {
                                "engine": "google_maps",
                                "q": f"{kw} near {first_part}",   # ✅ use only the first part
                                "ll": f"@{lat},{lng},14z",        # keep zoom if you prefer
                                "api_key": API_KEY
                            }

                            # Spinner around the API call
                            with st.spinner(f"Searching {kw} near {current_sight}..."):
                                try:
                                    act_search = GoogleSearch(activity_params)
                                    act_response = act_search.get_dict()
                                    act_data = act_response.get("local_results", [])
                                except Exception as e:
                                    st.error(f"Error calling Maps API: {e}")
                                    act_data = []

                            if act_data:
                                # Limit to top 2 activities
                                for top_act in act_data[:2]:
                                    collected_activities.append(top_act)  # save for recommendation
                                    with st.container(border=True):
                                        col_img, col_info = st.columns([1, 2])

                                        with col_img:
                                            if top_act.get("thumbnail"):
                                                st.image(top_act["thumbnail"], use_container_width=True)

                                        with col_info:
                                            st.subheader(top_act.get("title", "Unnamed"))
                                            st.write(f"⭐ {top_act.get('rating', 'N/A')} | {top_act.get('type', 'N/A')}")
                                            if top_act.get("address"):
                                                st.write(f"📍 {top_act['address']}")
                                            if top_act.get("hours"):
                                                st.write(f"⏰ {top_act['hours']}")
                                            if top_act.get("description") or top_act.get("snippet"):
                                                st.markdown(f"_{top_act.get('description') or top_act.get('snippet')}_")
                                            if top_act.get("user_review"):
                                                st.markdown(f"> 💬 *\"{top_act['user_review']}\"*")
                                            if top_act.get("website"):
                                                st.link_button("🌐 View Website", top_act["website"], use_container_width=True)

                                    # ✅ Collect coordinates for map
                                    if top_act.get("gps_coordinates"):
                                        lat_act = top_act["gps_coordinates"].get("latitude")
                                        lon_act = top_act["gps_coordinates"].get("longitude")
                                        if lat_act and lon_act:
                                            map_points.append({
                                                "lat": lat_act,
                                                "lon": lon_act,
                                                "name": top_act.get("title", "Activity")
                                            })
                            else:
                                st.write(f"No {kw} found near {current_sight}.")

                        # ✅ AI enrichment step: separate weather + activities
                        if collected_activities:    
                            # Calculate the actual date for this itinerary day
                            trip_date = check_in + timedelta(days=day-1)
                            trip_date_str = trip_date.strftime("%d-%m-%Y")

                            # ✅ Define place for weather/activity calls
                            place = first_part if first_part else current_sight

                            # Weather AI call (include actual date)
                            if enable_ai:   # only run if user enabled AI
                                weather_data = search_weather(place, trip_date)
                                st.markdown("### 🌤️ Weather Summary")
                                weather_md = weather_data.get("reconstructed_markdown", "")
                                if weather_md:
                                    st.markdown(weather_md.strip(), unsafe_allow_html=True)
                                else:
                                    st.info("No AI weather summary available.")
                            else:
                                weather_md = ""  # skip AI call if disabled
                                                    
                            # Activity AI call (pass weather context)
                            if enable_ai:   # only run if user enabled AI
                                ai_data = search_activity_recommendation(
                                    place,
                                    collected_activities,
                                    weather_summary=weather_md.strip() if weather_md else None
                                )

                                # ✅ Retrieve reconstructed_markdown and strip references
                                st.markdown("### 📝 AI Activity Recommendation")
                                ai_md = ai_data.get("reconstructed_markdown", "")
                                if ai_md:
                                    cutoff_marker = "### References"
                                    if cutoff_marker in ai_md:
                                        extracted_text = ai_md.split(cutoff_marker)[0].strip()
                                    else:
                                        extracted_text = ai_md.strip()

                                    # Show the markdown exactly as returned, minus references
                                    st.markdown(extracted_text, unsafe_allow_html=True)
                                else:
                                    st.info("No AI activity recommendation available.")


                        # ✅ Show map if points exist
                        if show_map and map_points:   # only run if user enabled map
                            df = pd.DataFrame(map_points)
                            st.pydeck_chart(pdk.Deck(
                                map_style="mapbox://styles/mapbox/streets-v11",
                                initial_view_state=pdk.ViewState(
                                    latitude=df["lat"].mean(),
                                    longitude=df["lon"].mean(),
                                    zoom=12,
                                    pitch=0,
                                ),
                                layers=[
                                    pdk.Layer(
                                        "ScatterplotLayer",
                                        data=df,
                                        get_position='[lon, lat]',
                                        get_color='[200, 30, 0, 160]',
                                        get_radius=100,
                                    ),
                                    pdk.Layer(
                                        "TextLayer",
                                        data=df,
                                        get_position='[lon, lat]',
                                        get_text="name",
                                        get_size=14,
                                        get_color=[0, 0, 0],
                                    )
                                ],
                            ))
                        elif show_map:
                            st.info("No activities found to display on the map.")
                        else:
                            st.info("Map display disabled.")


                    # --- TRANSPORTATION TAB ---
                    with subtabs[2]:
                        st.subheader("🚍 Transportation Advice")

                        # Determine current place
                        if day_index == 0:
                            # ✅ Day 0 起點改成機場節點
                            current_place = airport_node
                        else:
                            if day_index - 1 < len(location_distances):
                                current_place = location_distances[day_index - 1][1]
                            else:
                                current_place = airport_node  # fallback 改成機場

                        # Geocode current sight
                        coords = planner.geocode_location(current_sight, limit=1)
                        if coords:
                            lat, lng, formatted = coords[0]

                            # Geocode current place (可能是機場或前一天的地點)
                            prev_coords = planner.geocode_location(current_place, limit=1)
                            if prev_coords:
                                prev_lat, prev_lng, prev_formatted = prev_coords[0]
                                dist = haversine(prev_lat, prev_lng, lat, lng)

                                st.markdown(
                                    f"### Day {day_index+1}: Travel from {prev_formatted} → {formatted} "
                                    f"({dist:.1f} km) at {day_date.strftime('%Y-%m-%d')}"
                                )

                                # Spinner around directions API call
                                with st.spinner(f"Fetching transit directions from {prev_formatted} to {formatted}..."):
                                    try:
                                        raw_data = get_directions_raw(prev_formatted, formatted, mode="transit")
                                        directions = raw_data.get("directions", [])
                                        transit_options = [d for d in directions if d.get("travel_mode") == "Transit"]
                                    except Exception as e:
                                        st.error(f"Error fetching directions: {e}")
                                        transit_options = []

                                # --- Case 1: Both Flight + Transit ---
                                if "Flight" in transport_modes and "Transit" in transport_modes:  
                                    # Use current itinerary date for flight search
                                    flight_data = search_flights_google_ai(prev_formatted, formatted, day_date)

                                    reconstructed_md = flight_data.get("reconstructed_markdown", "")
                                    if reconstructed_md:
                                        cleaned_md = reconstructed_md.split("### References")[0].strip()
                                        st.markdown("### 📝 AI Flight Summary")
                                        st.markdown(cleaned_md, unsafe_allow_html=True)
                                    else:
                                        st.warning("No reconstructed_markdown found in response.")

                                    # Transit options
                                    for option_no, d in enumerate(transit_options, start=1):
                                        st.markdown(
                                            f"#### 🚇 Transit Option {option_no} "
                                            f"(Itinerary Date: {day_date.strftime('%Y-%m-%d')}, API Date: {d.get('date','N/A')})"
                                        )
                                        st.write(f"🕓 Departure: {d.get('start_time','N/A')} → Arrival: {d.get('end_time','N/A')}")
                                        st.write(f"📏 Total Distance: {d.get('formatted_distance','N/A')}")
                                        st.write(f"⌛ Estimated Duration: {d.get('formatted_duration','N/A')}")
                                        if d.get("icon"):
                                            st.image(d["icon"], width=40)

                                        for trip in d.get("trips", []):
                                            st.markdown(f"**{trip.get('title','Unnamed')}** ({trip.get('formatted_duration','N/A')})")
                                            if trip.get("start_stop") and trip.get("end_stop"):
                                                st.write(
                                                    f"From {trip['start_stop'].get('name','Unknown')} at {trip['start_stop'].get('time','N/A')} → "
                                                    f"{trip['end_stop'].get('name','Unknown')} at {trip['end_stop'].get('time','N/A')}"
                                                )
                                            for stop in trip.get("stops", []):
                                                st.write(f"- Stop: {stop.get('name','Unknown')} ({stop.get('time','N/A')})")
                                            if trip.get("service_run_by"):
                                                st.write(f"Operated by: {trip['service_run_by'].get('name','Unknown')}")
                                                if trip['service_run_by'].get("link"):
                                                    st.write(f"Website: {trip['service_run_by']['link']}")
                                            if trip.get("icon"):
                                                st.image(trip["icon"], width=40)
                                            if trip.get("travel_mode") == "Walking":
                                                st.write("🚶 Walking Segment:")
                                                for step in trip.get("details", []):
                                                    st.write(f"- {step.get('title','Step')} ({step.get('formatted_duration','N/A')})")
                                                    if step.get("geo_photo"):
                                                        st.image(step["geo_photo"], width=200)

                                    # --- AI Best Direction Recommendation ---
                                    if enable_ai:   # only run if user enabled AI
                                        ai_answer = ai_select_best_direction(
                                            transit_options,
                                            flight_data,
                                            day_date,
                                            prev_formatted,
                                            formatted
                                        )
                                        st.markdown("### 🧠 AI Best Direction Recommendation")
                                        st.write(ai_answer)
                                    else:
                                        st.info("AI Best Direction Recommendation disabled.")

                                # --- Case 2: Transit only ---
                                elif "Transit" in transport_modes:  
                                    for option_no, d in enumerate(transit_options, start=1):
                                        st.markdown(
                                            f"#### 🚇 Transit Option {option_no} "
                                            f"(Itinerary Date: {travel_date.strftime('%Y-%m-%d')}, API Date: {d.get('date','N/A')})"
                                        )
                                        st.write(f"🕓 Departure: {d.get('start_time','N/A')} → Arrival: {d.get('end_time','N/A')}")
                                        st.write(f"📏 Total Distance: {d.get('formatted_distance','N/A')}")
                                        st.write(f"⌛ Estimated Duration: {d.get('formatted_duration','N/A')}")
                                        if d.get("icon"):
                                            st.image(d["icon"], width=40)

                                        for trip in d.get("trips", []):
                                            st.markdown(f"**{trip.get('title','Unnamed')}** ({trip.get('formatted_duration','N/A')})")
                                            if trip.get("start_stop") and trip.get("end_stop"):
                                                st.write(
                                                    f"From {trip['start_stop'].get('name','Unknown')} at {trip['start_stop'].get('time','N/A')} → "
                                                    f"{trip['end_stop'].get('name','Unknown')} at {trip['end_stop'].get('time','N/A')}"
                                                )
                                            for stop in trip.get("stops", []):
                                                st.write(f"- Stop: {stop.get('name','Unknown')} ({stop.get('time','N/A')})")
                                            if trip.get("service_run_by"):
                                                st.write(f"Operated by: {trip['service_run_by'].get('name','Unknown')}")
                                                if trip['service_run_by'].get("link"):
                                                    st.write(f"Website: {trip['service_run_by']['link']}")
                                            if trip.get("icon"):
                                                st.image(trip["icon"], width=40)
                                            if trip.get("travel_mode") == "Walking":
                                                st.write("🚶 Walking Segment:")
                                                for step in trip.get("details", []):
                                                    st.write(f"- {step.get('title','Step')} ({step.get('formatted_duration','N/A')})")
                                                    if step.get("geo_photo"):
                                                        st.image(step["geo_photo"], width=200)

                                    # --- AI Transit Recommendation ---
                                    if enable_ai:   # only run if user enabled AI
                                        # Call the function
                                        ai_answer = ai_select_best_direction(
                                            transit_options,
                                            None,  # no flight data
                                            travel_date,
                                            prev_formatted,
                                            formatted
                                        )

                                        # Show the formatted AI answer
                                        st.markdown("### 🧠 AI Transit Recommendation")
                                        st.write(ai_answer)

                                    else:
                                        st.info("AI Transit Recommendation disabled.")


                                # --- Case 3: Flight only ---
                                else:
                                    # Call your flight search function
                                    flight_data = search_flights_google_ai(prev_formatted, curr_formatted, travel_date)

                                    # Show raw API response for debugging
                                    st.markdown("**Raw Flight API Response:**")

                                    # --- Show AI narrative (structured Markdown without References) ---
                                    reconstructed_md = flight_data.get("reconstructed_markdown", "")
                                    if reconstructed_md:
                                        # Remove trailing "### References" section if present
                                        cleaned_md = reconstructed_md.split("### References")[0].strip()
                                        st.markdown("### 📝 AI Flight Summary")
                                        st.markdown(cleaned_md, unsafe_allow_html=True)
                                    else:
                                        st.warning("No reconstructed_markdown found in response.")

                                    # --- AI Flight Recommendation ---
                                    if enable_ai:   # only run if user enabled AI
                                        ai_answer = ai_select_best_direction(
                                            None,
                                            flight_data,
                                            travel_date,
                                            prev_formatted,
                                            formatted
                                        )
                                        st.markdown("### 🧠 AI Flight Recommendation")
                                        st.write(ai_answer)
                                    else:
                                        st.info("AI Flight Recommendation disabled.")


                                # ✅ Map visualization for this leg
                                map_points = [
                                    {"lat": prev_lat, "lon": prev_lng, "name": prev_formatted},
                                    {"lat": lat, "lon": lng, "name": formatted}
                                ]

                                if show_map and map_points:
                                    df = pd.DataFrame(map_points)
                                    st.pydeck_chart(
                                        pdk.Deck(
                                            map_style="mapbox://styles/mapbox/streets-v11",
                                            initial_view_state=pdk.ViewState(
                                                latitude=df["lat"].mean(),
                                                longitude=df["lon"].mean(),
                                                zoom=10,
                                                pitch=0,
                                            ),
                                            layers=[
                                                pdk.Layer("ScatterplotLayer", data=df,
                                                        get_position='[lon, lat]',
                                                        get_color='[200, 30, 0, 160]',
                                                        get_radius=120),
                                                pdk.Layer("TextLayer", data=df,
                                                        get_position='[lon, lat]',
                                                        get_text="name",
                                                        get_size=14,
                                                        get_color=[0, 0, 0]),
                                                pdk.Layer("LineLayer",
                                                        data=pd.DataFrame([{
                                                            "lon_start": prev_lng, "lat_start": prev_lat,
                                                            "lon_end": lng, "lat_end": lat
                                                        }]),
                                                        get_source_position='[lon_start, lat_start]',
                                                        get_target_position='[lon_end, lat_end]',
                                                        get_color=[0, 128, 255],
                                                        get_width=4)
                                            ],
                                        )
                                    )
                                elif show_map:
                                    st.info("No route coordinates available to display on the map.")

        # ✅ End timer after itinerary loop finishes
        itinerary_elapsed = time.time() - itinerary_start
        st.success(f"⏱ Itinerary built in {itinerary_elapsed:.2f} seconds")
        
        
        
        
        