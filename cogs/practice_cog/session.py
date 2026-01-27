"""
Practice Session State Management
"""
from dataclasses import dataclass, field
from typing import List, Optional
from enum import Enum


class PracticeMode(Enum):
    TYPING = "typing"
    CHOICE = "choice"
    MIXED = "mixed"


@dataclass
class PracticeCard:
    """A single practice card"""
    id: int
    word: str
    translation: str
    language: str
    sentence: str
    sentence_with_blank: str
    # SRS fields (may be None for new cards)
    interval_days: Optional[float] = None
    ease_factor: Optional[float] = None
    repetitions: Optional[int] = None


@dataclass
class PracticeSession:
    """State for an active practice session"""
    user_id: int
    language: str
    mode: PracticeMode
    cards: List[PracticeCard] = field(default_factory=list)
    current_index: int = 0
    correct_count: int = 0
    total_reviewed: int = 0

    @property
    def current_card(self) -> Optional[PracticeCard]:
        """Get the current card or None if session is complete"""
        if self.current_index < len(self.cards):
            return self.cards[self.current_index]
        return None

    @property
    def is_complete(self) -> bool:
        """Check if all cards have been reviewed"""
        return self.current_index >= len(self.cards)

    @property
    def progress_text(self) -> str:
        """Get progress string like '3/10'"""
        return f"{self.current_index + 1}/{len(self.cards)}"

    def advance(self) -> None:
        """Move to the next card"""
        self.current_index += 1

    def record_answer(self, correct: bool) -> None:
        """Record whether the answer was correct"""
        self.total_reviewed += 1
        if correct:
            self.correct_count += 1

    def get_mode_for_card(self) -> str:
        """Get the mode to use for the current card (handles mixed mode)"""
        if self.mode == PracticeMode.MIXED:
            # Alternate between typing and choice
            import random
            return random.choice(["typing", "choice"])
        return self.mode.value
