from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

FORCE_NEW_SEARCH_PHRASES = {
    "search again",
    "another search",
    "more options",
    "different options",
    "show me more",
    "new search",
    "something else",
    "find more",
}

REQUIRED_FIELDS = ("cuisine", "location", "budget", "travel_mode", "travel_minutes")


@dataclass
class ConversationSession:
    """Stores per-call state including slots and prior searches."""

    call_sid: str
    caller_number: Optional[str] = None
    slots: Dict[str, Optional[str]] = field(
        default_factory=lambda: {
            "cuisine": None,
            "location": None,
            "budget": None,
            "travel_mode": None,
            "travel_minutes": None,
            "open_now": None,
            "open_until": None,
        }
    )
    history: List[Tuple[str, str]] = field(default_factory=list)
    last_search_signature: Tuple[Tuple[str, str], ...] | None = None
    last_prompt_text: Optional[str] = None
    rcs_sent: bool = False

    def append(self, role: str, content: str) -> None:
        self.history.append((role, content))

    def update_slots(self, updates: Dict[str, Optional[str]]) -> None:
        for key, value in updates.items():
            if value is not None and value != "":
                self.slots[key] = value

    @property
    def missing_slots(self) -> List[str]:
        missing = [key for key in REQUIRED_FIELDS if not self.slots.get(key)]
        return missing

    @property
    def ready_for_search(self) -> bool:
        return not self.missing_slots

    def signature(self) -> Tuple[Tuple[str, str], ...]:
        sig: List[Tuple[str, str]] = []
        for key in REQUIRED_FIELDS + ("open_now", "open_until"):
            value = self.slots.get(key)
            if value:
                sig.append((key, str(value).strip().lower()))
        return tuple(sig)

    def should_skip_search(self, normalized_prompt: str) -> bool:
        signature = self.signature()
        if not signature:
            return False
        if normalized_prompt and any(
            phrase in normalized_prompt for phrase in FORCE_NEW_SEARCH_PHRASES
        ):
            return False
        return signature == (self.last_search_signature or ())

    def mark_search(self, normalized_prompt: str) -> None:
        self.last_search_signature = self.signature()
        self.last_prompt_text = normalized_prompt


class SessionStore:
    """Simple in-memory session tracker."""

    def __init__(self):
        self._sessions: Dict[str, ConversationSession] = {}

    def get(self, call_sid: str) -> ConversationSession:
        if call_sid not in self._sessions:
            self._sessions[call_sid] = ConversationSession(call_sid=call_sid)
        return self._sessions[call_sid]

    def clear(self, call_sid: str) -> None:
        self._sessions.pop(call_sid, None)

    def clear_all(self) -> None:
        self._sessions.clear()

    def with_callers(self) -> Iterable[ConversationSession]:
        return self._sessions.values()
