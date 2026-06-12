"""World state management - characters, locations, items, events."""

import json
import time
from pathlib import Path
from typing import Dict, List, Optional


class WorldState:
    """Manages the entire game world state."""

    def __init__(self):
        self.title = "Untitled Story"
        self.synopsis = ""
        self.characters = {}  # id -> character dict
        self.locations = {}   # id -> location dict
        self.items = {}       # id -> item dict
        self.events = []      # chronological event log
        self.relationships = {}  # "char_a:char_b" -> relationship dict
        self.flags = {}       # arbitrary story flags
        self.chapter = 1
        self.created_at = time.time()
        self.updated_at = time.time()

    # ── Characters ───────────────────────────────────────────────────────

    def add_character(self, char_id: str, name: str, description: str = "",
                      personality: str = "", location: str = "",
                      is_player: bool = False) -> Dict:
        char = {
            "id": char_id,
            "name": name,
            "description": description,
            "personality": personality,
            "location": location,
            "is_player": is_player,
            "state": "active",  # active, dead, missing, etc.
            "inventory": [],
            "traits": [],
            "notes": "",
        }
        self.characters[char_id] = char
        self.updated_at = time.time()
        return char

    def get_character(self, char_id: str) -> Optional[Dict]:
        return self.characters.get(char_id)

    def update_character(self, char_id: str, **kwargs):
        if char_id in self.characters:
            self.characters[char_id].update(kwargs)
            self.updated_at = time.time()

    def move_character(self, char_id: str, location_id: str):
        if char_id in self.characters:
            self.characters[char_id]["location"] = location_id
            self.updated_at = time.time()

    # ── Locations ────────────────────────────────────────────────────────

    def add_location(self, loc_id: str, name: str, description: str = "",
                     connections: Optional[List[str]] = None) -> Dict:
        loc = {
            "id": loc_id,
            "name": name,
            "description": description,
            "connections": connections or [],
            "items": [],
            "atmosphere": "",
            "notes": "",
        }
        self.locations[loc_id] = loc
        self.updated_at = time.time()
        return loc

    def get_location(self, loc_id: str) -> Optional[Dict]:
        return self.locations.get(loc_id)

    def connect_locations(self, loc_a: str, loc_b: str):
        if loc_a in self.locations and loc_b in self.locations:
            if loc_b not in self.locations[loc_a]["connections"]:
                self.locations[loc_a]["connections"].append(loc_b)
            if loc_a not in self.locations[loc_b]["connections"]:
                self.locations[loc_b]["connections"].append(loc_a)
            self.updated_at = time.time()

    # ── Items ────────────────────────────────────────────────────────────

    def add_item(self, item_id: str, name: str, description: str = "",
                 location: str = "", owner: str = "") -> Dict:
        item = {
            "id": item_id,
            "name": name,
            "description": description,
            "location": location,
            "owner": owner,
            "properties": {},
            "notes": "",
        }
        self.items[item_id] = item
        self.updated_at = time.time()
        return item

    def give_item(self, item_id: str, char_id: str):
        if item_id in self.items:
            self.items[item_id]["owner"] = char_id
            self.items[item_id]["location"] = ""
            if char_id in self.characters:
                if item_id not in self.characters[char_id]["inventory"]:
                    self.characters[char_id]["inventory"].append(item_id)
            self.updated_at = time.time()

    # ── Relationships ────────────────────────────────────────────────────

    def set_relationship(self, char_a: str, char_b: str, relation: str = "",
                         sentiment: float = 0, notes: str = ""):
        key = f"{char_a}:{char_b}"
        self.relationships[key] = {
            "from": char_a,
            "to": char_b,
            "relation": relation,
            "sentiment": sentiment,  # -10 to 10
            "notes": notes,
        }
        self.updated_at = time.time()

    # ── Events ───────────────────────────────────────────────────────────

    def add_event(self, summary: str, event_type: str = "narrative",
                  characters: Optional[List[str]] = None,
                  location: str = "", importance: int = 5):
        event = {
            "timestamp": time.time(),
            "chapter": self.chapter,
            "type": event_type,
            "summary": summary,
            "characters": characters or [],
            "location": location,
            "importance": importance,
        }
        self.events.append(event)
        self.updated_at = time.time()
        return event

    # ── Flags ────────────────────────────────────────────────────────────

    def set_flag(self, key: str, value=True):
        self.flags[key] = value
        self.updated_at = time.time()

    def get_flag(self, key, default=None):
        return self.flags.get(key, default)

    # ── Serialization ────────────────────────────────────────────────────

    def to_dict(self) -> Dict:
        return {
            "title": self.title,
            "synopsis": self.synopsis,
            "characters": self.characters,
            "locations": self.locations,
            "items": self.items,
            "events": self.events[-200:],  # Keep last 200 events
            "relationships": self.relationships,
            "flags": self.flags,
            "chapter": self.chapter,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "WorldState":
        world = cls()
        world.title = data.get("title", "Untitled")
        world.synopsis = data.get("synopsis", "")
        world.characters = data.get("characters", {})
        world.locations = data.get("locations", {})
        world.items = data.get("items", {})
        world.events = data.get("events", [])
        world.relationships = data.get("relationships", {})
        world.flags = data.get("flags", {})
        world.chapter = data.get("chapter", 1)
        world.created_at = data.get("created_at", time.time())
        world.updated_at = data.get("updated_at", time.time())
        return world

    def save(self, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, path: str) -> "WorldState":
        with open(path, "r", encoding="utf-8") as f:
            return cls.from_dict(json.load(f))
