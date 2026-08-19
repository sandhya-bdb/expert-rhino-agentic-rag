---
title: Kaziranga ESZ Tracker
emoji: 🦏
colorFrom: green
colorTo: blue
sdk: gradio
sdk_version: 4.44.1
python_version: 3.12
app_file: app.py
pinned: false
---

<div align="center">

# 🦏 Kaziranga ESZ Policy Expert & Tracker
### *An Agentic RAG System for Conservation and Environmental Policy in Assam, India*

[![Framework: OpenAI Agents](https://img.shields.io/badge/Framework-OpenAI%20Agents%20SDK-007acc?style=for-the-badge&logo=openai&logoColor=white)](https://github.com/openai/openai-agents-python)
[![Protocol: MCP](https://img.shields.io/badge/Protocol-Model%20Context%20(MCP)-ea4335?style=for-the-badge&logo=google&logoColor=white)](https://modelcontextprotocol.io/)
[![VectorDB: Qdrant](https://img.shields.io/badge/VectorDB-Qdrant-ff6b6b?style=for-the-badge&logo=qdrant&logoColor=white)](https://qdrant.tech/)
[![Hosting: Hugging Face](https://img.shields.io/badge/Hosting-Hugging%20Face%20Spaces-ffc107?style=for-the-badge&logo=huggingface&logoColor=black)](https://huggingface.co/spaces)

---

[📖 Project Overview](#-project-overview) • [📸 Interface Details](#-interface-details) • [⚙️ Architecture](#️-architecture) • [📂 Structure](#-project-structure) • [🚀 Get Started](#-getting-started) • [🧪 Evaluation](#-evaluation-suite) • [☁️ Deployment](#-hugging-face-deployment)

</div>

---

## 📖 Project Overview

This platform is a state-of-the-art **Agentic RAG** system designed to support policy makers, journalists, and conservationists in studying environmental policies, wildlife management, and related disputes in Assam, India.

By pairing **pre-ingested official documentation** (Supreme Court rulings, MoEFCC directives, and government stances) with a **real-time web search and crawler engine**, the assistant answers questions with both historic legal accuracy and current news relevance.

> [!NOTE]  
> The system is heavily optimized to address the **Kaziranga Eco-Sensitive Zone (ESZ)** debate, which balances a 1-km localized rationalization stance (Assam Govt) against the 10-km default zone and animal migration corridor protections (Conservationists).

---

## 📸 Interface Details

The web dashboard is served as a custom Single Page Application (SPA) with a modern, glassmorphic dark interface:

*   **⚡ Real-Time Status Monitor**: Displays the number of active memories loaded inside the Qdrant vector database.
*   **📥 Dynamic Ingester**: Allows users to paste any webpage URL to scrape, extract, and index it into the database on-the-fly.
*   **💬 Responsive Chat Room**: Chat interface featuring message animations, suggested prompt chips, and full markdown rendering (with source citations).

---

## ⚙️ Architecture

```mermaid
graph TD
    User([User Interface]) -->|Chat / Ingest| FastAPI[FastAPI App]
    FastAPI -->|Lifecycle| MCPServer[MCP Stdio Subprocess Runner]
    
    subgraph Agentic Loop [OpenAI Agents SDK Core]
        Agent[Expert Agent] -->|Tool Routing| SearchTool[Google News RSS / DDG Search]
        Agent -->|MCP Protocol| Qdrant[Qdrant Vector DB MCP]
        Agent -->|MCP Protocol| Fetch[Fetch Scraper MCP]
    end

    FastAPI -->|Runner.run| Agent
```

---

## 📂 Project Structure

```
expert-rhino-agentic-rag/
├── app.py                     # Main FastAPI server with mounted Gradio wrapper
├── ingest_controversy.py      # Pre-compilation ingestion pipeline
├── pyproject.toml             # UV dependency management configs
├── requirements.txt           # Standard pip dependencies for Hugging Face Spaces
├── Dockerfile                 # Multi-platform deployment container blueprint
├── static/                    # Frontend Dashboard (HTML, CSS, JS)
│   ├── index.html
│   ├── styles.css
│   └── app.js
├── eval/                      # Local testing & LLM-as-a-judge pipeline
│   ├── evaluate.py
│   ├── golden_dataset.json
│   └── results/
└── src/                       # Centralized Code Packages (DRY)
    ├── __init__.py
    ├── config.py              # Environment configuration & DB paths
    ├── tools.py               # Google News RSS parser & search fallbacks
    └── agent.py               # Agent system instructions & scope guardrails
```

---

## 🚀 Getting Started

### 1. Prerequisites
Ensure you have the ultra-fast Python package manager [uv](https://docs.astral.sh/uv/getting-started/installation/) installed.

### 2. Configure Environment
Copy `.env.example` to `.env` and fill in your OpenRouter API Key:
```bash
cp .env.example .env
```
```env
OPENROUTER_API_KEY=your_api_key_here
LLM_MODEL=openrouter/openai/gpt-4o-mini
```

### 3. Install Dependencies
Instantly synchronize all packages in your local virtual environment:
```bash
uv sync
```

### 4. Seed the Database (Ingestion)
Pre-populate the local vector store with the official protected area profiles, legal orders, and stances:
```bash
uv run python ingest_controversy.py
```
This builds the database in the `knowledge/vectordb` directory.

### 5. Launch the App
Start the local FastAPI development server:
```bash
uv run uvicorn app:app --port 8000 --reload
```
Navigate to **`http://localhost:8000`** in your browser.

---

## 🧪 Evaluation Suite

The codebase features a built-in automated testing suite using **LLM-as-a-judge** (GPT-4o-mini) to grade the agent across multiple parameters:

| Metric | Description | Target |
| :--- | :--- | :--- |
| **Faithfulness** | Evaluates if answers are strictly grounded in retrieved database context. | `≥ 0.85` |
| **Relevancy** | Assesses if the generated response directly answers the user's question. | `≥ 0.85` |
| **Stance Balance** | Grades if policy debates fairly present both sides without taking a side. | `1.0 (Balanced)` |
| **Tool Routing** | Verifies if the agent correctly routes between database memory and web search. | `10/10 Correct` |
| **Guardrails** | Confirms out-of-scope queries (e.g. general coding or global GDP) are blocked. | `100% Blocked` |

Run the testing pipeline locally:
```bash
uv run python eval/evaluate.py
```
Raw results are saved as structured JSON cards under `eval/results/`.

---

## ☁️ Hugging Face Deployment

Deploying to **Hugging Face Spaces** gives you access to a secure, permanent **16 GB RAM CPU Basic** virtual machine for free. 

> [!WARNING]  
> Because the agent runs local MCP server processes (Qdrant & Fetch) in the background, trying to run the app on 512 MB platforms (like Render or Koyeb free tiers) will result in OOM (Out Of Memory) crashes (exit code 137). Hugging Face CPU Basic is required.

### Setup Instructions

1.  **Add Payment Method for Identity Verification**  
    Go to **[huggingface.co/settings/billing](https://huggingface.co/settings/billing)** and add a card. This is 100% free and is used solely for spam prevention to unlock the free CPU Basic tier.
2.  **Create a Gradio Space**  
    Create a new Space at **[huggingface.co/new-space](https://huggingface.co/new-space)**. Select the **Gradio** SDK and choose **CPU basic • 2 vCPU • 16 GB • Free** as the hardware.
3.  **Define Secrets**  
    In your Space's **Settings** tab, add `OPENROUTER_API_KEY` to **Variables and secrets**.
4.  **Push the Codebase**  
    Set your Space as the Git remote and push the clean, pre-compiled `hf-deploy` branch:
    ```bash
    git remote set-url hf https://YOUR_USERNAME:YOUR_WRITE_TOKEN@huggingface.co/spaces/YOUR_USERNAME/YOUR_SPACE_NAME
    git push hf hf-deploy:main --force
    ```

Once pushed, Hugging Face will compile the dependencies, boot up the mounted FastAPI endpoints, and serve the custom interface!