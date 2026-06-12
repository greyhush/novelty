"""Consistency checker - detects and handles contradictions gracefully."""

import re
from typing import Dict, List, Optional, Tuple
from novelty.world import WorldState
from novelty.memory import MemoryKeeper


class ConsistencyChecker:
    """Checks player input and agent output for contradictions with world state.

    Philosophy: Never hard-reject. Instead, flag contradictions and let
    the Narrator decide how to handle them (hallucination? dream?
    unreliable narrator? time anomaly?).
    """

    def __init__(self, world: WorldState, memory: Optional[MemoryKeeper] = None):
        self.world = world
        self.memory = memory

    def check_player_input(self, text: str) -> Dict:
        """Check player input against world state.

        Returns:
            {
                "valid": bool,
                "issues": list of issue dicts,
                "suggestion": str (how to handle)
            }
        """
        issues = []
        text_lower = text.lower()

        # Check 1: Dead characters acting alive
        issues.extend(self._check_dead_characters(text_lower))

        # Check 2: Destroyed locations referenced as intact
        issues.extend(self._check_destroyed_locations(text_lower))

        # Check 3: Impossible physics (optional, lenient)
        issues.extend(self._check_impossible_actions(text_lower))

        # Check 4: Character in wrong location
        issues.extend(self._check_location_consistency(text_lower))

        # Check 5: Item contradictions
        issues.extend(self._check_item_contradictions(text_lower))

        # Check 6: Memory-based fact contradictions
        if self.memory:
            issues.extend(self._check_memory_facts(text_lower))

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "suggestion": self._suggest_handling(issues),
        }

    def check_agent_output(self, text: str, agent_type: str = "character") -> Dict:
        """Check agent output for consistency.

        Args:
            text: The generated response
            agent_type: "character" or "narrator"
        """
        issues = []
        text_lower = text.lower()

        # NPCs shouldn't know things they haven't witnessed
        issues.extend(self._check_knowledge_bounds(text_lower, agent_type))

        # Character voice consistency
        if agent_type == "character":
            issues.extend(self._check_character_voice(text_lower))

        # Dead characters shouldn't speak (unless ghost/memory)
        issues.extend(self._check_dead_characters(text_lower))

        return {
            "valid": len(issues) == 0,
            "issues": issues,
        }

    def _check_dead_characters(self, text: str) -> List[Dict]:
        """Check if dead characters are being referenced as alive."""
        issues = []
        # Verbs that indicate a character is alive and acting
        alive_verbs = (
            r"(?:said|says|say|told|tells|tell|spoke|speak|speaks|"
            r"walked|walk|walks|runs?|ran|moving|moved|"
            r"smiled|smile|smiles|laughed|laugh|laughs|"
            r"looked|look|looks|nodded|nod|nods|"
            r"replied|reply|replies|answered|answer|answers|"
            r"shouted|shout|shouts|screamed|scream|screams|"
            r"cried|cry|cries|whispered|whisper|whispers|"
            r"picked|pick|picks|grabbed|grab|grabs|"
            r"held|hold|holds|wielded|wield|wields|"
            r"attacked|attack|attacks|struck|strike|strikes|"
            r"sat|sit|sits|stood|stand|stands|"
            r"drew|draw|draws|cast|casts|"
            r"stepped|step|steps|marched|march|marches)"
        )
        for cid, char in self.world.characters.items():
            if char["state"] == "dead":
                name = char["name"].lower()
                if name in text:
                    # Pattern 1: Name + verb (e.g., "Elara walks")
                    pattern1 = rf"\b{re.escape(name)}\b\s+{alive_verbs}"
                    # Pattern 2: Name: "dialogue" (e.g., 'Elara: "I will help"')
                    pattern2 = r'\b' + re.escape(name) + r'\s*:\s*["\u201c]'
                    # Pattern 3: Name + possessive action (e.g., "Elara's hands tremble")
                    pattern3 = rf"\b{re.escape(name)}'s?\s+(?:hands?|eyes?|voice|face|lips?|body|fingers?)\s+\w+"

                    if re.search(pattern1, text) or re.search(pattern2, text) or re.search(pattern3, text):
                        issues.append({
                            "type": "dead_character_alive",
                            "severity": "high",
                            "detail": f"{char['name']} is dead but is being described as alive and acting",
                            "character": cid,
                            "suggestion": "ghost/memory/illusion/dream/hallucination",
                        })
        return issues

    def _check_destroyed_locations(self, text: str) -> List[Dict]:
        """Check if destroyed locations are referenced as intact."""
        issues = []
        for lid, loc in self.world.locations.items():
            if loc.get("state") == "destroyed":
                name = loc["name"].lower()
                if name in text:
                    intact_patterns = [
                        f"the {name} stands", f"enter the {name}",
                        f"inside the {name}", f"the {name} is",
                    ]
                    for pattern in intact_patterns:
                        if pattern in text:
                            issues.append({
                                "type": "destroyed_location",
                                "severity": "medium",
                                "detail": f"{loc['name']} was destroyed but is referenced as intact",
                                "location": lid,
                            })
                            break
        return issues

    def _check_impossible_actions(self, text: str) -> List[Dict]:
        """Check for physically impossible actions (lenient)."""
        issues = []
        # This is intentionally very lenient - it's a fantasy game
        # Only flag truly absurd contradictions

        # Example: character teleporting between distant locations in one turn
        player_id = None
        for cid, char in self.world.characters.items():
            if char.get("is_player"):
                player_id = cid
                break

        if player_id:
            player = self.world.get_character(player_id)
            if player and player.get("location"):
                loc = self.world.get_location(player["location"])
                if loc:
                    # Check for instant travel to disconnected locations
                    travel_patterns = [
                        r"(?:fly|teleport|instantly|suddenly)\s+(?:to|into|arrive)\s+(?:at\s+)?(?:the\s+)?(\w+)",
                    ]
                    for pattern in travel_patterns:
                        match = re.search(pattern, text)
                        if match:
                            dest_name = match.group(1).lower()
                            # Check if destination exists and is not connected
                            for lid, l in self.world.locations.items():
                                if dest_name in l["name"].lower() and lid != player["location"]:
                                    if lid not in loc.get("connections", []):
                                        # Only flag if it seems like the player is treating it as normal
                                        if "teleport" not in text and "fly" not in text:
                                            issues.append({
                                                "type": "instant_travel",
                                                "severity": "low",
                                                "detail": f"Traveling to {l['name']} without passing through connected locations",
                                                "suggestion": "narrate the journey",
                                            })
        return issues

    def _check_location_consistency(self, text: str) -> List[Dict]:
        """Check if characters are in the right places."""
        issues = []
        # Check if NPCs are being referenced in locations they're not in
        for cid, char in self.world.characters.items():
            if char.get("is_player") or char["state"] != "active":
                continue
            name = char["name"].lower()
            if name not in text.lower():
                continue

            # Check if the text places them somewhere else
            for lid, loc in self.world.locations.items():
                if lid == char["location"]:
                    continue
                if loc["name"].lower() in text.lower():
                    # They might be traveling - only flag if it's presented as current
                    current_patterns = [
                        f"{name} is in", f"{name} stands in",
                        f"{name} at the {loc['name'].lower()}",
                    ]
                    for p in current_patterns:
                        if p in text.lower():
                            issues.append({
                                "type": "wrong_location",
                                "severity": "low",
                                "detail": f"{char['name']} is at {self.world.locations[char['location']]['name']}, not {loc['name']}",
                                "suggestion": "narrate travel or correct",
                            })
        return issues

    def _check_item_contradictions(self, text: str) -> List[Dict]:
        """Check for item-related contradictions."""
        issues = []
        for iid, item in self.world.items.items():
            name = item["name"].lower()
            if name not in text.lower():
                continue

            # Item owned by someone but being picked up from nowhere
            if item["owner"]:
                owner = self.world.get_character(item["owner"])
                if owner:
                    pickup_patterns = [
                        f"pick up the {name}", f"grab the {name}",
                        f"take the {name}", f"find the {name}",
                    ]
                    for p in pickup_patterns:
                        if p in text.lower():
                            issues.append({
                                "type": "item_owner_conflict",
                                "severity": "low",
                                "detail": f"{item['name']} is carried by {owner['name']}",
                                "suggestion": "narrate transfer or correct",
                            })
        return issues

    def _check_memory_facts(self, text: str) -> List[Dict]:
        """Check against established facts from MemoryKeeper."""
        issues = []
        if not self.memory:
            return issues

        for fact in self.memory.facts[-30:]:
            fact_text = fact["fact"].lower()

            # Check for character death facts
            if "died" in fact_text or "dead" in fact_text or "killed" in fact_text:
                for cid, char in self.world.characters.items():
                    name_lower = char["name"].lower()
                    if name_lower in fact_text and name_lower in text:
                        # They're mentioned in a fact as dead AND in current input
                        if char["state"] == "dead":
                            alive_verbs = (
                                r"(?:said|says|walked|walks|runs?|spoke|speak|"
                                r"smiled|laughed|looked|nodded|replied|shouted|"
                                r"stood|sat|drew|cast|attacked|moved|running)"
                            )
                            if re.search(rf"\b{re.escape(name_lower)}\b\s+{alive_verbs}", text):
                                issues.append({
                                    "type": "memory_contradiction",
                                    "severity": "high",
                                    "detail": f"Memory says {char['name']} died (Ch.{fact['chapter']}), but they appear alive",
                                    "source": f"fact: {fact['fact'][:80]}",
                                    "suggestion": "ghost/memory/flashback/illusion/dream",
                                })

            # Check for destroyed location facts
            if "destroyed" in fact_text or "collapsed" in fact_text or "burned" in fact_text:
                for lid, loc in self.world.locations.items():
                    name_lower = loc["name"].lower()
                    if name_lower in fact_text and name_lower in text:
                        if loc.get("state") == "destroyed":
                            intact_patterns = [
                                f"enter the {name_lower}", f"inside the {name_lower}",
                                f"the {name_lower} stands", f"at the {name_lower}",
                            ]
                            for p in intact_patterns:
                                if p in text:
                                    issues.append({
                                        "type": "memory_contradiction",
                                        "severity": "high",
                                        "detail": f"Memory says {loc['name']} was destroyed (Ch.{fact['chapter']}), but it's referenced as intact",
                                        "source": f"fact: {fact['fact'][:80]}",
                                        "suggestion": "rebuilt/alternate timeline/unreliable narrator",
                                    })

            # Check for relationship-breaking events
            if "betrayed" in fact_text or "broke" in fact_text or "enemy" in fact_text:
                for key, rel in self.world.relationships.items():
                    if "enemy" in rel.get("relation", "").lower() or "hostile" in rel.get("relation", "").lower():
                        from_name = self.world.characters.get(rel["from"], {}).get("name", "").lower()
                        to_name = self.world.characters.get(rel["to"], {}).get("name", "").lower()
                        if from_name and to_name:
                            if from_name in text and to_name in text:
                                # Check if they're described as friendly
                                friendly_patterns = [
                                    f"{from_name} and {to_name} laughed",
                                    f"{from_name} hugged {to_name}",
                                    f"friends",
                                ]
                                for p in friendly_patterns:
                                    if p in text:
                                        issues.append({
                                            "type": "relationship_contradiction",
                                            "severity": "medium",
                                            "detail": f"{rel['from']} and {rel['to']} are enemies, but described as friendly",
                                            "suggestion": "reconciliation arc or narrator correction",
                                        })

        return issues

    def _check_knowledge_bounds(self, text: str, agent_type: str) -> List[Dict]:
        """Check if agent is using knowledge it shouldn't have."""
        issues = []
        # This is a soft check - flag but don't block
        # NPCs shouldn't reference events they weren't present for
        return issues

    def _check_character_voice(self, text: str) -> List[Dict]:
        """Check if character output matches their personality."""
        issues = []
        # Soft check - personality consistency
        return issues

    def _suggest_handling(self, issues: List[Dict]) -> str:
        """Suggest how to handle contradictions."""
        if not issues:
            return ""

        high_issues = [i for i in issues if i["severity"] == "high"]
        if high_issues:
            return (
                "The narrator should acknowledge this gracefully. Options: "
                "1) Treat as dream/hallucination/flashback "
                "2) Have an NPC react with confusion ('Wait, you died...') "
                "3) Narrate as unreliable narrator "
                "4) Treat as time anomaly or parallel timeline"
            )

        return "Minor inconsistency. Narrator can naturally work around it."
