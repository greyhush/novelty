"""Memory keeper - tracks events, prevents contradictions, manages context."""

import json
import hashlib
from typing import Dict, List, Optional
from novelty.world import WorldState


class MemoryKeeper:
    """Tracks narrative memory and enforces consistency."""

    def __init__(self, world: WorldState):
        self.world = world
        self.summaries = []      # chapter summaries
        self.facts = []          # established facts that must not contradict
        self.last_summary_len = 0

    def record_event(self, summary: str, event_type: str = "narrative",
                     characters: Optional[List[str]] = None,
                     location: str = "", importance: int = 5):
        """Record a new event and check for contradictions."""
        self.world.add_event(summary, event_type, characters, location, importance)

        # Auto-extract facts from important events
        if importance >= 7:
            self.facts.append({
                "chapter": self.world.chapter,
                "fact": summary,
                "importance": importance,
            })

    def get_recent_context(self, n_events: int = 10) -> str:
        """Get recent events as formatted text."""
        events = self.world.events[-n_events:]
        lines = []
        for e in events:
            ch = e.get("chapter", "?")
            lines.append(f"[Ch.{ch}] {e['summary']}")
        return "\n".join(lines)

    def get_facts_context(self, max_facts: int = 20) -> str:
        """Get established facts for consistency checking."""
        recent_facts = self.facts[-max_facts:]
        if not recent_facts:
            return ""
        lines = ["## Established Facts (DO NOT CONTRADICT)"]
        for f in recent_facts:
            lines.append(f"- [Ch.{f['chapter']}] {f['fact']}")
        return "\n".join(lines)

    def summarize_chapter(self, chapter: Optional[int] = None) -> str:
        """Generate a summary of a chapter's events."""
        ch = chapter or self.world.chapter
        chapter_events = [e for e in self.world.events if e.get("chapter") == ch]
        if not chapter_events:
            return f"Chapter {ch}: No events recorded."

        summary_parts = []
        for e in chapter_events:
            summary_parts.append(e["summary"])

        combined = " | ".join(summary_parts)
        summary = f"Chapter {ch} summary: {combined[:500]}"
        self.summaries.append({
            "chapter": ch,
            "summary": summary,
            "event_count": len(chapter_events),
        })
        return summary

    def get_full_context(self, max_chars: int = 4000) -> str:
        """Build full memory context for agents."""
        parts = []

        # Chapter summaries (compact)
        if self.summaries:
            parts.append("## Story So Far")
            for s in self.summaries[-5:]:
                parts.append(s["summary"])

        # Facts
        facts_ctx = self.get_facts_context()
        if facts_ctx:
            parts.append(facts_ctx)

        # Recent events
        recent = self.get_recent_context(8)
        if recent:
            parts.append("## Recent Events")
            parts.append(recent)

        full = "\n\n".join(parts)
        if len(full) > max_chars:
            # Truncate from the beginning
            full = full[-max_chars:]
            full = "..." + full[full.index("\n"):]
        return full

    def to_dict(self) -> Dict:
        return {
            "summaries": self.summaries,
            "facts": self.facts,
        }

    @classmethod
    def from_dict(cls, data: Dict, world: WorldState) -> "MemoryKeeper":
        mk = cls(world)
        mk.summaries = data.get("summaries", [])
        mk.facts = data.get("facts", [])
        return mk
