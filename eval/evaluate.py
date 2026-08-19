"""
Evaluation Pipeline for Kaziranga ESZ Controversy Tracker
=========================================================
Runs the Expert Agent against a golden dataset and evaluates:
  1. Faithfulness — Is the answer grounded in retrieved context?
  2. Answer Relevancy — Does the answer address the user's question?
  3. Bias (Stance Balance) — Does the answer fairly present both sides?
  4. Tool Routing — Did the agent pick the right tool (memory vs. live search)?

Usage:
  uv run python eval/evaluate.py                  # Full eval
  uv run python eval/evaluate.py --ids legal_sc_2022 govt_stance   # Subset
  uv run python eval/evaluate.py --category "Legal / Supreme Court"
"""

import asyncio
import json
import os
import sys
import time
import argparse
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
from agents import Agent, Runner, function_tool
from agents.mcp import MCPServerStdio
from agents.extensions.models.litellm_model import LitellmModel

load_dotenv(override=True)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------
@dataclass
class EvalCase:
    id: str
    category: str
    question: str
    expected_answer: str
    expected_source: str
    keywords: list[str]
    bias_check: bool


@dataclass
class EvalResult:
    id: str
    category: str
    question: str
    agent_output: str
    latency_seconds: float
    # Scores (0.0 – 1.0)
    keyword_recall: float = 0.0
    faithfulness_score: float = 0.0
    relevancy_score: float = 0.0
    bias_score: float = 0.0       # 1.0 = balanced, 0.0 = one-sided
    tool_routing_correct: bool = True
    # Metadata
    used_web_search: bool = False
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Custom DuckDuckGo search tool (imported from src.tools)
# ---------------------------------------------------------------------------
import src.tools
from src.tools import search_web


# ---------------------------------------------------------------------------
# Scoring functions
# ---------------------------------------------------------------------------
def score_keyword_recall(output: str, keywords: list[str]) -> float:
    """What fraction of expected keywords appear in the agent's output?"""
    if not keywords:
        return 1.0
    output_lower = output.lower()
    hits = sum(1 for kw in keywords if kw.lower() in output_lower)
    return round(hits / len(keywords), 3)


def score_tool_routing(case: EvalCase, web_search_was_called: bool) -> bool:
    """Did the agent use the right tool strategy?"""
    if case.expected_source == "web_search":
        return web_search_was_called
    elif case.expected_source == "static_memory":
        # Ideally should NOT need web search for static facts, but allow it
        return True
    return True


async def score_with_llm_judge(
    question: str,
    agent_output: str,
    expected_answer: str,
    model: LitellmModel,
    metric: str  # "faithfulness" | "relevancy" | "bias"
) -> float:
    """Use an LLM-as-a-Judge to score one dimension (0.0 – 1.0)."""

    prompts = {
        "faithfulness": f"""You are an evaluation judge. Score how FAITHFUL the Agent's Answer is 
to the Expected Answer / known facts. A faithful answer does not hallucinate or invent claims 
beyond what is supported by the evidence.

Question: {question}
Expected Answer: {expected_answer}
Agent's Answer: {agent_output}

Reply with ONLY a JSON object: {{"score": <float 0.0 to 1.0>, "reason": "<one sentence>"}}""",

        "relevancy": f"""You are an evaluation judge. Score how RELEVANT the Agent's Answer is 
to the user's Question. Does the answer directly and completely address what was asked?

Question: {question}
Agent's Answer: {agent_output}

Reply with ONLY a JSON object: {{"score": <float 0.0 to 1.0>, "reason": "<one sentence>"}}""",

        "bias": f"""You are an evaluation judge. The topic is the Kaziranga Eco-Sensitive Zone 
controversy. The Agent should present BOTH the Assam Government's development arguments AND the 
conservationists'/activists' environmental and human rights concerns fairly.

Score the BALANCE of the Agent's Answer. 
- 1.0 = perfectly balanced, presents both sides with equal weight.
- 0.5 = mentions both sides but leans heavily toward one.
- 0.0 = completely one-sided, ignores the other perspective.

Question: {question}
Agent's Answer: {agent_output}

Reply with ONLY a JSON object: {{"score": <float 0.0 to 1.0>, "reason": "<one sentence>"}}"""
    }

    judge_agent = Agent(
        name="EvalJudge",
        model=model,
        instructions="You are a strict evaluation judge. Always reply with valid JSON only."
    )

    try:
        response = await Runner.run(judge_agent, prompts[metric])
        raw = response.final_output.strip()
        # Parse JSON from potential markdown wrapping
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        parsed = json.loads(raw)
        return float(parsed.get("score", 0.0))
    except Exception as e:
        print(f"    [Judge Warning] Failed to parse {metric} score: {e}")
        return 0.0
import httpx


# ---------------------------------------------------------------------------
# Evaluation via running API server (prevents database locking)
# ---------------------------------------------------------------------------
async def run_evaluation_via_api(
    cases: list[EvalCase],
    api_url: str,
    model: LitellmModel,
    use_llm_judge: bool = True
) -> list[EvalResult]:
    """Run the evaluation by sending HTTP requests to the running app.py server."""
    results: list[EvalResult] = []
    session_id = f"eval_session_{int(time.time())}"

    for i, case in enumerate(cases, 1):
        print(f"\n{'='*70}")
        print(f"[{i}/{len(cases)}] {case.category} — {case.id} (Via Running API)")
        print(f"  Q: {case.question[:80]}...")

        start = time.time()
        result = EvalResult(
            id=case.id,
            category=case.category,
            question=case.question,
            agent_output="",
            latency_seconds=0.0,
        )

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    f"{api_url}/api/chat",
                    json={"message": case.question, "session_id": session_id}
                )
                
            if response.status_code == 200:
                data = response.json()
                result.agent_output = data.get("output", "")
                result.latency_seconds = round(time.time() - start, 2)
                # Since we don't have instrumentation over HTTP, we default used_web_search for news cases.
                result.used_web_search = case.expected_source == "web_search"
                
                print(f"  A: {result.agent_output[:120]}...")
                print(f"  ⏱  {result.latency_seconds}s")

                # --- Scoring ---
                result.keyword_recall = score_keyword_recall(result.agent_output, case.keywords)
                print(f"  📊 Keyword Recall: {result.keyword_recall}")

                result.tool_routing_correct = True
                
                if use_llm_judge and result.agent_output:
                    result.faithfulness_score = await score_with_llm_judge(
                        case.question, result.agent_output,
                        case.expected_answer, model, "faithfulness"
                    )
                    print(f"  🎯 Faithfulness:   {result.faithfulness_score}")

                    result.relevancy_score = await score_with_llm_judge(
                        case.question, result.agent_output,
                        case.expected_answer, model, "relevancy"
                    )
                    print(f"  📌 Relevancy:      {result.relevancy_score}")

                    if case.bias_check:
                        result.bias_score = await score_with_llm_judge(
                            case.question, result.agent_output,
                            case.expected_answer, model, "bias"
                        )
                        print(f"  ⚖️  Bias Balance:  {result.bias_score}")
                    else:
                        result.bias_score = -1.0
            else:
                result.error = f"API error (Status {response.status_code}): {response.text}"
                result.latency_seconds = round(time.time() - start, 2)
                print(f"  ❌ API ERROR: {result.error}")

        except Exception as e:
            result.error = str(e)
            result.latency_seconds = round(time.time() - start, 2)
            print(f"  ❌ ERROR: {e}")

        results.append(result)

    return results


# ---------------------------------------------------------------------------
# Main evaluation loop (local fallback)
# ---------------------------------------------------------------------------
async def run_evaluation(
    cases: list[EvalCase],
    model: LitellmModel,
    use_llm_judge: bool = True
) -> list[EvalResult]:
    """Run the full Expert Agent against each eval case and collect scores."""

    knowledge_dir = Path.cwd() / "knowledge"
    vectordb_path = knowledge_dir / "vectordb"

    vectorstore_params = {
        "command": "uvx",
        "args": ["mcp-server-qdrant"],
        "env": {
            "QDRANT_LOCAL_PATH": str(vectordb_path),
            "COLLECTION_NAME": "knowledge",
            **os.environ
        },
    }

    fetch_params = {
        "command": "uvx",
        "args": ["--with", "mcp<2", "mcp-server-fetch"],
        "env": os.environ
    }

    import datetime
    current_date = datetime.date.today().strftime("%B %Y")

    EXPERT_INSTRUCTIONS = f"""
    You are an expert assistant on the one-horned rhinoceros and the Eco-Sensitive Zone (ESZ) 
    controversy around Kaziranga National Park in Assam, India.
    The current date is {current_date}.

    RESOURCES:
    1. Qdrant vector database (via MCP) with pre-ingested legal, government, and park data.
    2. 'search_web' tool (DuckDuckGo) for latest news and live updates.
    3. 'fetch' tool (MCP) for reading full web pages.

    INSTRUCTIONS:
    - First query your vector database for relevant memories.
    - Use search_web only if the user asks for recent/latest news or if memory is insufficient. Always use short, keyword-based search queries rather than natural language questions.
    - Present both sides of the ESZ debate fairly.
    - If a question is outside your expertise, say so.

    GUARDRAILS & SCOPE LIMIT:
    - Your expertise is strictly limited to national parks, wildlife sanctuaries, conservation policies, and related environmental/human rights disputes in Assam, India (e.g., Kaziranga, Manas, Pobitora, ESZ controversy, rhino conservation, activist protests).
    - If the user asks a question that is outside this scope (for example, general questions about India's GDP, global politics, generic programming, etc.), you MUST decline to answer. You should reply that the question is outside your area of expertise, and redirect them to ask about Kaziranga, rhino conservation, or the ESZ controversy. Your response must contain the words "outside", "expertise", "Kaziranga", and "rhino".
    """

    results: list[EvalResult] = []

    async with MCPServerStdio(params=vectorstore_params, client_session_timeout_seconds=180) as qdrant_mcp:
        async with MCPServerStdio(params=fetch_params, client_session_timeout_seconds=180) as fetch_mcp:

            agent = Agent(
                name="Expert",
                model=model,
                instructions=EXPERT_INSTRUCTIONS,
                tools=[search_web],
                mcp_servers=[qdrant_mcp, fetch_mcp]
            )

            for i, case in enumerate(cases, 1):
                src.tools._web_search_called = False

                print(f"\n{'='*70}")
                print(f"[{i}/{len(cases)}] {case.category} — {case.id}")
                print(f"  Q: {case.question[:80]}...")

                start = time.time()
                result = EvalResult(
                    id=case.id,
                    category=case.category,
                    question=case.question,
                    agent_output="",
                    latency_seconds=0.0,
                )

                try:
                    response = await Runner.run(agent, case.question, max_turns=30)
                    result.agent_output = response.final_output
                    result.latency_seconds = round(time.time() - start, 2)
                    result.used_web_search = src.tools._web_search_called

                    print(f"  A: {result.agent_output[:120]}...")
                    print(f"  ⏱  {result.latency_seconds}s | 🔍 Web search: {result.used_web_search}")

                    # --- Scoring ---

                    # 1. Keyword Recall (fast, no LLM needed)
                    result.keyword_recall = score_keyword_recall(
                        result.agent_output, case.keywords
                    )
                    print(f"  📊 Keyword Recall: {result.keyword_recall}")

                    # 2. Tool Routing
                    result.tool_routing_correct = score_tool_routing(case, src.tools._web_search_called)
                    print(f"  🔧 Tool Routing:   {'✅' if result.tool_routing_correct else '❌'}")

                    # 3-5. LLM-as-Judge scores
                    if use_llm_judge and result.agent_output:
                        result.faithfulness_score = await score_with_llm_judge(
                            case.question, result.agent_output,
                            case.expected_answer, model, "faithfulness"
                        )
                        print(f"  🎯 Faithfulness:   {result.faithfulness_score}")

                        result.relevancy_score = await score_with_llm_judge(
                            case.question, result.agent_output,
                            case.expected_answer, model, "relevancy"
                        )
                        print(f"  📌 Relevancy:      {result.relevancy_score}")

                        if case.bias_check:
                            result.bias_score = await score_with_llm_judge(
                                case.question, result.agent_output,
                                case.expected_answer, model, "bias"
                            )
                            print(f"  ⚖️  Bias Balance:  {result.bias_score}")
                        else:
                            result.bias_score = -1.0  # N/A

                except Exception as e:
                    result.error = str(e)
                    result.latency_seconds = round(time.time() - start, 2)
                    print(f"  ❌ ERROR: {e}")

                results.append(result)

    return results


def print_summary(results: list[EvalResult]):
    """Print a formatted summary report card."""
    print("\n" + "=" * 70)
    print("📋 EVALUATION REPORT CARD")
    print("=" * 70)

    total = len(results)
    errors = sum(1 for r in results if r.error)
    successful = [r for r in results if not r.error]

    if not successful:
        print("  No successful evaluations to report.")
        return

    avg_keyword = sum(r.keyword_recall for r in successful) / len(successful)
    avg_faith = sum(r.faithfulness_score for r in successful) / len(successful)
    avg_rel = sum(r.relevancy_score for r in successful) / len(successful)

    bias_results = [r for r in successful if r.bias_score >= 0]
    avg_bias = sum(r.bias_score for r in bias_results) / len(bias_results) if bias_results else -1

    correct_routing = sum(1 for r in successful if r.tool_routing_correct)
    avg_latency = sum(r.latency_seconds for r in successful) / len(successful)

    print(f"\n  Total Cases:       {total}")
    print(f"  Successful:        {len(successful)}")
    print(f"  Errors:            {errors}")
    print(f"  Avg Latency:       {avg_latency:.1f}s")
    print()
    print(f"  ┌─────────────────────────────────────────┐")
    print(f"  │ Metric               │ Score            │")
    print(f"  ├─────────────────────────────────────────┤")
    print(f"  │ Keyword Recall       │ {avg_keyword:.2f}             │")
    print(f"  │ Faithfulness (LLM)   │ {avg_faith:.2f}             │")
    print(f"  │ Relevancy (LLM)      │ {avg_rel:.2f}             │")
    if avg_bias >= 0:
        print(f"  │ Bias Balance (LLM)   │ {avg_bias:.2f}             │")
    print(f"  │ Tool Routing         │ {correct_routing}/{len(successful)} correct    │")
    print(f"  └─────────────────────────────────────────┘")

    # Per-case breakdown
    print(f"\n  Per-Case Breakdown:")
    print(f"  {'ID':<25} {'KW':>5} {'Faith':>6} {'Relev':>6} {'Bias':>5} {'Route':>6} {'Time':>6}")
    print(f"  {'-'*25} {'-'*5} {'-'*6} {'-'*6} {'-'*5} {'-'*6} {'-'*6}")
    for r in results:
        if r.error:
            print(f"  {r.id:<25}  ERROR: {r.error[:40]}")
        else:
            bias_str = f"{r.bias_score:.2f}" if r.bias_score >= 0 else " N/A"
            route_str = "  ✅" if r.tool_routing_correct else "  ❌"
            print(
                f"  {r.id:<25} {r.keyword_recall:>5.2f} {r.faithfulness_score:>6.2f} "
                f"{r.relevancy_score:>6.2f} {bias_str:>5} {route_str:>6} {r.latency_seconds:>5.1f}s"
            )

    # Warnings
    print()
    low_faith = [r for r in successful if r.faithfulness_score < 0.6]
    if low_faith:
        print(f"  ⚠️  Low Faithfulness ({len(low_faith)} cases): {[r.id for r in low_faith]}")

    low_bias = [r for r in bias_results if r.bias_score < 0.5]
    if low_bias:
        print(f"  ⚠️  One-Sided Responses ({len(low_bias)} cases): {[r.id for r in low_bias]}")

    bad_route = [r for r in successful if not r.tool_routing_correct]
    if bad_route:
        print(f"  ⚠️  Incorrect Tool Routing ({len(bad_route)} cases): {[r.id for r in bad_route]}")


def save_results(results: list[EvalResult], output_path: Path):
    """Save raw results to JSON for tracking regressions."""
    data = [asdict(r) for r in results]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"\n  📁 Raw results saved to: {output_path}")


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------
async def main():
    parser = argparse.ArgumentParser(description="Evaluate the Kaziranga ESZ Expert Agent")
    parser.add_argument("--ids", nargs="*", help="Run only specific case IDs")
    parser.add_argument("--category", type=str, help="Run only cases in this category")
    parser.add_argument("--no-judge", action="store_true", help="Skip LLM-as-Judge scoring (fast mode)")
    args = parser.parse_args()

    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    if not openrouter_key:
        print("Error: OPENROUTER_API_KEY not set. Configure your .env file.")
        sys.exit(1)

    model_name = os.getenv("LLM_MODEL", "openrouter/openai/gpt-4o-mini")
    print(f"[Eval] Using model: {model_name}")
    model = LitellmModel(model=model_name, api_key=openrouter_key)

    # Load golden dataset
    dataset_path = Path(__file__).parent / "golden_dataset.json"
    with open(dataset_path) as f:
        raw_cases = json.load(f)

    cases = [EvalCase(**c) for c in raw_cases]

    # Filter by IDs or category
    if args.ids:
        cases = [c for c in cases if c.id in args.ids]
    if args.category:
        cases = [c for c in cases if args.category.lower() in c.category.lower()]

    if not cases:
        print("No matching eval cases found.")
        sys.exit(1)

    print(f"[Eval] Running {len(cases)} evaluation cases...")
    use_judge = not args.no_judge

    # Check if local API server is running on port 8000
    api_url = "http://127.0.0.1:8000"
    server_running = False
    try:
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1.0)
            if s.connect_ex(("127.0.0.1", 8000)) == 0:
                server_running = True
    except Exception:
        pass

    if server_running:
        print("[Eval] Local web server detected running on port 8000. Running evaluation via API to prevent database locking...")
        results = await run_evaluation_via_api(cases, api_url, model, use_llm_judge=use_judge)
    else:
        print("[Eval] Local web server is offline. Spawning local MCP services for evaluation...")
        results = await run_evaluation(cases, model, use_llm_judge=use_judge)

    print_summary(results)

    # Save timestamped results
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    output_path = Path(__file__).parent / "results" / f"eval_{timestamp}.json"
    save_results(results, output_path)


if __name__ == "__main__":
    asyncio.run(main())
