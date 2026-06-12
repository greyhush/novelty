"""Game engine - orchestrates agents and manages game loop."""

import json
import time
from pathlib import Path
from typing import Dict, List, Optional

from novelty.world import WorldState
from novelty.memory import MemoryKeeper
from novelty.llm import LLMClient
from novelty.agents import WorldBuilder, CharacterActor, Narrator
from novelty.router import Router
from novelty.checker import ConsistencyChecker


class GameEngine:
    """Main game engine - ties all agents together."""

    def __init__(self, llm: LLMClient):
        self.llm = llm
        self.world = WorldState()
        self.memory = MemoryKeeper(self.world)
        self.router = Router(self.world)
        self.checker = ConsistencyChecker(self.world, self.memory)

        # Agents
        self.world_builder = WorldBuilder(llm)
        self.character_actor = CharacterActor(llm)
        self.narrator = Narrator(llm)

        # State
        self.running = False
        self.auto_narrate = True  # auto-generate narration after dialogue
        self.last_response = ""

    def new_game(self, genre: str, description: str = "",
                 player_name: str = "Hero") -> str:
        """Start a new game by generating the world."""
        self.world = self.world_builder.generate_world(genre, description, player_name)
        self.memory = MemoryKeeper(self.world)
        self.router = Router(self.world)
        self.checker = ConsistencyChecker(self.world, self.memory)

        self.memory.record_event(
            f"A new story begins: {self.world.title}. {self.world.synopsis}",
            event_type="system", importance=8,
        )

        return self._format_world_intro()

    def process_input(self, text: str) -> str:
        """Process player input and return game response."""
        routed = self.router.route(text)
        response = ""

        if routed["type"] == "empty":
            return ""

        elif routed["type"] == "command":
            response = self._handle_command(routed)

        elif routed["type"] == "meta":
            # OOC discussion
            self.memory.record_event(f"[OOC] {text}", event_type="system", importance=1)
            response = self._handle_meta(text)

        elif routed["type"] == "dialogue":
            # Consistency check on player input
            check = self.checker.check_player_input(text)
            # Record player dialogue
            speaker = routed.get("speaker", "player")
            char_name = self.world.characters.get(speaker, {}).get("name", speaker)
            self.memory.record_event(
                f'{char_name} says: "{routed["content"]}"',
                event_type="player_input",
                characters=[speaker],
                importance=5,
            )
            # Generate NPC responses (with consistency check)
            response = self._handle_dialogue(routed, check)

        elif routed["type"] == "narration":
            # Player is writing as author
            check = self.checker.check_player_input(text)
            self.memory.record_event(
                text, event_type="player_input", importance=6,
            )
            response = self._handle_narration(routed, check)

        elif routed["type"] == "action":
            # Player character action
            check = self.checker.check_player_input(text)
            self.memory.record_event(
                text, event_type="player_input", importance=5,
            )
            response = self._handle_action(routed, check)

        self.last_response = response
        return response

    def _handle_command(self, routed: Dict) -> str:
        cmd = routed["command"]
        args = routed.get("args", "")

        if cmd == "/help":
            return self._cmd_help()
        elif cmd == "/save":
            return self._cmd_save(args)
        elif cmd == "/load":
            return self._cmd_load(args)
        elif cmd == "/world":
            return self._cmd_world()
        elif cmd == "/chars":
            return self._cmd_chars()
        elif cmd == "/locations":
            return self._cmd_locations()
        elif cmd == "/items":
            return self._cmd_items()
        elif cmd == "/add":
            return self._cmd_add(args)
        elif cmd == "/suggest":
            return self._cmd_suggest()
        elif cmd == "/summary":
            return self._cmd_summary()
        elif cmd == "/chapter":
            return self._cmd_chapter()
        elif cmd == "/flag":
            return self._cmd_flag(args)
        elif cmd == "/relate":
            return self._cmd_relate(args)
        elif cmd == "/quit":
            self.running = False
            return "Farewell, storyteller."
        else:
            return f"Unknown command: {cmd}. Type /help for available commands."

    def _handle_meta(self, text: str) -> str:
        """Handle out-of-character discussion."""
        system = "You are a helpful game assistant. The player is making an OOC comment. Respond briefly and helpfully, then suggest what they might want to do next."
        return self.llm.chat([
            {"role": "system", "content": system},
            {"role": "user", "content": text},
        ], temperature=0.7, max_tokens=300)

    def _handle_dialogue(self, routed: Dict, check: Dict = None) -> str:
        """Generate NPC responses to dialogue, with consistency checking."""
        responses = []

        # If there are high-severity issues, have the narrator address them first
        if check and not check["valid"]:
            high_issues = [i for i in check.get("issues", []) if i.get("severity") == "high"]
            if high_issues:
                # Inject consistency handling into the scene
                issue_desc = "; ".join(i["detail"] for i in high_issues)
                suggestion = check.get("suggestion", "")
                # Narrator acknowledges the anomaly gracefully
                anomaly = self.narrator.narrate(
                    world_ctx=self._build_world_context(),
                    memory_ctx=self.memory.get_full_context(2000),
                    player_input=f"[CONSISTENCY ALERT] The player just said/did something contradictory: {issue_desc}. "
                                 f"Handle this gracefully in the narrative. Options: {suggestion}. "
                                 f"DO NOT break immersion. Work it into the story naturally.",
                    scene_summary=self._build_scene_context(routed.get("target_characters", [])),
                )
                responses.append(anomaly)
                self.memory.record_event(
                    f"[Anomaly] {issue_desc} — handled as: {anomaly[:100]}",
                    event_type="narrative", importance=7,
                )

        # Build scene context
        scene_ctx = self._build_scene_context(routed.get("target_characters", []))

        # For each NPC in the scene, generate their response
        for char_id in routed.get("target_characters", []):
            char = self.world.get_character(char_id)
            if char and not char.get("is_player") and char["state"] == "active":
                response = self.character_actor.act(
                    character=char,
                    scene_context=scene_ctx,
                    recent_dialogue=self.memory.get_recent_context(5),
                )

                # Check NPC output for consistency
                output_check = self.checker.check_agent_output(response, "character")
                if not output_check["valid"]:
                    # Retry with consistency instructions
                    issues = "; ".join(i["detail"] for i in output_check["issues"])
                    response = self.character_actor.act(
                        character=char,
                        scene_context=scene_ctx + f"\n\n[IMPORTANT: {issues}]",
                        recent_dialogue=self.memory.get_recent_context(5),
                        direction=f"You must stay consistent. {issues}",
                    )

                responses.append(f'**{char["name"]}:** {response}')
                self.memory.record_event(
                    f'{char["name"]}: {response}',
                    event_type="narrative",
                    characters=[char_id],
                    importance=5,
                )

        # If no specific NPCs targeted, have the narrator respond
        if not responses or (len(responses) == 1 and check and not check["valid"]):
            narration = self.narrator.narrate(
                world_ctx=self._build_world_context(),
                memory_ctx=self.memory.get_full_context(),
                player_input=routed["content"],
            )
            responses.append(narration)
            self.memory.record_event(narration, event_type="narrative", importance=5)

        return "\n\n".join(responses)

    def _handle_narration(self, routed: Dict, check: Dict = None) -> str:
        """Player is writing as author - acknowledge and add NPC reactions."""
        # If there are issues, have the narrator handle them
        prefix = ""
        if check and not check["valid"]:
            high_issues = [i for i in check.get("issues", []) if i.get("severity") == "high"]
            if high_issues:
                issue_desc = "; ".join(i["detail"] for i in high_issues)
                suggestion = check.get("suggestion", "")
                prefix = self.narrator.narrate(
                    world_ctx=self._build_world_context(),
                    memory_ctx=self.memory.get_full_context(2000),
                    player_input=f"[CONSISTENCY ALERT] {issue_desc}. Handle gracefully. Options: {suggestion}",
                )
                self.memory.record_event(
                    f"[Anomaly] {issue_desc} — {prefix[:100]}",
                    event_type="narrative", importance=7,
                )

        # The player's narration IS the narrative. We just add NPC responses.
        scene_ctx = self._build_scene_context(routed.get("target_characters", []))

        # Have relevant NPCs react
        npc_responses = []
        for char_id in routed.get("target_characters", []):
            char = self.world.get_character(char_id)
            if char and not char.get("is_player") and char["state"] == "active":
                response = self.character_actor.act(
                    character=char,
                    scene_context=scene_ctx,
                    recent_dialogue=self.memory.get_recent_context(3),
                    direction="React naturally to what just happened.",
                )

                # Check NPC output
                output_check = self.checker.check_agent_output(response, "character")
                if not output_check["valid"]:
                    issues = "; ".join(i["detail"] for i in output_check["issues"])
                    response = self.character_actor.act(
                        character=char,
                        scene_context=scene_ctx + f"\n\n[IMPORTANT: {issues}]",
                        recent_dialogue=self.memory.get_recent_context(3),
                        direction=f"Stay consistent. {issues}",
                    )

                npc_responses.append(f'**{char["name"]}:** {response}')

        result = ""
        if prefix:
            result += f"{prefix}\n\n"
        result += f"*{routed['content']}*\n"
        if npc_responses:
            result += "\n\n" + "\n\n".join(npc_responses)
        else:
            # Narrator adds a brief continuation
            continuation = self.narrator.narrate(
                world_ctx=self._build_world_context(),
                memory_ctx=self.memory.get_full_context(2000),
                player_input=f"The player just described: {routed['content']}\nContinue the scene briefly.",
            )
            result += f"\n\n{continuation}"

        return result

    def _handle_action(self, routed: Dict, check: Dict = None) -> str:
        """Handle player character action with consistency checking."""
        # If there are high-severity issues, address them first
        prefix = ""
        if check and not check["valid"]:
            high_issues = [i for i in check.get("issues", []) if i.get("severity") == "high"]
            if high_issues:
                issue_desc = "; ".join(i["detail"] for i in high_issues)
                suggestion = check.get("suggestion", "")
                prefix = self.narrator.narrate(
                    world_ctx=self._build_world_context(),
                    memory_ctx=self.memory.get_full_context(2000),
                    player_input=f"[CONSISTENCY ALERT] {issue_desc}. Handle gracefully in the narrative. Options: {suggestion}",
                )
                self.memory.record_event(
                    f"[Anomaly] {issue_desc} — {prefix[:100]}",
                    event_type="narrative", importance=7,
                )

        narration = self.narrator.narrate(
            world_ctx=self._build_world_context(),
            memory_ctx=self.memory.get_full_context(),
            player_input=routed["content"],
            scene_summary=self._build_scene_context(routed.get("target_characters", [])),
        )
        self.memory.record_event(narration, event_type="narrative", importance=5)

        # Also have NPCs in the scene react if appropriate
        player_loc = None
        player_id = self.router.player_char_id
        if player_id:
            player = self.world.get_character(player_id)
            if player:
                player_loc = player.get("location")

        npc_parts = []
        if player_loc:
            for cid, char in self.world.characters.items():
                if cid != player_id and char.get("location") == player_loc and char["state"] == "active":
                    # NPC might react
                    if any(word in routed["content"].lower() for word in
                           ["attack", "fight", "break", "shout", "scream", "run", "fall", "drop", "open"]):
                        response = self.character_actor.act(
                            character=char,
                            scene_context=self._build_scene_context([cid]),
                            recent_dialogue=narration[:300],
                            direction="React to what the player character just did.",
                        )

                        # Check NPC output
                        output_check = self.checker.check_agent_output(response, "character")
                        if not output_check["valid"]:
                            issues = "; ".join(i["detail"] for i in output_check["issues"])
                            response = self.character_actor.act(
                                character=char,
                                scene_context=self._build_scene_context([cid]) + f"\n\n[IMPORTANT: {issues}]",
                                recent_dialogue=narration[:300],
                                direction=f"Stay consistent. {issues}",
                            )

                        npc_parts.append(f'**{char["name"]}:** {response}')

        result = ""
        if prefix:
            result += f"{prefix}\n\n"
        result += narration
        if npc_parts:
            result += "\n\n" + "\n\n".join(npc_parts)

        return result

    # ── Scene building ───────────────────────────────────────────────────

    def _build_scene_context(self, involved_chars: List[str] = None) -> str:
        """Build current scene description."""
        parts = []
        player_id = self.router.player_char_id
        player = self.world.get_character(player_id) if player_id else None

        if player and player.get("location"):
            loc = self.world.get_location(player["location"])
            if loc:
                parts.append(f"Location: {loc['name']} — {loc['description']}")
                if loc["atmosphere"]:
                    parts.append(f"Atmosphere: {loc['atmosphere']}")

                # Who else is here?
                others = [c for cid, c in self.world.characters.items()
                          if cid != player_id and c.get("location") == player["location"]
                          and c["state"] == "active"]
                if others:
                    parts.append("Present: " + ", ".join(
                        f"{c['name']} ({c.get('personality', '')[:30]})" for c in others
                    ))

                # Items here
                scene_items = [i for iid, i in self.world.items.items()
                               if i.get("location") == player["location"]]
                if scene_items:
                    parts.append("Items: " + ", ".join(i["name"] for i in scene_items))

        return "\n".join(parts) if parts else "The scene is undefined."

    def _build_world_context(self) -> str:
        """Build brief world context for agents."""
        parts = [f"Title: {self.world.title}"]
        if self.world.synopsis:
            parts.append(f"Premise: {self.world.synopsis}")
        parts.append(f"Chapter: {self.world.chapter}")
        return "\n".join(parts)

    # ── Command handlers ─────────────────────────────────────────────────

    def _cmd_help(self) -> str:
        lines = ["**Available Commands:**"]
        for cmd, desc in self.Router.COMMANDS.items():
            lines.append(f"  `{cmd}` — {desc}")
        lines.append("\n**Tips:**")
        lines.append("  • Write dialogue with quotes: \"Hello there!\"")
        lines.append("  • Write actions normally: I walk to the door")
        lines.append("  • Write as author: The sky darkens suddenly")
        lines.append("  • Use [OOC: ...] for meta discussion")
        return "\n".join(lines)

    def _cmd_save(self, args: str) -> str:
        save_dir = Path.home() / ".novelty" / "saves"
        save_dir.mkdir(parents=True, exist_ok=True)

        name = args.strip() or f"autosave_{int(time.time())}"
        save_path = save_dir / f"{name}.json"

        data = {
            "world": self.world.to_dict(),
            "memory": self.memory.to_dict(),
            "llm": self.llm.to_dict(),
        }
        save_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        return f"Game saved: {save_path}"

    def _cmd_load(self, args: str) -> str:
        save_dir = Path.home() / ".novelty" / "saves"
        name = args.strip()

        if not name:
            # List saves
            saves = list(save_dir.glob("*.json"))
            if not saves:
                return "No saves found."
            lines = ["**Available saves:**"]
            for s in sorted(saves):
                lines.append(f"  • {s.stem}")
            lines.append("\nUse `/load <name>` to load a save.")
            return "\n".join(lines)

        save_path = save_dir / f"{name}.json"
        if not save_path.exists():
            return f"Save not found: {name}"

        data = json.loads(save_path.read_text())
        self.world = WorldState.from_dict(data["world"])
        self.memory = MemoryKeeper.from_dict(data["memory"], self.world)
        self.router = Router(self.world)
        self.checker = ConsistencyChecker(self.world, self.memory)

        return f"Game loaded: {name}\n\n{self._format_world_intro()}"

    def _cmd_world(self) -> str:
        return f"**{self.world.title}**\n{self.world.synopsis}\nChapter: {self.world.chapter}\nCharacters: {len(self.world.characters)} | Locations: {len(self.world.locations)} | Items: {len(self.world.items)} | Events: {len(self.world.events)}"

    def _cmd_chars(self) -> str:
        if not self.world.characters:
            return "No characters defined."
        lines = ["**Characters:**"]
        for cid, char in self.world.characters.items():
            role = "🧑‍💻 PLAYER" if char.get("is_player") else "🤖 NPC"
            loc = self.world.locations.get(char.get("location", ""), {}).get("name", "?")
            lines.append(f"  {role} **{char['name']}** @ {loc}")
            if char["description"]:
                lines.append(f"    {char['description'][:80]}")
            if char["inventory"]:
                items = [self.world.items.get(i, {}).get("name", i) for i in char["inventory"]]
                lines.append(f"    Carrying: {', '.join(items)}")
        return "\n".join(lines)

    def _cmd_locations(self) -> str:
        if not self.world.locations:
            return "No locations defined."
        lines = ["**Locations:**"]
        for lid, loc in self.world.locations.items():
            lines.append(f"  📍 **{loc['name']}** — {loc['description'][:60]}")
            if loc["connections"]:
                conn = [self.world.locations.get(c, {}).get("name", c) for c in loc["connections"]]
                lines.append(f"    → {', '.join(conn)}")
        return "\n".join(lines)

    def _cmd_items(self) -> str:
        if not self.world.items:
            return "No items in the world."
        lines = ["**Items:**"]
        for iid, item in self.world.items.items():
            owner = ""
            if item["owner"]:
                owner_char = self.world.get_character(item["owner"])
                owner = f" (held by {owner_char['name']})" if owner_char else ""
            loc = ""
            if item["location"]:
                loc_name = self.world.locations.get(item["location"], {}).get("name", item["location"])
                loc = f" @ {loc_name}"
            lines.append(f"  🎒 **{item['name']}**{owner}{loc}")
            if item["description"]:
                lines.append(f"    {item['description'][:60]}")
        return "\n".join(lines)

    def _cmd_add(self, args: str) -> str:
        if not args:
            return "Usage: `/add character/location/item <description>`\nExample: `/add character A mysterious hooded figure appears in the corner`"
        parts = args.split(None, 1)
        if len(parts) < 2:
            return "Please specify what to add and a description."

        what = parts[0].lower()
        desc = parts[1]

        result = self.world_builder.expand_world(self.world, f"A {what}: {desc}")
        added = []

        for c in result.get("characters", []):
            self.world.add_character(c["id"], c["name"],
                                     description=c.get("description", ""),
                                     personality=c.get("personality", ""),
                                     location=c.get("location", ""))
            added.append(f"Character: {c['name']}")

        for l in result.get("locations", []):
            self.world.add_location(l["id"], l["name"],
                                    description=l.get("description", ""))
            added.append(f"Location: {l['name']}")

        for i in result.get("items", []):
            self.world.add_item(i["id"], i["name"],
                                description=i.get("description", ""))
            added.append(f"Item: {i['name']}")

        if added:
            self.memory.record_event(
                f"New elements added: {', '.join(added)}",
                event_type="system", importance=3,
            )
            return f"Added to world:\n" + "\n".join(f"  • {a}" for a in added)
        return "Couldn't parse what to add. Try: `/add character A brave knight named Sir Galen`"

    def _cmd_suggest(self) -> str:
        return self.narrator.suggest_direction(self.world, self.memory)

    def _cmd_summary(self) -> str:
        if not self.memory.summaries:
            self.memory.summarize_chapter()
        return self.memory.get_full_context(max_chars=3000)

    def _cmd_chapter(self) -> str:
        summary = self.memory.summarize_chapter()
        self.world.chapter += 1
        return f"Chapter {self.world.chapter - 1} closed.\n\n{summary}\n\n**Chapter {self.world.chapter} begins.**"

    def _cmd_flag(self, args: str) -> str:
        if not args:
            flags = self.world.flags
            if not flags:
                return "No story flags set."
            lines = ["**Story Flags:**"]
            for k, v in flags.items():
                lines.append(f"  • {k}: {v}")
            return "\n".join(lines)
        parts = args.split(None, 1)
        key = parts[0]
        value = parts[1] if len(parts) > 1 else "true"
        self.world.set_flag(key, value)
        return f"Flag set: {key} = {value}"

    def _cmd_relate(self, args: str) -> str:
        # Format: /relate char_a char_b relationship
        parts = args.split(None, 2)
        if len(parts) < 3:
            return "Usage: `/relate <char_a> <char_b> <relationship>`"
        self.world.set_relationship(parts[0], parts[1], relation=parts[2])
        return f"Relationship set: {parts[0]} → {parts[1]}: {parts[2]}"

    # ── Formatting ───────────────────────────────────────────────────────

    def _format_world_intro(self) -> str:
        """Format the world introduction for the player."""
        lines = [f"# {self.world.title}"]
        if self.world.synopsis:
            lines.append(f"\n*{self.world.synopsis}*\n")

        # Player character
        player_id = self.router.player_char_id
        if player_id:
            player = self.world.get_character(player_id)
            if player:
                lines.append(f"**Your character: {player['name']}**")
                if player["description"]:
                    lines.append(player["description"])
                if player["location"]:
                    loc = self.world.get_location(player["location"])
                    if loc:
                        lines.append(f"\nYou find yourself in **{loc['name']}**.")
                        lines.append(loc["description"])
                        if loc["atmosphere"]:
                            lines.append(f"*{loc['atmosphere']}*")

                # Who's here?
                others = [c for cid, c in self.world.characters.items()
                          if cid != player_id and c.get("location") == player.get("location")
                          and c["state"] == "active"]
                if others:
                    lines.append(f"\nPresent here: {', '.join(c['name'] for c in others)}")

        lines.append("\n*Type `/help` for commands. Start writing your story.*")
        return "\n".join(lines)
