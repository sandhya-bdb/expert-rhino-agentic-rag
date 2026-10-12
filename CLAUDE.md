# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Agentic RAG assistant for Assam conservation policy (Kaziranga, Manas, Pobitora), focused on the Kaziranga Eco-Sensitive Zone (ESZ) dispute. Built on the OpenAI Agents SDK, with LLM calls going through LiteLLM to OpenRouter. Deployed as a Docker image on Hugging Face Spaces.

## Commands

Run every command from the repo root. `src/config.py` resolves `knowledge/` from `Path.cwd()`.

```bash
uv sync                                          # install deps
cp .env.example .env                             # needs OPENROUTER_API_KEY; LLM_MODEL is optional
uv run uvicorn app:app --port 8000 --reload      # run app (UI at /)
uv run python ingest_controversy.py              # rebuild the vector DB from seed URLs + knowledge/static_sources/

uv run python eval/evaluate.py                   # full eval suite (LLM judge)
uv run python eval/evaluate.py --ids legal_sc_2022 govt_stance   # single/specific cases
uv run python eval/evaluate.py --category "Legal / Supreme Court"
uv run python eval/evaluate.py --no-judge        # skip LLM judge (fast)

docker build -t kaziranga-expert . && docker run -p 7860:7860 --env-file .env kaziranga-expert
```

There is no unit test suite, linter or formatter config. The evaluation suite in `eval/` is the only regression check, and it makes real LLM and network calls.

## Architecture

- **Agents** (`src/agent.py`): two agents share one `LitellmModel` factory.
  - **Expert** answers questions. It has the `search_web` function tool and both MCP servers.
  - **Ingester** fetches a URL and writes the extracted facts into Qdrant.
  - System prompts live in `get_expert_instructions()` and `get_ingester_instructions()`. The Expert prompt carries the routing policy (vector memory first, web search on a miss or for recent news), the both-sides balance requirement and the scope guardrail.
- **MCP servers** are stdio subprocesses launched with `uvx`:
  - `mcp-server-qdrant` uses local file mode at `knowledge/vectordb/`, collection `knowledge`.
  - `mcp-server-fetch` is pinned with `--with "mcp<2"`.
  - In `app.py` they start once in the FastAPI `lifespan`, are kept in the module-level `mcp_servers` dict, and are shared by every request. A new `Agent` is built per request. `ingest_controversy.py` and the direct path in `eval/evaluate.py` start their own copies of the servers.
- **Web search** (`src/tools.py`) tries Google News RSS (India edition) first, then DuckDuckGo news, then DuckDuckGo text, with retries. On failure it returns an error string rather than raising, so the agent can recover. It also sets the module-global flag `_web_search_called`, which the evals read to score tool routing.
- **HTTP API** (`app.py`): `/api/chat` runs the Expert with `SQLiteSession(session_id)`, `/api/ingest` runs the Ingester with `max_turns=30`, and `/api/stats` reads the Qdrant point count directly with `qdrant_client`. The real UI is the plain HTML/JS SPA in `static/`. The Gradio app mounted at `/gradio-backend` exists only to satisfy the Hugging Face Gradio SDK requirement.

## Gotchas

- **Qdrant local mode allows only one process to open the DB.** While the app is running, `ingest_controversy.py` or a direct eval run will hit a lock conflict. `eval/evaluate.py` detects a server on port 8000 and sends its questions through `/api/chat` instead. In that mode it cannot read `_web_search_called`, so it cannot score tool routing. `/api/stats` falls back to `"Active"` when the DB is locked.
- **Eval coupling:** the guardrail eval case expects the decline message to contain the words "outside", "expertise", "Kaziranga" and "rhino", and the Expert prompt requires them explicitly. Keep the prompt, `eval/golden_dataset.json` (keywords, `expected_source`, `bias_check`) and the scorers in `eval/evaluate.py` consistent when changing any of them. Run results are written to `eval/results/` with timestamps.
- **Two dependency lists:** `pyproject.toml`/`uv.lock` are used for local development and Docker. `requirements.txt` is a separate, smaller list for Hugging Face Spaces (Gradio pinned `<5`). Update both when adding a runtime dependency.
- **Dockerfile:** the image copies only `app.py`, `styles.py`, `src/`, `static/` and `knowledge/`, and it pre-caches both MCP servers. New top-level modules need a `COPY` line. The container listens on `PORT` (7860 on HF Spaces).
- The pre-built vector DB in `knowledge/vectordb/` is committed and shipped in the image.
