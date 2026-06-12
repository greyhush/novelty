#!/usr/bin/env python3
"""novelty CLI - Play or create interactive fiction powered by LLM."""

import argparse
import json
import sys
from pathlib import Path


def load_config() -> dict:
    config_path = Path.home() / ".novelty" / "config.json"
    if config_path.exists():
        return json.loads(config_path.read_text())
    return {}


def save_config(config: dict):
    config_path = Path.home() / ".novelty" / "config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config, indent=2))


def cmd_setup(args):
    """Configure LLM backend."""
    config = load_config()

    print("=== Novelty Setup ===\n")
    print("Choose LLM provider:")
    print("  1. Ollama (local)")
    print("  2. OpenAI-compatible API")
    print("  3. MiMo (Xiaomi)")

    choice = input("\nChoice [1]: ").strip() or "1"

    if choice == "1":
        provider = "ollama"
        base_url = input("Ollama URL [http://localhost:11434]: ").strip() or "http://localhost:11434"
        model = input("Model name: ").strip()
        api_key = ""
    elif choice == "3":
        provider = "mimo"
        base_url = "https://api.mimo.xiaomi.com/v1"
        api_key = input("API key: ").strip()
        model = input("Model [mimo-v2.5-pro]: ").strip() or "mimo-v2.5-pro"
    else:
        provider = "openai"
        base_url = input("API URL [https://api.openai.com/v1]: ").strip() or "https://api.openai.com/v1"
        api_key = input("API key: ").strip()
        model = input("Model: ").strip()

    config["llm"] = {
        "provider": provider,
        "model": model,
        "base_url": base_url,
        "api_key": api_key,
    }
    save_config(config)
    print(f"\nConfigured: {provider}/{model}")
    print("Now run: novelty play")


def cmd_play(args):
    """Start or continue a game."""
    from novelty.llm import LLMClient
    from novelty.engine import GameEngine

    config = load_config()
    llm_config = config.get("llm", {})

    if not llm_config.get("model"):
        print("No LLM configured. Run: novelty setup")
        return

    llm = LLMClient.from_dict(llm_config)
    engine = GameEngine(llm)

    # Load or create
    if args.load:
        result = engine.process_input(f"/load {args.load}")
        print(result)
    else:
        print("\n" + "="*50)
        print("  N O V E L T Y")
        print("  Open-world interactive fiction")
        print("="*50 + "\n")

        print("Choose mode:")
        print("  1. New story (AI generates world)")
        print("  2. Load saved game")

        mode = input("\nChoice [1]: ").strip() or "1"

        if mode == "2":
            saves_dir = Path.home() / ".novelty" / "saves"
            saves = list(saves_dir.glob("*.json")) if saves_dir.exists() else []
            if not saves:
                print("No saves found. Starting new game.")
                mode = "1"
            else:
                print("\nAvailable saves:")
                for s in sorted(saves):
                    print(f"  • {s.stem}")
                name = input("\nSave name: ").strip()
                result = engine.process_input(f"/load {name}")
                print(result)

        if mode == "1":
            print("\n--- World Creation ---")
            print("Describe your story's genre and setting.")
            print("Examples:")
            print('  "Cyberpunk noir detective story in a rain-soaked megacity"')
            print('  "Fantasy kingdom on the brink of war, ancient magic awakening"')
            print('  "Slice-of-life drama in a small Japanese coastal town"')
            print('  "Space opera aboard a generation ship heading to Alpha Centauri"')

            genre = input("\nGenre/Setting: ").strip()
            if not genre:
                genre = "Fantasy adventure"

            player_name = input("Your character's name [Hero]: ").strip() or "Hero"

            print("\nGenerating world...")
            intro = engine.new_game(genre, player_name=player_name)
            print(f"\n{intro}")

    # Game loop
    print("\n" + "-"*50)
    engine.running = True

    try:
        while engine.running:
            try:
                user_input = input("\n> ").strip()
            except EOFError:
                break

            if not user_input:
                continue

            response = engine.process_input(user_input)
            if response:
                print(f"\n{response}")

    except KeyboardInterrupt:
        print("\n\nGame interrupted. Auto-saving...")
        engine.process_input("/save autosave")

    print("\nThanks for playing Novelty!")


def cmd_saves(args):
    """List saved games."""
    saves_dir = Path.home() / ".novelty" / "saves"
    saves = list(saves_dir.glob("*.json")) if saves_dir.exists() else []
    if not saves:
        print("No saves found.")
        return
    print("Saved games:")
    for s in sorted(saves):
        size = s.stat().st_size
        print(f"  • {s.stem} ({size/1024:.1f} KB)")


def main():
    parser = argparse.ArgumentParser(
        prog="novelty",
        description="Novelty - Open-world text adventure powered by LLM"
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("setup", help="Configure LLM backend")

    p = sub.add_parser("play", help="Start or continue a game")
    p.add_argument("--load", "-l", default=None, help="Load a saved game")

    sub.add_parser("saves", help="List saved games")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    {"setup": cmd_setup, "play": cmd_play, "saves": cmd_saves}[args.command](args)


if __name__ == "__main__":
    main()
