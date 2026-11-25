"""Send the same prompt to Gemini and Groq and compare their usage."""

import argparse
import json
import math
import os
import sys
from pathlib import Path
from time import perf_counter

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
DEFAULT_MODELS = {
    "gemini": "gemini-3.1-flash-lite",
    "groq": "openai/gpt-oss-20b",
}
# Standard paid-tier text prices in USD per million tokens (input, output).
# Checked 2026-11-24: https://ai.google.dev/gemini-api/docs/pricing
# and https://console.groq.com/docs/models
PRICES = {
    "gemini": {
        "gemini-3.1-flash-lite": (0.25, 1.50),
        "gemini-3.5-flash-lite": (0.30, 2.50),
        "gemini-2.5-flash-lite": (0.10, 0.40),
    },
    "groq": {
        "openai/gpt-oss-20b": (0.075, 0.30),
        "openai/gpt-oss-120b": (0.15, 0.60),
    },
}


def get_key(provider):
    """Read a key without ever printing it; reject example placeholders."""
    name = f"{provider.upper()}_API_KEY"
    key = os.getenv(name, "").strip()
    if not key and provider == "gemini":
        key = os.getenv("GOOGLE_API_KEY", "").strip()
    if not key or key.startswith("replace_with_"):
        raise ValueError(f"Missing {name}. Copy .env.example to .env and set your key.")
    return key


def get_prices(provider, model):
    """Use the selected model's prices or explicit environment overrides."""
    prefix = provider.upper()
    input_rate = os.getenv(f"{prefix}_INPUT_PRICE_PER_M")
    output_rate = os.getenv(f"{prefix}_OUTPUT_PRICE_PER_M")
    if input_rate is None and output_rate is None:
        if model not in PRICES[provider]:
            raise ValueError(f"No prices configured for {provider}. Set both "
                             f"{prefix}_INPUT_PRICE_PER_M and {prefix}_OUTPUT_PRICE_PER_M.")
        return PRICES[provider][model]
    try:
        rates = (float(input_rate), float(output_rate))
        if any(not math.isfinite(rate) or rate < 0 for rate in rates):
            raise ValueError
    except (TypeError, ValueError):
        raise ValueError(f"Set both {prefix} prices to non-negative numbers.") from None
    return rates


def token_count(value):
    """Reject missing usage instead of estimating it from the reply."""
    if type(value) is not int or value < 0:
        raise RuntimeError("API did not return a valid token count.")
    return value


def call_gemini(prompt, model, key):
    """Return text and actual Gemini usage metadata."""
    from google import genai

    client = genai.Client(api_key=key, vertexai=False)
    try:
        response = client.models.generate_content(model=model, contents=prompt)
        usage = response.usage_metadata
        if usage is None or not response.text:
            raise RuntimeError("Gemini returned no text or usage data.")
        # Gemini bills reported thinking tokens at the output rate as well.
        output = token_count(usage.candidates_token_count)
        output += token_count(getattr(usage, "thoughts_token_count", None) or 0)
        return response.text, token_count(usage.prompt_token_count), output
    finally:
        client.close()


def call_groq(prompt, model, key):
    """Return text and actual Groq chat-completion usage."""
    from groq import Groq

    with Groq(api_key=key, timeout=60.0, max_retries=0) as client:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        usage = response.usage
        reply = response.choices[0].message.content if response.choices else None
        if usage is None or not reply:
            raise RuntimeError("Groq returned no text or usage data.")
        return reply, token_count(usage.prompt_tokens), token_count(usage.completion_tokens)


def calculate_cost(input_tokens, output_tokens, input_price, output_price):
    """Convert per-million-token prices to a USD cost for this request."""
    return (input_tokens * input_price + output_tokens * output_price) / 1_000_000


def print_results(results, times):
    """Show both complete replies, then a side-by-side metrics table."""
    for result in results:
        print(f"\n--- {result['provider'].upper()} ({result['model']}) ---")
        print(result["reply"])
    print("\nProvider comparison (standard paid-tier estimate)")
    print(f"{'Provider':<10} {'Input tokens':>13} {'Output tokens':>14} "
          f"{'Seconds':>10} {'Cost (USD)':>14}")
    print("-" * 65)
    for result, seconds in zip(results, times):
        print(f"{result['provider']:<10} {result['input_tokens']:>13} "
              f"{result['output_tokens']:>14} {seconds:>10.3f} "
              f"{result['cost_usd']:>14.9f}")
    print("Eligible free-tier calls cost $0; estimates are not actual bills.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prompt", help="The same prompt to send to both providers")
    args = parser.parse_args(argv)
    if not args.prompt.strip():
        parser.error("prompt cannot be empty")
    load_dotenv(ROOT / ".env", override=False)

    # Validate both configurations before spending either provider's quota.
    configs = []
    try:
        for provider in ("gemini", "groq"):
            key = get_key(provider)
            model = os.getenv(f"{provider.upper()}_MODEL", DEFAULT_MODELS[provider]).strip()
            if not model:
                raise ValueError(f"Set a non-empty {provider.upper()}_MODEL.")
            configs.append((provider, model, key, get_prices(provider, model)))
    except ValueError as error:
        print(f"Configuration error: {error}", file=sys.stderr)
        return 1

    results, times = [], []
    for provider, model, key, (input_price, output_price) in configs:
        call = call_gemini if provider == "gemini" else call_groq
        try:
            start = perf_counter()
            reply, input_tokens, output_tokens = call(args.prompt, model, key)
            times.append(perf_counter() - start)
        except Exception as error:
            # SDK exception messages can include request details. Do not log them.
            status = getattr(error, "status_code", None) or getattr(error, "code", None)
            status_text = f", HTTP {status}" if isinstance(status, int) else ""
            print(f"{provider}: request failed ({type(error).__name__}{status_text}). "
                  "Check your key, model, quota and internet connection. "
                  "No new results.json was saved.", file=sys.stderr)
            return 1
        results.append({
            "provider": provider,
            "model": model,
            "reply": reply,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "input_price_per_m": input_price,
            "output_price_per_m": output_price,
            "cost_usd": calculate_cost(input_tokens, output_tokens, input_price, output_price),
        })

    print_results(results, times)
    try:
        (ROOT / "results.json").write_text(
            json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    except OSError:
        print("Could not write results.json. Check folder permissions.", file=sys.stderr)
        return 1
    print("\nSaved results.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
