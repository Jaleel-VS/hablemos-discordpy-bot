"""Conjugation session state management."""
import time
from dataclasses import dataclass, field
from enum import Enum


class ConjugationMode(Enum):
    TYPING = "typing"
    CHOICE = "choice"


@dataclass
class ConjugationCard:
    """A single conjugation question."""

    verb_id: int
    infinitive: str
    english: str
    tense: str
    pronoun: str
    correct_form: str


@dataclass
class ConjugationSession:
    """State for an active conjugation session."""

    user_id: int
    mode: ConjugationMode
    cards: list[ConjugationCard] = field(default_factory=list)
    current_index: int = 0
    correct_count: int = 0
    total_reviewed: int = 0
    created_at: float = field(default_factory=time.time)

    @property
    def current_card(self) -> ConjugationCard | None:
        if self.current_index < len(self.cards):
            return self.cards[self.current_index]
        return None

    @property
    def is_complete(self) -> bool:
        return self.current_index >= len(self.cards)

    @property
    def progress_text(self) -> str:
        return f"{self.current_index + 1}/{len(self.cards)}"

    def advance(self) -> None:
        self.current_index += 1

    def record_answer(self, correct: bool) -> None:
        self.total_reviewed += 1
        if correct:
            self.correct_count += 1
