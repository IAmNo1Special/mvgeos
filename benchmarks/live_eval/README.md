# Live Evaluation Harness — Seeker Protocol vs Baseline

This directory contains a **live-model evaluation** that runs real tasks against OpenRouter to measure the Seeker Protocol's impact on:
- Task success rate
- Mana (token) consumption
- Turn count
- Wall-clock latency
- Tool selection quality

## Prerequisites

1. **OpenRouter API key** — Required for live model calls
   - Set `OPENROUTER_API_KEY` environment variable, OR
   - Create `~/.agents/.mvgeos/auth/openrouter.json`:
     ```json
     {"api_key": "sk-or-v1-..."}
     ```

2. **Model access** — The default model (`nvidia/nemotron-3-ultra-550b-a55b:free`) must be available on your OpenRouter account.

## Quick Start

```bash
# From mvgeos repo root
cd benchmarks/live_eval
uv run python runner.py
```

## Configuration

Environment variables:
| Variable | Default | Description |
|----------|---------|-------------|
| `MVGEOS_EVAL_MODEL` | `nvidia/nemotron-3-ultra-550b-a55b:free` | Model ID |
| `MVGEOS_EVAL_TEMPERATURE` | `0.0` | Sampling temperature |
| `MVGEOS_EVAL_MAX_TOKENS` | `4096` | Max output tokens per turn |
| `MVGEOS_EVAL_CONTEMPLATION` | `medium` | Reasoning effort level |
| `MVGEOS_EVAL_MAX_TURNS` | `20` | Max turns per task |
| `MVGEOS_EVAL_TIMEOUT` | `120` | Per-task timeout (seconds) |

## Task Suite

10 tasks across 4 categories:
- **file_ops** (5): read, write, list, modify, recursive search
- **code_search** (3): function lookup, class method, grep pattern
- **synthesis** (1): multi-file data aggregation
- **json_manipulation** (1): parse and query JSON

Each task has:
- Deterministic file setup
- Ground truth for automated success checking
- Clear success criteria

## Modes Compared

| Mode | Description |
|------|-------------|
| **baseline** | All 56 tools (6 real + 50 distractors) visible every turn |
| **seeker** | 7 meta/heal tools visible; real tools discovered via `tool_search` |

## Metrics Collected

Per task × mode:
- `success` (bool) — ground truth match
- `turns` — conversation turns
- `mana_used` — cumulative tokens
- `wall_time_seconds` — real elapsed time
- `tools_called` — unique tool names invoked
- `tool_call_count` — total tool invocations
- `final_output` — model's response (truncated)

## Output

Results saved as `results_<timestamp>.json` with full detail.
Console prints per-task progress and a summary table.

## Free-tier notes (learned 2026-09-14)

- Verify availability live: `GET https://openrouter.ai/api/v1/models`,
  filter `id.endswith(":free")`, zero pricing, `tools` in
  `supported_parameters`. Catalog churns fast — `z-ai/glm-5.2:free` and
  `minimax/minimax-m3:free` were gone the same week guides recommended them.
- Current coding pick: `poolside/laguna-s-2.1:free` (purpose-built coding
  agent, 262K context, tools). Fallbacks: `nvidia/nemotron-3.5-lightning:free`
  (1M context), `cohere/north-mini-code:free` (mini code model).
- Do NOT use `openrouter/free` for benchmarking: it routes to a random free
  model per request, breaking baseline-vs-seeker comparability.
- Quota is account-wide per day (~50 with no credits; up to ~200; $10 credit
  unlocks 1000/day). A full 10-task x 2-mode run costs ~60-160 requests —
  budget a full day's quota. Override per run with `MVGEOS_EVAL_MODEL`.
- Free endpoints may log prompts (data policy). Never run proprietary code.
- Always pass `provider_name="openrouter"` (the default): it forces the
  OpenRouter Realm factory even for model IDs the local catalog lacks.

## Hermetic vs Live

This evaluation is **not** part of the CI suite (`TESTING.md` §2). It:
- Requires network and credentials
- Has non-deterministic model output
- Costs real API credits
- Measures *intelligence* (task success) not just *mechanics* (wire bytes)

Run locally or in a controlled environment; exclude from automated pipelines.

## Interpreting Results

A successful Seeker evaluation shows:
- **Success rate** ≥ baseline (Seeker finds the right tools)
- **Mana/turn** significantly lower (fewer tools in context)
- **Latency** comparable or better (smaller context = faster inference)
- **Tool precision** higher (correct tool selected via discovery)

If Seeker underperforms on success rate, investigate:
- `tool_search` NLT selector quality
- Discovery latency (extra turn cost)
- Task suitability (some tasks need no discovery)