"""Multi-agent system - World Builder, Character Actor, Narrator."""

from typing import Dict, List, Optional
from novelty.world import WorldState
from novelty.memory import MemoryKeeper
from novelty.llm import LLMClient


class Agent:
    """Base agent."""

    def __init__(self, llm: LLMClient):
        self.llm = llm

    def _chat(self, system: str, user: str, temperature: float = 0.8,
              max_tokens: int = 1024) -> str:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        return self.llm.chat(messages, temperature=temperature, max_tokens=max_tokens)


class WorldBuilder(Agent):
    """Generates initial world lore, characters, locations, and items.

    Runs at game start and on player request. Not every turn.
    """

    SYSTEM_PROMPT = """You are a world-building engine for an interactive fiction game.
Generate rich, detailed world settings based on the player's genre/theme/setting description.

Output MUST be valid JSON with this structure:
{
  "title": "Story title",
  "synopsis": "1-2 sentence premise",
  "characters": [
    {
      "id": "char_id",
      "name": "Character Name",
      "description": "Physical appearance and background",
      "personality": "Key personality traits",
      "location": "location_id where they start",
      "is_player": false
    }
  ],
  "locations": [
    {
      "id": "loc_id",
      "name": "Location Name",
      "description": "What this place looks like, feels like",
      "atmosphere": "Current mood/ambiance",
      "connections": ["other_loc_id"]
    }
  ],
  "items": [
    {
      "id": "item_id",
      "name": "Item Name",
      "description": "What it is, what it does",
      "location": "loc_id or owner char_id"
    }
  ],
  "relationships": [
    {
      "from": "char_a_id",
      "to": "char_b_id",
      "relation": "e.g. old friends, rivals, siblings",
      "notes": "context"
    }
  ]
}

Rules:
- Generate at least 1 player character, 2-3 NPCs, 2-3 locations
- Make the world feel lived-in with atmosphere and sensory details
- Include at least 2 items that could matter to the plot
- Create interesting relationship dynamics
- Use simple ASCII IDs (lowercase, underscores)
"""

    def generate_world(self, genre: str, description: str = "",
                       player_name: str = "Hero") -> WorldState:
        """Generate a complete world from a genre/description."""
        prompt = f"Genre: {genre}"
        if description:
            prompt += f"\nSetting: {description}"
        prompt += f"\nPlayer character name: {player_name}"
        prompt += "\n\nGenerate a complete world. Output ONLY valid JSON."

        raw = self._chat(self.SYSTEM_PROMPT, prompt, temperature=0.9, max_tokens=3000)
        return self._parse_world(raw)

    def expand_world(self, world: WorldState, what: str) -> Dict:
        """Add new elements to an existing world."""
        system = self.SYSTEM_PROMPT + "\n\nCurrent world:\n" + self._world_summary(world)
        prompt = f"Add the following to this world: {what}\n\nOutput ONLY the new elements as JSON."
        raw = self._chat(system, prompt, temperature=0.9, max_tokens=1500)
        return self._parse_json(raw)

    def _parse_world(self, raw: str) -> WorldState:
        data = self._parse_json(raw)
        world = WorldState()
        world.title = data.get("title", "Untitled")
        world.synopsis = data.get("synopsis", "")

        for c in data.get("characters", []):
            world.add_character(
                c["id"], c["name"],
                description=c.get("description", ""),
                personality=c.get("personality", ""),
                location=c.get("location", ""),
                is_player=c.get("is_player", False),
            )

        for l in data.get("locations", []):
            world.add_location(
                l["id"], l["name"],
                description=l.get("description", ""),
                connections=l.get("connections", []),
            )
            if l.get("atmosphere"):
                world.locations[l["id"]]["atmosphere"] = l["atmosphere"]

        for i in data.get("items", []):
            loc = i.get("location", "")
            owner = ""
            # If location matches a character, it's an owner
            if loc in world.characters:
                owner = loc
                loc = ""
            item = world.add_item(i["id"], i["name"],
                                  description=i.get("description", ""),
                                  location=loc, owner=owner)
            if owner:
                world.give_item(i["id"], owner)

        for r in data.get("relationships", []):
            world.set_relationship(
                r["from"], r["to"],
                relation=r.get("relation", ""),
                notes=r.get("notes", ""),
            )

        return world

    def _parse_json(self, raw: str) -> Dict:
        # Extract JSON from possible markdown code blocks
        text = raw.strip()
        if "```json" in text:
            text = text.split("```json", 1)[1].split("```", 1)[0]
        elif "```" in text:
            text = text.split("```", 1)[1].split("```", 1)[0]
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Try to find JSON object
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start:end])
                except json.JSONDecodeError:
                    pass
            return {}


class CharacterActor(Agent):
    """Generates NPC dialogue and actions in-character."""

    SYSTEM_PROMPT = """You are a character actor in an interactive fiction game.
You think and respond IN CHARACTER as the specified NPC.

Rules:
- Stay true to the character's personality, background, and current emotional state
- React naturally to what's happening in the scene
- Use speech patterns that fit the character (formal/casual/archaic/etc.)
- Show emotions through actions and dialogue, don't just state them
- Keep responses concise (1-3 paragraphs)
- End with an action or line that invites response

Output format: Write as the character. No meta-commentary.
"""

    def act(self, character: Dict, scene_context: str,
            recent_dialogue: str, direction: str = "") -> str:
        """Generate a character's response in a scene."""
        system = self.SYSTEM_PROMPT
        system += f"\n\n## Your Character\nName: {character['name']}"
        if character.get("description"):
            system += f"\nAppearance/Background: {character['description']}"
        if character.get("personality"):
            system += f"\nPersonality: {character['personality']}"

        prompt = f"## Current Scene\n{scene_context}\n\n"
        if recent_dialogue:
            prompt += f"## Recent Dialogue\n{recent_dialogue}\n\n"
        if direction:
            prompt += f"## Direction (subtle guidance, not spoken)\n{direction}\n\n"
        prompt += f"Respond as {character['name']}. What do you say or do?"

        return self._chat(system, prompt, temperature=0.85, max_tokens=500)


class Narrator(Agent):
    """Drives the plot, describes the world, manages pacing and tension."""

    SYSTEM_PROMPT = """You are the narrator and director of an interactive fiction game.
You describe the world, advance the plot, and create dramatic tension.

Your responsibilities:
1. Describe environments with sensory detail (sights, sounds, smells, textures)
2. Introduce unexpected events naturally (weather, arrivals, discoveries)
3. Manage pacing - slow down for emotional moments, speed up for action
4. Track dramatic tension and build toward satisfying story beats
5. When the player describes an action, describe the CONSEQUENCES vividly
6. Transition between scenes smoothly

Rules:
- Write in literary prose, like a novel narrator
- NEVER control the player character's dialogue or inner thoughts
- You CAN describe NPC reactions and environmental responses
- End with something that invites the player's next move
- Keep responses to 2-4 paragraphs typically
"""

    def narrate(self, world_ctx: str, memory_ctx: str,
                player_input: str, scene_summary: str = "") -> str:
        """Generate narrative response to player input."""
        system = self.SYSTEM_PROMPT

        prompt = ""
        if world_ctx:
            prompt += f"## World State\n{world_ctx}\n\n"
        if memory_ctx:
            prompt += f"## Story Memory\n{memory_ctx}\n\n"
        if scene_summary:
            prompt += f"## Current Scene\n{scene_summary}\n\n"
        prompt += f"## Player Input\n{player_input}\n\n"
        prompt += "Narrate what happens next."

        return self._chat(system, prompt, temperature=0.85, max_tokens=800)

    def suggest_direction(self, world: WorldState, memory: MemoryKeeper) -> str:
        """Suggest possible story directions (for the player's reference)."""
        system = "You are a story advisor. Suggest 3 possible directions the story could go next. Be brief (1 sentence each). Creative and varied."

        ctx = memory.get_full_context(max_chars=2000)
        prompt = f"Story so far:\n{ctx}\n\nSuggest 3 directions:"

        return self._chat(system, prompt, temperature=0.9, max_tokens=200)


import json  # needed by WorldBuilder._parse_json
