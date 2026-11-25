# Two-provider cost tracker

Assignment 1 · Agentic AI Developer · Phase 1 Foundations (Track A)

A small Python command-line tool that sends one unchanged prompt to Google Gemini and Groq. It prints both replies, compares API-reported token usage, elapsed seconds and estimated cost, and writes `results.json` for the latest successful run.

## Setup

You need Python 3.10+ and [uv](https://docs.astral.sh/uv/getting-started/installation/).

1. Clone your repository (or extract the project ZIP) and open a terminal in the directory containing `tracker.py`.
2. Protect secrets **before obtaining keys**: commit `.gitignore` and `.env.example` first. The former ignores `.env` and local variants; the latter contains placeholders only.
3. Get a free-tier API key for each provider:
   - Gemini: <https://aistudio.google.com/apikey>
   - Groq: <https://console.groq.com/keys>
4. Copy the example configuration:

   ```bash
   cp .env.example .env
   ```

   On Windows PowerShell: `Copy-Item .env.example .env`. Open `.env` in your editor and replace the two key placeholders. Keep the keys in this local file only. Use free-tier accounts/projects if you want to avoid actual charges.
5. Install dependencies (uv will also do this on the first run):

   ```bash
   uv sync
   ```

## Run

```bash
uv run tracker.py "Explain artificial intelligence in one sentence."
uv run tracker.py "Write a two-line poem about rain."
uv run tracker.py "Explain Python lists in three short points."
```

The first argument must be the entire prompt in quotes. Each execution sends the same prompt to both APIs. Inspect `results.json` after each run, because the next successful execution replaces it. The file is generated locally and ignored by Git because replies can contain private information. The TA's own test run generates it; there is no fabricated output file in this repository.

### Sample terminal output

Illustrative example only (synthetic replies, counts and timing, not a live API result). Actual replies, usage and latency will vary.

```text
--- GEMINI (gemini-3.1-flash-lite) ---
Artificial intelligence is technology that enables computers to perform tasks that normally require human intelligence.

--- GROQ (openai/gpt-oss-20b) ---
Artificial intelligence is the ability of machines to learn, reason, and perform tasks typically requiring human intelligence.

Provider comparison (standard paid-tier estimate)
Provider    Input tokens  Output tokens    Seconds     Cost (USD)
-----------------------------------------------------------------
gemini                10             25      0.820    0.000040000
groq                  30             40      0.410    0.000014250
Eligible free-tier calls cost $0; estimates are not actual bills.

Saved results.json
```

### JSON structure

`results.json` is a list of two objects (`gemini`, then `groq`). Each contains exactly the eight assignment fields: `provider`, `model`, `reply`, `input_tokens`, `output_tokens`, `input_price_per_m`, `output_price_per_m`, and `cost_usd`. Timing is shown in the terminal as requested, not added to the specified JSON schema.

## Models and pricing

The default models are configurable in `.env` through `GEMINI_MODEL` and `GROQ_MODEL`. If those variables are absent, the script uses the same defaults so a TA can supply only keys as environment variables. `GOOGLE_API_KEY` is also accepted as a fallback for Gemini.

Standard paid-tier text rates (USD per million tokens), checked November 24, 2026:

| Provider | Default model | Input / 1M | Output / 1M |
| --- | --- | ---: | ---: |
| Gemini | `gemini-3.1-flash-lite` | $0.25 | $1.50 |
| Groq | `openai/gpt-oss-20b` | $0.075 | $0.30 |

Sources: [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing), [Groq models and pricing](https://console.groq.com/docs/models), [Groq free-tier limits](https://console.groq.com/docs/rate-limits).

Both defaults are listed for free-tier use, subject to eligibility and rate limits. `cost_usd` represents what the reported tokens would cost at the standard paid text rates, not an actual invoice. Eligible free-tier requests cost zero. This keeps the comparison meaningful even when neither request incurs a real charge. No cache discounts, tool charges or special pricing tiers are modeled.

```text
cost_usd = (input_tokens * input_price_per_m
            + output_tokens * output_price_per_m) / 1_000_000
```

Gemini reads `usage_metadata.prompt_token_count` and `candidates_token_count` plus any reported `thoughts_token_count` (thinking tokens are priced as output). Groq reads `usage.prompt_tokens` and `usage.completion_tokens`. The program rejects missing usage instead of counting words. Calls are sequential; the elapsed time measures the complete client call, including client setup and cleanup, and is not a pure server inference benchmark.

To switch models, edit `.env`. `tracker.py` includes a small table of alternative models and rates. For other models, set both price overrides for the relevant provider (see `.env.example`) using the current official pricing page. Unknown models without a price pair fail with a clear configuration error rather than silently using the wrong rates.

## Error handling and tests

Missing keys or invalid price configurations produce an explanatory error before any API call. API errors show the provider and error type/status without printing raw SDK error messages or keys. An unsuccessful run does not overwrite the last successful `results.json`.

Run the offline tests:

```bash
uv run python -m unittest discover -s tests -v
```

The tests cover cost arithmetic, key validation, price validation, missing usage, identical prompts, and JSON output using mocked provider responses. They do not prove that real API calls work. Run all three prompts above with your own keys to verify live behavior and replace the illustrative sample with your own real output if desired.

## Learning reflection (review and personalize after your live runs)

I learned that token counts should come from each model's API usage metadata rather than from the number of words in a response. Separating input and output rates makes the cost calculation transparent. Free-tier usage and the equivalent paid-tier cost are different, and API keys must remain outside Git history.

## Submit safely

Create a public GitHub repository (or grant the TA access). If starting from the ZIP rather than a clone, initialize Git in the project directory and commit the protection files before obtaining keys:

```bash
git init
git add .gitignore .env.example
git commit -m "Protect API keys"
```

After setup and live testing, inspect the files to be committed:

```bash
git check-ignore .env
git add tracker.py pyproject.toml README.md tests .gitignore .env.example
# If uv created uv.lock, also run: git add uv.lock
git diff --cached --stat
git status --short
git commit -m "Build two-provider cost tracker"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPOSITORY.git
git push -u origin main
```

Use a new empty remote for these commands. If you cloned an existing repository, skip `git init` and `git remote add origin`. Never use force-add on `.env`; verify it is not tracked (`git ls-files .env` should print nothing). If any real key has ever entered Git history, revoke it immediately; deleting the file in a later commit does not remove it from history. Follow the course's instructions for repairing the history.

Submit your repository URL in Google Classroom: Assignment 1 → Add or create → Link → paste URL → Turn in. Never post API keys in Classroom.
