from __future__ import annotations

import time
import uuid
from typing import Dict, List, Optional, Tuple

import requests

from .settings import settings

GOOGLE_PLACES_BASE = "https://places.googleapis.com/v1"
GOOGLE_GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
GOOGLE_DISTANCE_MATRIX_URL = "https://maps.googleapis.com/maps/api/distancematrix/json"

FIELD_MASK = ",".join(
    [
        "places.displayName",
        "places.formattedAddress",
        "places.rating",
        "places.userRatingCount",
        "places.priceLevel",
        "places.currentOpeningHours",
        "places.location",
    ]
)


def geocode_location(location: str) -> Tuple[Optional[float], Optional[float]]:
    params = {"address": location, "key": settings.google_places_api_key}
    response = requests.get(GOOGLE_GEOCODE_URL, params=params, timeout=10)
    response.raise_for_status()
    results = response.json().get("results", [])
    if not results:
        return None, None
    geometry = results[0]["geometry"]["location"]
    return geometry.get("lat"), geometry.get("lng")


def build_location_bias(lat: float, lng: float, travel_mode: str, minutes: int) -> Dict:
    if travel_mode == "walking":
        radius = min(minutes * 80, 5000)  # approx 80 meters per minute
    else:
        radius = min(minutes * 400, 10000)  # transit covers more distance
    return {
        "circle": {
            "center": {"latitude": lat, "longitude": lng},
            "radius": radius,
        }
    }


def to_price_levels(budget: str | None) -> Optional[List[str]]:
    if not budget:
        return None
    mapping = {
        "$": ["PRICE_LEVEL_INEXPENSIVE"],
        "$$": ["PRICE_LEVEL_MODERATE"],
        "$$$": ["PRICE_LEVEL_EXPENSIVE"],
        "$$$$": ["PRICE_LEVEL_VERY_EXPENSIVE"],
    }
    return mapping.get(budget)


def search_restaurants(slots: Dict[str, Optional[str]]) -> Dict[str, object]:
    cuisine = slots.get("cuisine") or "restaurant"
    location_text = slots.get("location") or ""
    budget = slots.get("budget")
    travel_mode = slots.get("travel_mode") or "walking"
    try:
        travel_minutes = int(slots.get("travel_minutes") or 15)
    except (TypeError, ValueError):
        travel_minutes = 15

    lat, lng = geocode_location(location_text)
    location_bias = None
    if lat and lng:
        location_bias = build_location_bias(lat, lng, travel_mode, travel_minutes)

    body: Dict[str, object] = {
        "textQuery": f"{cuisine} restaurants in {location_text}".strip(),
        "includedType": "restaurant",
        "maxResultCount": 15,
        "strictTypeFiltering": True,
        "rankPreference": "DISTANCE",
    }

    price_levels = to_price_levels(budget)
    if price_levels:
        body["priceLevels"] = price_levels
    if location_bias:
        body["locationBias"] = location_bias
    if slots.get("open_now") == "true":
        body["openNow"] = True

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": settings.google_places_api_key,
        "X-Goog-FieldMask": FIELD_MASK,
    }

    response = requests.post(
        f"{GOOGLE_PLACES_BASE}/places:searchText", json=body, headers=headers, timeout=15
    )
    try:
        response.raise_for_status()
    except requests.HTTPError:
        return {
            "success": False,
            "results": [],
            "message": "I couldn't retrieve restaurant data right now. Want to try again?",
        }

    places = response.json().get("places", [])
    if not places:
        return {
            "success": False,
            "results": [],
            "message": f"No {cuisine} spots found near {location_text}. Try adjusting your request.",
        }

    scored = rank_places(places, travel_mode, travel_minutes, lat, lng)
    recommendations = format_voice_summary(scored[:3], slots)
    search_id = str(uuid.uuid4())

    return {
        "success": True,
        "search_id": search_id,
        "results": scored,
        "voice_response": recommendations,
    }


def rank_places(
    places: List[Dict], travel_mode: str, travel_minutes: int, lat: Optional[float], lng: Optional[float]
) -> List[Dict]:
    ranked: List[Dict] = []
    for place in places:
        rating = place.get("rating") or 0
        reviews = place.get("userRatingCount") or 0
        score = rating * 2
        if reviews > 100:
            score += 0.5
        elif reviews < 10:
            score -= 0.5
        place_copy = {
            "name": place.get("displayName", {}).get("text", "Unknown"),
            "address": place.get("formattedAddress", "Address unavailable"),
            "rating": rating,
            "user_rating_count": reviews,
            "price_level": place.get("priceLevel"),
            "score": score,
        }
        if lat and lng and place.get("location"):
            duration = compute_travel_duration(
                lat,
                lng,
                place["location"].get("latitude"),
                place["location"].get("longitude"),
                travel_mode,
            )
            if duration:
                place_copy["travel"] = duration
        ranked.append(place_copy)

    ranked.sort(key=lambda item: item["score"], reverse=True)
    return ranked


def compute_travel_duration(
    user_lat: float,
    user_lng: float,
    dest_lat: Optional[float],
    dest_lng: Optional[float],
    mode: str,
) -> Optional[Dict[str, str]]:
    if dest_lat is None or dest_lng is None:
        return None
    params = {
        "origins": f"{user_lat},{user_lng}",
        "destinations": f"{dest_lat},{dest_lng}",
        "mode": mode,
        "key": settings.google_places_api_key,
        "departure_time": str(int(time.time())),
    }
    response = requests.get(GOOGLE_DISTANCE_MATRIX_URL, params=params, timeout=10)
    try:
        response.raise_for_status()
    except requests.HTTPError:
        return None
    data = response.json()
    try:
        element = data["rows"][0]["elements"][0]
        if element["status"] != "OK":
            return None
        return {
            "distance_text": element["distance"]["text"],
            "duration_text": element["duration"]["text"],
        }
    except (KeyError, IndexError):
        return None


def format_voice_summary(top_places: List[Dict], slots: Dict[str, Optional[str]]) -> str:
    if not top_places:
        return "I couldn't find matching restaurants. Want to try a different search?"

    intro = ""
    if len(top_places) == 1:
        intro = "I found one spot you might like. "
    elif len(top_places) == 2:
        intro = "Here are two places that fit what you asked for. "
    else:
        intro = "Here are the top three I found. "

    lines: List[str] = []
    for idx, place in enumerate(top_places, start=1):
        parts = [f"Number {idx}, {place['name']}"]
        if place.get("rating"):
            parts.append(f"rated {place['rating']} stars")
        if place.get("travel") and place["travel"].get("duration_text"):
            parts.append(f"about {place['travel']['duration_text']} away")
        lines.append(", ".join(parts) + ".")

    prompt = (
        "Want more details on any of these, or should I send the list to your phone?"
    )
    return intro + " ".join(lines) + " " + prompt
