from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime


@dataclass
class Article:
    title: str
    url: str
    source_type: str  # "official" | "media" | "research" | "community" | "product"
    source_name: str  # "r/OpenAI", "TechCrunch", "OpenAI Blog", etc.
    published_at: datetime
    score: int | None = None
    comments: int | None = None
    summary: str | None = None
    tags: list[str] = field(default_factory=list)
    content: str = ""
    importance_score: float | None = None
    title_ko: str = ""
    summary_ko: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["published_at"] = self.published_at.isoformat()
        return d
