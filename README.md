# AI digest

A Lambda that runs daily at 7am Pacific and emails a digest:

- **From the AI labs:** new posts from OpenAI, Anthropic, Google DeepMind, Google AI, Microsoft Research, Hugging Face, NVIDIA, AWS ML and Mistral
- **News:** AI coverage from TechCrunch, The Verge and Ars Technica
- **On Hacker News:** AI stories on the front page
- **Trending repos:** the most-starred new GitHub repos tagged `llm`, `ai-agents`, `generative-ai` or `machine-learning`

Claude Haiku 5.5 on Bedrock writes a one-sentence summary for each item. A DynamoDB table remembers the links it has already sent, so nothing shows up twice. Sources, caps and keywords are all in `src/sources.py`.

## Deploy

Requires Python 3.13, the [AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html), and AWS credentials for us-east-2.

```powershell
sam build
sam deploy
```

After the first deploy:

1. The address in `samconfig.toml` must already be a verified SES identity in us-east-2.
2. Make sure Claude Haiku 5.5 is enabled under [Bedrock model access](https://console.aws.amazon.com/bedrock/home#/modelaccess).

## Test it

```powershell
# Builds the digest without sending it or marking anything as seen
sam remote invoke DigestFunction --event '{"dry_run": true}'

# Sends a real email now
sam remote invoke DigestFunction
```

Logs: `sam logs -n DigestFunction --tail`

## Change it

- **Time or timezone:** `ScheduleCron` / `ScheduleTimezone` in `template.yaml`
- **Model:** `ModelId` in `template.yaml` (for example `anthropic.claude-sonnet-5-5`)
- **Sources:** `src/sources.py`
