import os
import sys
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import gradio as gr

# OpenAI Agents SDK imports
from agents import Runner, SQLiteSession
from agents.mcp import MCPServerStdio

# Modular source imports
from src.config import VECTORDB_PATH, PORT
from src.agent import create_expert_agent, create_ingester_agent

# Global dictionary to store running MCP server instances
mcp_servers = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize the local Qdrant and Fetch MCP servers
    print("[Lifespan] Initializing local MCP services...")
    
    vectorstore_params = {
        "command": "uvx",
        "args": ["mcp-server-qdrant"],
        "env": {
            "QDRANT_LOCAL_PATH": str(VECTORDB_PATH),
            "COLLECTION_NAME": "knowledge",
            **os.environ
        },
    }

    fetch_params = {
        "command": "uvx",
        "args": ["--with", "mcp<2", "mcp-server-fetch"],
        "env": os.environ
    }

    # Start Vector Store MCP Server
    try:
        print("[Lifespan] Connecting to Qdrant MCP server...")
        vectorstore_mcp = MCPServerStdio(params=vectorstore_params, client_session_timeout_seconds=180)
        await vectorstore_mcp.__aenter__()
        mcp_servers["qdrant"] = vectorstore_mcp
        print("[Lifespan] Qdrant MCP server connected successfully.")
    except Exception as e:
        print(f"[Lifespan] Failed to start Qdrant MCP server: {e}")

    # Start Fetch MCP Server
    try:
        print("[Lifespan] Connecting to Fetch MCP server...")
        fetch_mcp = MCPServerStdio(params=fetch_params, client_session_timeout_seconds=180)
        await fetch_mcp.__aenter__()
        mcp_servers["fetch"] = fetch_mcp
        print("[Lifespan] Fetch MCP server connected successfully.")
    except Exception as e:
        print(f"[Lifespan] Failed to start Fetch MCP server: {e}")

    yield

    # Shutdown: Clean up MCP subprocesses
    print("[Lifespan] Shutting down MCP services...")
    if "qdrant" in mcp_servers:
        try:
            await mcp_servers["qdrant"].__aexit__(None, None, None)
            print("[Lifespan] Qdrant MCP server stopped.")
        except Exception as e:
            print(f"[Lifespan] Error stopping Qdrant MCP: {e}")
            
    if "fetch" in mcp_servers:
        try:
            await mcp_servers["fetch"].__aexit__(None, None, None)
            print("[Lifespan] Fetch MCP server stopped.")
        except Exception as e:
            print(f"[Lifespan] Error stopping Fetch MCP: {e}")

app = FastAPI(lifespan=lifespan)

# API Schemas
class ChatRequest(BaseModel):
    message: str
    session_id: str

class IngestRequest(BaseModel):
    url: str

# API Endpoints
@app.get("/api/stats")
async def stats_endpoint():
    if not VECTORDB_PATH.exists():
        return {"points_count": 0, "status": "Ready (Empty)"}
        
    try:
        from qdrant_client import QdrantClient
        client = QdrantClient(path=str(VECTORDB_PATH))
        collection_name = "knowledge"
        
        if not client.collection_exists(collection_name):
            client.close()
            return {"points_count": 0, "status": "Ready (Empty)"}
            
        info = client.get_collection(collection_name)
        count = info.points_count
        client.close()
        return {"points_count": count, "status": "Ready"}
    except Exception as e:
        print(f"[Stats API] Local read lock active: {e}")
        return {"points_count": "Active", "status": "Connected"}

@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest):
    qdrant_mcp = mcp_servers.get("qdrant")
    fetch_mcp = mcp_servers.get("fetch")
    
    if not qdrant_mcp:
        raise HTTPException(status_code=500, detail="Qdrant MCP server is not running")
    if not fetch_mcp:
        raise HTTPException(status_code=500, detail="Fetch MCP server is not running")

    convo = SQLiteSession(req.session_id)

    try:
        agent = create_expert_agent(qdrant_mcp, fetch_mcp)
        response = await Runner.run(agent, req.message, session=convo)
        return {"output": response.final_output}
    except Exception as e:
        print(f"[Chat API] Execution failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/ingest")
async def ingest_endpoint(req: IngestRequest):
    qdrant_mcp = mcp_servers.get("qdrant")
    fetch_mcp = mcp_servers.get("fetch")
    
    if not qdrant_mcp:
        raise HTTPException(status_code=500, detail="Qdrant MCP server is not running")
    if not fetch_mcp:
        raise HTTPException(status_code=500, detail="Fetch MCP server is not running")

    try:
        agent = create_ingester_agent(qdrant_mcp, fetch_mcp)
        task = f"Fetch the website '{req.url}', extract key facts and knowledge, and save them as unique memories in the vector database. Reply with a short status update."
        response = await Runner.run(agent, task, max_turns=30)
        return {"message": response.final_output}
    except Exception as e:
        print(f"[Ingest API] Ingestion failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Mount a dummy Gradio app to satisfy the Hugging Face Gradio SDK requirement
io = gr.Interface(
    fn=lambda x: f"FastAPI Server is running. Custom UI is served at the root domain.",
    inputs="text",
    outputs="text",
    title="Assam Conservation Policy Expert Backend"
)
app = gr.mount_gradio_app(app, io, path="/gradio-backend")

# Serve static frontend files
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def read_index():
    return FileResponse("static/index.html")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=PORT, reload=True)
