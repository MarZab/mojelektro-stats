from __future__ import annotations

from cli._env import load_dotenv

if __name__ == "__main__":
    load_dotenv()

    from cli import app

    app()
