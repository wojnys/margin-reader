"""Model registry for migrations and test metadata; importing creates no engine."""

from __future__ import annotations

from backend.app.modules.books.models import Book
from backend.app.modules.capture.models import Pairing
from backend.app.modules.chat.models import ChatThread, ChatTurn
from backend.app.modules.conversation.models import ConversationExpression, ConversationSet
from backend.app.modules.knowledge.models import (
    IndexJob,
    KnowledgeClaim,
    KnowledgeEntity,
    KnowledgeSummary,
    Mention,
    Passage,
    SectionSummary,
    SourcePage,
)
from backend.app.modules.practice.models import Review
from backend.app.modules.readings.models import ReadingSession, StepResult
from backend.app.modules.vocabulary.models import Vocabulary, VocabularySource

__all__ = [
    "Book",
    "ReadingSession",
    "StepResult",
    "Vocabulary",
    "VocabularySource",
    "Review",
    "Pairing",
    "ConversationSet",
    "ConversationExpression",
    "ChatThread",
    "ChatTurn",
    "IndexJob",
    "SourcePage",
    "Passage",
    "KnowledgeEntity",
    "Mention",
    "KnowledgeClaim",
    "KnowledgeSummary",
    "SectionSummary",
]
