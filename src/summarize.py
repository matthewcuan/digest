"""Writes a one-sentence summary for each item with Claude Haiku on Bedrock.

Uses Claude Haiku 4.5 through Bedrock's Converse API (bedrock-runtime). Haiku 5.5 is
only served on the newer bedrock-mantle endpoint, which this AWS account isn't offered
yet; to move back, see git history for the AnthropicBedrockMantle version of this file.
"""

import json
import logging
import os

import boto3

log = logging.getLogger(__name__)
MODEL_ID = os.environ.get("MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0")
BEDROCK = boto3.client("bedrock-runtime")

PROMPT = """Below is a JSON list of AI-related items from today: blog posts, news, \
Hacker News stories, and GitHub repos. For each item, write one plain sentence \
(at most 25 words) saying what it is or what was announced. Use only the title and \
snippet given; if they are too thin to say more, restate the title as a sentence. \
No hype, no "this article discusses". Return a summary for every id by calling \
the save_summaries tool.

{items}"""

# A forced tool call is how Converse returns schema-shaped JSON.
TOOL = {
    "toolSpec": {
        "name": "save_summaries",
        "description": "Save the one-sentence summary for each item.",
        "inputSchema": {"json": {
            "type": "object",
            "properties": {
                "summaries": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"id": {"type": "integer"}, "summary": {"type": "string"}},
                        "required": ["id", "summary"],
                    },
                }
            },
            "required": ["summaries"],
        }},
    }
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
        response = BEDROCK.converse(
            modelId=MODEL_ID,
            messages=[{"role": "user", "content": [{"text": PROMPT.format(items=json.dumps(payload))}]}],
            inferenceConfig={"maxTokens": 8000},
            toolConfig={"tools": [TOOL], "toolChoice": {"tool": {"name": "save_summaries"}}},
        )
        if response["stopReason"] != "tool_use":
            log.warning("Summaries stopped early (%s); using snippets", response["stopReason"])
            return
        block = next(b["toolUse"] for b in response["output"]["message"]["content"] if "toolUse" in b)
        summaries = block["input"].get("summaries", [])
        if isinstance(summaries, str):  # occasionally the array arrives JSON-encoded
            summaries = json.loads(summaries)
        for entry in summaries:
            i = entry.get("id")
            if isinstance(i, int) and 0 <= i < len(items) and str(entry.get("summary", "")).strip():
                items[i]["summary"] = entry["summary"].strip()
        usage = response.get("usage", {})
        log.info("Summarized %d of %d items (%s in / %s out tokens)", len(summaries), len(items),
                 usage.get("inputTokens"), usage.get("outputTokens"))
    except Exception:
        log.exception("Summarizing failed; sending snippets instead")
