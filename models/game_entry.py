"""
models/game_entry.py – Immutable data model for a single game catalogue entry.
"""

from dataclasses import dataclass, field
from typing import List


@dataclass(frozen=True)
class GameEntry:
    """
    Represents one game in the master catalogue.

    Attributes
    ----------
    title       : Human-readable game title.
    detail_url  : Absolute URL to the game's detail / mirror page.
    region      : Optional region tag parsed from the catalogue (e.g. "NTSC").
    size_hint   : Optional size string parsed from the catalogue (e.g. "7.8 GB").
    """

    title: str
    detail_url: str
    region: str = ""
    size_hint: str = ""

    def __str__(self) -> str:
        parts = [self.title]
        if self.region:
            parts.append(f"[{self.region}]")
        if self.size_hint:
            parts.append(f"({self.size_hint})")
        return "  ".join(parts)


@dataclass
class MirrorLink:
    """
    Represents a single downloadable mirror for a game.

    Attributes
    ----------
    label : Human-readable mirror name / host.
    url   : Direct download URL.
    """

    label: str
    url: str

    def __str__(self) -> str:
        return f"{self.label}  →  {self.url}"
