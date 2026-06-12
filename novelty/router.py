"""Router - interprets player input and dispatches to appropriate agents."""

import re
from typing import Dict, List, Optional, Tuple
from novelty.world import WorldState


class Router:
    """Routes player input to the correct agent(s)."""

    # Meta commands (start with /)
    COMMANDS = {
        "/help": "Show available commands",
        "/save": "Save game",
        "/load": "Load game",
        "/world": "Show world state",
        "/chars": "Show characters",
        "/locations": "Show locations",
        "/items": "Show items",
        "/add": "Add new element (character/location/item)",
        "/edit": "Edit existing element",
        "/suggest": "Get story direction suggestions",
        "/summary": "Summarize story so far",
        "/chapter": "Advance to next chapter",
        "/flag": "Set a story flag",
        "/relate": "Set relationship between characters",
        "/quit": "Exit game",
    }

    def __init__(self, world: WorldState):
        self.world = world
        self._player_char_id = None

    @property
    def player_char_id(self) -> Optional[str]:
        """Find the player character ID."""
        if self._player_char_id and self._player_char_id in self.world.characters:
            return self._player_char_id
        for cid, char in self.world.characters.items():
            if char.get("is_player"):
                self._player_char_id = cid
                return cid
        return None

    def route(self, text: str) -> Dict:
        """Analyze player input and determine routing.

        Returns dict with:
            type: "command" | "meta" | "dialogue" | "action" | "narration"
            command: str (if type is "command")
            content: str
            target_characters: list of character IDs involved
            is_dialogue: bool
            is_action: bool
            is_meta: bool
        """
        text = text.strip()
        if not text:
            return {"type": "empty", "content": ""}

        # Check for commands
        if text.startswith("/"):
            return self._parse_command(text)

        # Check for OOC (out of character)
        if text.startswith("[OOC") or text.startswith("[ooc"):
            return {"type": "meta", "content": text, "is_meta": True,
                    "is_dialogue": False, "is_action": False,
                    "target_characters": []}

        # Check for dialogue (contains quotes or character name says pattern)
        is_dialogue, speaker, content = self._parse_dialogue(text)
        if is_dialogue:
            target_chars = self._find_mentioned_characters(text)
            return {
                "type": "dialogue",
                "content": content,
                "speaker": speaker,
                "is_dialogue": True,
                "is_action": False,
                "is_meta": False,
                "target_characters": target_chars,
            }

        # Check for narration/description (player acting as author)
        is_narration = self._detect_narration(text)
        if is_narration:
            target_chars = self._find_mentioned_characters(text)
            return {
                "type": "narration",
                "content": text,
                "is_dialogue": False,
                "is_action": False,
                "is_meta": False,
                "is_narration": True,
                "target_characters": target_chars,
            }

        # Default: action (player describing what their character does)
        target_chars = self._find_mentioned_characters(text)
        return {
            "type": "action",
            "content": text,
            "is_dialogue": False,
            "is_action": True,
            "is_meta": False,
            "target_characters": target_chars,
        }

    def _parse_command(self, text: str) -> Dict:
        parts = text.split(None, 1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""
        return {
            "type": "command",
            "command": cmd,
            "args": args,
            "content": text,
            "is_dialogue": False,
            "is_action": False,
            "is_meta": True,
            "target_characters": [],
        }

    def _parse_dialogue(self, text: str) -> Tuple[bool, str, str]:
        """Check if text contains dialogue. Returns (is_dialogue, speaker, content)."""
        # Pattern: "CharacterName: 'dialogue text'" or "CharacterName says: text"
        patterns = [
            r'^(\w+):\s*["\u201c](.+?)["\u201d]',
            r'^(\w+)\s+says?[,:]?\s*["\u201c](.+?)["\u201d]',
            r'^["\u201c](.+?)["\u201d]\s*(\w+)\s+says?',
        ]
        for pattern in patterns:
            m = re.match(pattern, text, re.IGNORECASE | re.DOTALL)
            if m:
                groups = m.groups()
                if len(groups) == 2:
                    # Check if first group is a character name
                    if groups[0] in self.world.characters:
                        return True, groups[0], groups[1]
                    # Second pattern match
                    if groups[1] in self.world.characters:
                        return True, groups[1], groups[0]

        # Check for quoted text (player speaking as their character)
        if '"' in text or '\u201c' in text:
            quote_match = re.search(r'["\u201c](.+?)["\u201d]', text)
            if quote_match:
                player_id = self.player_char_id
                if player_id:
                    return True, player_id, text

        return False, "", text

    def _detect_narration(self, text: str) -> bool:
        """Detect if player is writing as narrator/author."""
        narration_signals = [
            "suddenly", "meanwhile", "the sky", "a loud",
            "from behind", "the door", "a figure",
            "the next morning", "hours later", "as the sun",
            "rain began", "the ground", "an earthquake",
        ]
        text_lower = text.lower()
        # If it starts with a scene description pattern
        if any(text_lower.startswith(s) for s in ["the ", "a ", "as ", "from ", "suddenly", "meanwhile"]):
            return True
        # If it contains time/space transitions
        if any(s in text_lower for s in narration_signals):
            # But only if it's NOT a simple action
            if not text_lower.startswith("i ") and not text_lower.startswith("we "):
                return True
        return False

    def _find_mentioned_characters(self, text: str) -> List[str]:
        """Find character IDs mentioned in the text."""
        found = []
        text_lower = text.lower()
        for cid, char in self.world.characters.items():
            if char["name"].lower() in text_lower:
                found.append(cid)
        return found
