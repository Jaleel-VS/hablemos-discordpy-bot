"""Practice session state management."""
import time
from dataclasses import dataclass, field
from enum import Enum


class PracticeMode(Enum):
    TYPING = "typing"
    CHOICE = "choice"


@dataclass
class PracticeCard:
    """A single practice card."""

    id: int
    word: str
    translation: str
    language: str
    sentence: str
    sentence_with_blank: str
    card_json: str | None = None  # Serialized FSRS Card state
    sentence_translation: str = ""
    level: str = ""


@dataclass
class PracticeSession:
    """State for an active practice session."""

    user_id: int
    language: str
    mode: PracticeMode
    tracked: bool = True
    cards: list[PracticeCard] = field(default_factory=list)
    current_index: int = 0
    correct_count: int = 0
    total_reviewed: int = 0
    created_at: float = field(default_factory=time.time)

    @property
    def current_card(self) -> PracticeCard | None:
        """Get the current card or None if session is complete."""
        if self.current_index < len(self.cards):
            return self.cards[self.current_index]
        return None

    @property
    def is_complete(self) -> bool:
        """Check if all cards have been reviewed."""
        return self.current_index >= len(self.cards)

    @property
    def progress_text(self) -> str:
        """Get progress string like '3/10'."""
        return f"{self.current_index + 1}/{len(self.cards)}"

    def advance(self) -> None:
        """Move to the next card."""
        self.current_index += 1

    def record_answer(self, correct: bool) -> None:
        """Record whether the answer was correct."""
        self.total_reviewed += 1
        if correct:
            self.correct_count += 1

    def get_mode_for_card(self) -> str:
        """Get the mode to use for the current card."""
        return self.mode.value
