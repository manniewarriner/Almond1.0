"""Synthetic drafting comparison against the already-running local model only."""

from __future__ import annotations

import argparse
import json
import urllib.request
from time import perf_counter

from almond_ai.agents.registry import AgentRegistry
from almond_ai.bots.registry import BUILT_IN_BOTS, bot_system_prompt
from almond_ai.config import ModelSettings
from almond_ai.core.drafting import drafting_messages
from almond_ai.models.provider import LocalHTTPProvider


def benchmark(profile: str = "both") -> None:
    request = (
        "Draft a client email.\nPurpose: Ask Alex to confirm availability for a review meeting.\n"
        "Key points: Tuesday at 10am is proposed, not booked. Ask for a reply. "
        "Do not invent a date, venue or sender name.\nTone: Brief, professional."
    )
    history = [{"role": "user", "content": request}]
    bot = next(bot for bot in BUILT_IN_BOTS if bot.id == "drafting")
    legacy = [
        {"role": "system", "content": bot_system_prompt(bot, AgentRegistry().system_prompt())},
        *history,
    ]
    provider = LocalHTTPProvider(ModelSettings(provider="llama_cpp"))
    for name, messages, drafting in (
        ("before", legacy, False),
        ("after", drafting_messages(history), True),
    ):
        if profile != "both" and profile != name:
            continue
        url, payload = provider._payload(messages, stream=True, drafting=drafting)
        # Bound the legacy comparison too; the old production path had no output cap.
        payload["max_tokens"] = 512
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        start = perf_counter()
        first = None
        text = ""
        finish = None
        timings = None
        with urllib.request.urlopen(req, timeout=120) as response:
            for raw_line in response:
                line = raw_line.decode().strip()
                if not line.startswith("data:"):
                    continue
                body = line[5:].strip()
                if body == "[DONE]":
                    break
                data = json.loads(body)
                timings = data.get("timings", timings)
                for choice in data.get("choices", []):
                    chunk = choice.get("delta", {}).get("content") or ""
                    if chunk:
                        if first is None:
                            first = perf_counter() - start
                            print(
                                json.dumps({"profile": name, "first_text_seconds": first}),
                                flush=True,
                            )
                        text += chunk
                    finish = choice.get("finish_reason") or finish
        print(
            json.dumps(
                {
                    "profile": name,
                    "first_text_seconds": round(first, 3) if first else None,
                    "total_seconds": round(perf_counter() - start, 3),
                    "input_characters": sum(len(m["content"]) for m in messages),
                    "output_words": len(text.split()),
                    "finish_reason": finish,
                    "timings": timings,
                    "synthetic_draft": text,
                }
            ),
            flush=True,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("before", "after", "both"), default="both")
    benchmark(parser.parse_args().profile)
