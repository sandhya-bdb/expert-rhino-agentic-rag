import asyncio
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from agents import Runner
from agents.mcp import MCPServerStdio

# Modular source imports
from src.config import VECTORDB_PATH
from src.agent import create_ingester_agent

load_dotenv(override=True)

async def main():
    fetch_params = {
        "command": "uvx",
        "args": ["--with", "mcp<2", "mcp-server-fetch"],
    }

    vectorstore_params = {
        "command": "uvx",
        "args": ["mcp-server-qdrant"],
        "env": {
            "QDRANT_LOCAL_PATH": str(VECTORDB_PATH),
            "COLLECTION_NAME": "knowledge",
        },
    }

    # Foundational URLs
    urls = [
        "https://www.kaziranga-national-park.com/",
        "https://manasnptr.in/",
        "https://pobitorasafari.in/",
        "https://theprint.in/india/himanta-defends-move-to-limit-eco-sensitive-zone-around-kaziranga-to-1-km/2330816/",
        "https://environmentandforest.assam.gov.in/"
    ]

    # Foundational Static Files
    static_files = [
        "knowledge/static_sources/supreme_court_2022_order.txt",
        "knowledge/static_sources/supreme_court_2023_order.txt",
        "knowledge/static_sources/assam_government_esz_stance.txt"
    ]

    print("Starting Ingestion Agent...")
    async with MCPServerStdio(params=fetch_params, client_session_timeout_seconds=180) as fetch_mcp:
        async with MCPServerStdio(params=vectorstore_params, client_session_timeout_seconds=180) as vectorstore_mcp:
            try:
                agent = create_ingester_agent(vectorstore_mcp, fetch_mcp)
            except Exception as e:
                print(f"Error creating Ingester agent: {e}")
                sys.exit(1)

            # 1. Ingest URLs
            for url in urls:
                print(f"\n--- Ingesting URL: {url} ---")
                task = f"Fetch the website '{url}', extract key facts and knowledge, and save them as unique memories in the vector database. Reply with a short status update."
                try:
                    response = await Runner.run(agent, task, max_turns=30)
                    print(f"Status: {response.final_output}")
                except Exception as e:
                    print(f"Failed to ingest URL {url}: {e}")

            # 2. Ingest Static Files
            for file_path in static_files:
                path = Path(file_path)
                if not path.exists():
                    print(f"Warning: Static source file {file_path} not found.")
                    continue
                print(f"\n--- Ingesting static file: {file_path} ---")
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                
                task = f"Add the following document content to the vector database as unique memories. Extract key sections, rulings, stances, and facts:\n\n{content}\n\nReply with a short status update."
                try:
                    response = await Runner.run(agent, task, max_turns=30)
                    print(f"Status: {response.final_output}")
                except Exception as e:
                    print(f"Failed to ingest file {file_path}: {e}")

    print("\nIngestion complete!")

if __name__ == "__main__":
    asyncio.run(main())
