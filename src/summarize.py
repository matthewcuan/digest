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

PROMPT = """Below is a JSON list of AI-related items from today: blog posts from AI labs, \
news stories, Hacker News posts, and new GitHub repos. They go into a daily digest \
for someone who follows AI closely and wants only what matters.

For every item, return:
- summary: one plain sentence (at most 25 words) saying what it is or what was \
announced. Use only the title and snippet given; if they are too thin to say more, \
restate the title as a sentence. No hype, no "this article discusses".
- score: an integer from 1 to 10 for how much it matters to that reader.
  9-10: major model or product launches, significant research results, big \
industry or policy moves.
  5-8: notable releases, useful technical posts, meaningful company news.
  1-4: customer case studies, marketing, event recaps, minor updates, opinion \
pieces with no news.
  When several items cover the same story, give the most informative one its \
normal score and the rest 1.
  Score GitHub repos on how useful or novel the project looks, not star count alone.

Return every id by calling the save_summaries tool.

{items}"""

# A forced tool call is how Converse returns schema-shaped JSON.
TOOL = {
    "toolSpec": {
        "name": "save_summaries",
        "description": "Save the one-sentence summary and importance score for each item.",
        "inputSchema": {"json": {
            "type": "object",
            "properties": {
                "summaries": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "integer"},
                            "summary": {"type": "string"},
                            "score": {"type": "integer", "minimum": 1, "maximum": 10},
                        },
                        "required": ["id", "summary", "score"],
                    },
                }
            },
            "required": ["summaries"],
        }},
    }
}


def add_summaries(items: list[dict]) -> None:
    """Sets item["summary"] and item["score"] in place.

    If the call fails, summaries fall back to the snippet and scores stay None.
    """
    for item in items:
        item["summary"] = item["snippet"][:200]
        item["score"] = None
    if not items:
        return

    payload = [{"id": i, "title": it["title"], "source": it["source"], "snippet": it["snippet"]}
               for i, it in enumerate(items)]
    try:
        response = BEDROCK.converse(
            modelId=MODEL_ID,
            messages=[{"role": "user", "content": [{"text": PROMPT.format(items=json.dumps(payload))}]}],
            inferenceConfig={"maxTokens": 16000},
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
            if not (isinstance(i, int) and 0 <= i < len(items)):
                continue
            if str(entry.get("summary", "")).strip():
                items[i]["summary"] = entry["summary"].strip()
            try:
                items[i]["score"] = max(1, min(10, int(entry.get("score"))))
            except (TypeError, ValueError):
                pass
        usage = response.get("usage", {})
        log.info("Summarized %d of %d items (%s in / %s out tokens)", len(summaries), len(items),
                 usage.get("inputTokens"), usage.get("outputTokens"))
    except Exception:
        log.exception("Summarizing failed; sending snippets instead")
