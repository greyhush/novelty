# Novelty

Open-world text adventure game. Player writes the story. LLM generates the world in real-time.

You are both the **player** and the **author**. Write dialogue, describe actions, or take over as narrator. The AI handles everything else — NPC reactions, world consistency, plot twists.

## Architecture

Four cooperating agents:

```
Player Input
     ↓
┌──────────┐
│  Router   │ ← Interprets: dialogue? action? narration? command?
└────┬─────┘
     ↓
┌──────────────┐     ┌──────────────┐
│ Character    │ ←→  │  Narrator    │
│ Actor (NPC)  │     │  (Director)  │
└──────┬───────┘     └──────┬───────┘
       ↓                    ↓
┌──────────────┐     ┌──────────────┐
│   Memory     │ ←→  │ World State  │
│   Keeper     │     │  (JSON)      │
└──────────────┘     └──────────────┘
```

- **World Builder** — Generates lore, characters, locations at game start
- **Character Actor** — NPCs think and respond in-character
- **Narrator** — Drives plot, describes environments, manages pacing
- **Memory Keeper** — Tracks events, prevents contradictions

## Install

```bash
pip install -e .
```

## Quick Start

```bash
# Configure your LLM
novelty setup

# Play
novelty play

# Load a save
novelty play --load my_save

# List saves
novelty saves
```

## How to Play

You write freely. The game interprets what you mean:

| You write | What happens |
|-----------|-------------|
| `"Hello there!"` | Your character speaks |
| `I walk to the door and open it` | Your character acts |
| `The sky darkens suddenly` | You narrate as author (scene change) |
| `Aria: "I don't trust him"` | You write another character's line |
| `/help` | Show commands |
| `/suggest` | Get story direction ideas |
| `/add character A grumpy dwarf` | Add new character to world |

### Player = Author + Character

You have two modes:
- **Character mode**: "I pick up the sword and charge at the dragon"
- **Author mode**: "Three days later, a letter arrives at the castle"

The LLM adapts to whichever role you're playing.

## Commands

| Command | Description |
|---------|-------------|
| `/help` | Show commands |
| `/save [name]` | Save game |
| `/load [name]` | Load game |
| `/world` | Show world state |
| `/chars` | Show characters |
| `/locations` | Show locations |
| `/items` | Show items |
| `/add <type> <desc>` | Add character/location/item |
| `/suggest` | Get story direction suggestions |
| `/summary` | Story summary |
| `/chapter` | Advance to next chapter |
| `/flag [key] [val]` | Set/view story flags |
| `/relate A B relation` | Set character relationship |
| `/quit` | Exit (auto-saves) |

## Supported LLMs

| Provider | Examples |
|----------|---------|
| Ollama (local) | Any Ollama model |
| OpenAI-compatible | GPT-4, DeepSeek, vLLM |
| MiMo | mimo-v2.5-pro |

## Storage

- Config: `~/.novelty/config.json`
- Saves: `~/.novelty/saves/<name>.json`

## License

MIT
