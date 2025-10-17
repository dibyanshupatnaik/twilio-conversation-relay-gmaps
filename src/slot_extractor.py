from __future__ import annotations

import re
from typing import Dict, Optional, Tuple

CUISINE_KEYWORDS = {
    "thai",
    "indian",
    "mexican",
    "japanese",
    "chinese",
    "korean",
    "mediterranean",
    "greek",
    "italian",
    "vegan",
    "vegetarian",
    "bbq",
    "barbecue",
    "steakhouse",
    "seafood",
    "sushi",
    "ramen",
    "burger",
    "pizza",
    "tacos",
    "biryani",
    "pho",
    "dim sum",
}

BUDGET_KEYWORDS = {
    "cheap": "$",
    "inexpensive": "$",
    "affordable": "$",
    "budget": "$",
    "mid": "$$",
    "mid-range": "$$",
    "moderate": "$$",
    "average": "$$",
    "nice": "$$$",
    "fancy": "$$$",
    "expensive": "$$$",
    "splurge": "$$$$",
    "very expensive": "$$$$",
    "luxury": "$$$$",
}

TRAVEL_MODE_KEYWORDS = {
    "walk": "walking",
    "walking": "walking",
    "on foot": "walking",
    "transit": "transit",
    "train": "transit",
    "bus": "transit",
    "subway": "transit",
    "metro": "transit",
    "public transport": "transit",
}

FOLLOW_UP_PROMPTS = {
    "cuisine": "What kind of food are you craving?",
    "location": "Where should I search for restaurants?",
    "budget": "Do you have a budget in mind?",
    "travel_mode": "Would you prefer to walk or take transit?",
    "travel_minutes": "How many minutes are you willing to travel?",
}


def extract_slots(
    utterance: str, current: Dict[str, Optional[str]] | None = None
) -> Dict[str, Optional[str]]:
    """Extract basic slot values from a natural language utterance."""
    slots = dict(current or {})
    text = utterance.lower()

    cuisine = _extract_cuisine(text)
    if cuisine:
        slots["cuisine"] = cuisine

    location = _extract_location(text)
    if location:
        slots["location"] = location

    budget = _extract_budget(text)
    if budget:
        slots["budget"] = budget

    travel_mode, minutes = _extract_travel(text)
    if travel_mode:
        slots["travel_mode"] = travel_mode
    if minutes:
        slots["travel_minutes"] = minutes

    if "open now" in text:
        slots["open_now"] = "true"

    open_until = _extract_open_until(text)
    if open_until:
        slots["open_until"] = open_until

    return slots


def follow_up_for_missing(missing: list[str]) -> str:
    if not missing:
        return (
            "Thanks! I have everything I need. Let me find a few options for you now."
        )
    next_slot = missing[0]
    prompt = FOLLOW_UP_PROMPTS.get(
        next_slot, "Could you tell me a little more so I can narrow it down?"
    )
    if next_slot == "travel_minutes":
        return "How many minutes are you comfortable traveling?"
    return prompt


def _extract_cuisine(text: str) -> Optional[str]:
    for keyword in sorted(CUISINE_KEYWORDS, key=len, reverse=True):
        if re.search(rf"\b{re.escape(keyword)}\b", text):
            return keyword
    if "food" in text:
        match = re.search(r"(?:want|like|craving|need|for)\s+([a-z\s]+?)\s+food", text)
        if match:
            return match.group(1).strip()
    return None


def _extract_location(text: str) -> Optional[str]:
    patterns = [
        r"(?:near|around|by|close to)\s+(?P<loc>[a-z0-9\s',.-]+)",
        r"(?:in|at)\s+(?P<loc>[a-z0-9\s',.-]+)",
        r"(?P<loc>downtown|midtown|uptown|manhattan|brooklyn|queens|soho|chelsea)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            location = match.group("loc").strip(" .,!?:")
            if location:
                return location
    return None


def _extract_budget(text: str) -> Optional[str]:
    symbols = re.search(r"\$+\s*\$*", text)
    if symbols:
        return symbols.group().replace(" ", "")
    amount = re.search(r"(?:under|below|around)\s+\$?(\d{2,3})", text)
    if amount:
        dollars = int(amount.group(1))
        if dollars < 20:
            return "$"
        if dollars < 40:
            return "$$"
        if dollars < 70:
            return "$$$"
        return "$$$$"
    for keyword, value in BUDGET_KEYWORDS.items():
        if keyword in text:
            return value
    return None


def _extract_travel(text: str) -> Tuple[Optional[str], Optional[str]]:
    minutes_match = re.search(r"(\d{1,2})\s*(?:minute|min)", text)
    minutes = minutes_match.group(1) if minutes_match else None

    mode = None
    for keyword, value in TRAVEL_MODE_KEYWORDS.items():
        if keyword in text:
            mode = value
            break

    return mode, minutes


def _extract_open_until(text: str) -> Optional[str]:
    match = re.search(r"(?:open until|until)\s+(\d{1,2}\s*(?:am|pm))", text)
    if match:
        return match.group(1).replace(" ", "")
    return None
