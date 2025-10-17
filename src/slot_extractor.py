from __future__ import annotations

import json
from typing import Dict, Optional

from .clients import openai_client

FOLLOW_UP_PROMPTS = {
    "cuisine": "What kind of food are you craving?",
    "location": "Where should I search for restaurants?",
    "budget": "Do you have a budget in mind?",
    "travel_mode": "Would you prefer to walk or take transit?",
    "travel_minutes": "How many minutes are you comfortable traveling?",
}


# -- TODO 3: Extracting Slots using LLM -------------------------------
FIELD_SPECS = [
]

SYSTEM_INSTRUCTION = """
"""

def extract_slots(
    utterance: str, previous: Dict[str, Optional[str]] | None = None
) -> Dict[str, Optional[str]]:
    """
    Use OpenAI to extract slot values from the latest utterance, taking prior
    slot values into account.
    """

    prior_context = json.dumps(previous or {}, indent=2)

    completion = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_INSTRUCTION},
            {
                "role": "user",
                "content": (
                    f"Caller said: {utterance}\n"
                    f"Previous slot values (for reference only):\n{prior_context}\n"
                    "Return the updated JSON now."
                ),
            },
        ],
    )

    raw_payload = completion.choices[0].message.content
    parsed = json.loads(raw_payload)
    return _normalise_slots(parsed)


def _normalise_slots(payload: Dict[str, object]) -> Dict[str, Optional[str]]:
    normalised: Dict[str, Optional[str]] = {}
    for field in FIELD_NAMES:
        value = payload.get(field)
        normalised[field] = _normalise_value(value)
    return normalised


def _normalise_value(value: object) -> Optional[str]:
    if value in (None, "", "null"):
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(int(value)) if isinstance(value, float) else str(value)
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return json.dumps(value)


def follow_up_for_missing(missing: list[str]) -> str:
    if not missing:
        return "Thanks! I have everything I need. Let me find a few options for you now."
    next_slot = missing[0]
    return FOLLOW_UP_PROMPTS.get(
        next_slot, "Could you tell me a bit more so I can narrow it down?"
    )
