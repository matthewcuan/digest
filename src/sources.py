"""What the digest pulls from. Edit these lists to change the sources."""

# AI company blogs (RSS/Atom). A feed that fails is logged and skipped.
BLOGS = {
    "OpenAI": "https://openai.com/news/rss.xml",
    "Google DeepMind": "https://deepmind.google/blog/rss.xml",
    "Google AI": "https://blog.google/technology/ai/rss/",
    "Microsoft Research": "https://www.microsoft.com/en-us/research/feed/",
    "Hugging Face": "https://huggingface.co/blog/feed.xml",
    "NVIDIA": "https://blogs.nvidia.com/feed/",
    "AWS Machine Learning": "https://aws.amazon.com/blogs/machine-learning/feed/",
    "Mistral": "https://mistral.ai/rss.xml",
}

# Anthropic has no RSS feed, so its sitemap is read instead (pages under these paths).
ANTHROPIC_SITEMAP = "https://www.anthropic.com/sitemap.xml"
ANTHROPIC_PATHS = ("/news/", "/research/", "/engineering/")

# AI news outlets (RSS).
NEWS = {
    "TechCrunch": "https://techcrunch.com/category/artificial-intelligence/feed/",
    "The Verge": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
    "Ars Technica": "https://arstechnica.com/ai/feed/",
}

# Hacker News front-page stories whose titles match this pattern count as AI stories.
HN_KEYWORDS = (
    r"\b(AI|A\.I\.|LLMs?|GPT|ChatGPT|Claude|Anthropic|OpenAI|Gemini|DeepMind|Llama|Mistral|"
    r"Copilot|agents?|agentic|transformers?|diffusion|neural|machine learning|ML|"
    r"inference|fine-?tun\w*|RAG|embeddings?|model weights|open-?weights?|Hugging ?Face)\b"
)

# GitHub repos created in the last week with these topics, ranked by stars.
GITHUB_TOPICS = ("llm", "ai-agents", "generative-ai", "machine-learning")

# Per-section caps so the email stays short.
MAX_PER_SECTION = {"blogs": 20, "news": 15, "hn": 10, "github": 10}

# How far back to look for new posts. Repeats are filtered out separately.
LOOKBACK_HOURS = 36
