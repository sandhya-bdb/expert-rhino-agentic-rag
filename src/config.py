import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(override=True)

WORKSPACE_DIR = Path.cwd()
KNOWLEDGE_DIR = WORKSPACE_DIR / "knowledge"
VECTORDB_PATH = KNOWLEDGE_DIR / "vectordb"

KNOWLEDGE_DIR.mkdir(exist_ok=True)

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
LLM_MODEL = os.getenv("LLM_MODEL", "openrouter/openai/gpt-4o-mini")
PORT = int(os.getenv("PORT", 8000))
