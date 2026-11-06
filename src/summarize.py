"""Writes a one-sentence summary for each item with Claude Haiku on Bedrock."""

import json
import logging
import os

from anthropic import AnthropicBedrockMantle

log = logging.getLogger(__name__)
MODEL_ID = os.environ.get("MODEL_ID", "anthropic.claude-haiku-5-5")

PROMPT = """Below is a JSON list of AI-related items from today: blog posts, news, \
Hacker News stories, and GitHub repos. For each item, write one plain sentence \
(at most 25 words) saying what it is or what was announced. Use only the title and \
snippet given; if they are too thin to say more, restate the title as a sentence. \
No hype, no "this article discusses". Return a summary for every id.

{items}"""

SCHEMA = {
    "type": "object",
    "properties": {
        "summaries": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": {"type": "integer"}, "summary": {"type": "string"}},
                "required": ["id", "summary"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["summaries"],
    "additionalProperties": False,
}


def add_summaries(items: list[dict]) -> None:
    """Sets item["summary"] in place. Falls back to the snippet if the call fails."""
    for item in items:
        item["summary"] = item["snippet"][:200]
    if not items:
        return

    payload = [{"id": i, "title": it["title"], "source": it["source"], "snippet": it["snippet"]}
               for i, it in enumerate(items)]
    try:
        client = AnthropicBedrockMantle()  # region and credentials come from the Lambda environment
        response = client.messages.create(
            model=MODEL_ID,
            max_tokens=16000,
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
            messages=[{"role": "user", "content": PROMPT.format(items=json.dumps(payload))}],
        )
        if response.stop_reason != "end_turn":
            log.warning("Summaries stopped early (%s); using snippets", response.stop_reason)
            return
        text = next(b.text for b in response.content if b.type == "text")
        for entry in json.loads(text)["summaries"]:
            if 0 <= entry["id"] < len(items) and entry["summary"].strip():
                items[entry["id"]]["summary"] = entry["summary"].strip()
        log.info("Summarized %d items (%s in / %s out tokens)", len(items),
                 response.usage.input_tokens, response.usage.output_tokens)
    except Exception:
        log.exception("Summarizing failed; sending snippets instead")
