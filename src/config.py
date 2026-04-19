"""Source configuration for AI Daily Clipping Crawler."""

# Reddit subreddits to crawl
REDDIT_SUBREDDITS = [
    "MachineLearning",
    "artificial",
    "OpenAI",
    "LocalLLaMA",
    "ChatGPT",
    "singularity",
    "StableDiffusion",
    "ClaudeAI",
]
REDDIT_POSTS_PER_SUB = 8

# Hacker News
HN_TOP_STORIES_LIMIT = 50
HN_AI_KEYWORDS = [
    "ai", "llm", "gpt", "claude", "gemini", "openai", "anthropic",
    "model", "neural", "machine learning", "deep learning", "transformer",
    "diffusion", "language model", "chatbot", "copilot", "agent",
    "rag", "fine-tune", "finetune", "embedding", "reasoning",
    "multimodal", "vision", "huggingface", "mistral", "llama",
    "stable diffusion", "midjourney", "sora", "ml ", " ml",
]

# arXiv categories
ARXIV_CATEGORIES = ["cs.AI", "cs.LG", "cs.CL"]
ARXIV_MAX_RESULTS = 40

# RSS feeds: (url, source_name, source_type)
RSS_FEEDS = [
    # Official blogs
    ("https://openai.com/blog/rss.xml", "OpenAI Blog", "official"),
    ("https://www.anthropic.com/rss.xml", "Anthropic Blog", "official"),
    ("https://blog.google/technology/ai/rss/", "Google AI Blog", "official"),
    ("https://ai.meta.com/blog/rss/", "Meta AI Blog", "official"),
    ("https://blogs.microsoft.com/ai/feed/", "Microsoft AI Blog", "official"),
    ("https://blogs.nvidia.com/feed/", "NVIDIA Blog", "official"),
    # Media
    ("https://techcrunch.com/category/artificial-intelligence/feed/", "TechCrunch AI", "media"),
    ("https://www.theverge.com/rss/ai-artificial-intelligence/index.xml", "The Verge AI", "media"),
    ("https://venturebeat.com/category/ai/feed/", "VentureBeat AI", "media"),
    ("https://www.technologyreview.com/feed/", "MIT Tech Review", "media"),
    ("https://the-decoder.com/feed/", "The Decoder", "media"),
    ("https://www.marktechpost.com/feed/", "MarkTechPost", "media"),
]

# GitHub Trending
GITHUB_TRENDING_URL = "https://github.com/trending?since=daily&spoken_language_code="
GITHUB_AI_KEYWORDS = [
    "ai", "llm", "gpt", "model", "neural", "machine-learning",
    "deep-learning", "transformer", "diffusion", "language-model",
    "agent", "rag", "embedding", "fine-tune", "inference",
    "chatbot", "copilot", "multimodal",
]

# HuggingFace Daily Papers
HUGGINGFACE_PAPERS_URL = "https://huggingface.co/papers"

# Product Hunt
PRODUCTHUNT_API_URL = "https://api.producthunt.com/v2/api/graphql"
PRODUCTHUNT_AI_TAGS = ["artificial-intelligence", "machine-learning", "chatgpt", "ai"]

# Dedup
DEDUP_SIMILARITY_THRESHOLD = 0.7

# Source type priority for dedup (lower = higher priority)
SOURCE_TYPE_PRIORITY = {
    "official": 0,
    "media": 1,
    "research": 2,
    "community": 3,
    "product": 4,
}

# Common HTTP headers
HTTP_HEADERS = {
    "User-Agent": "AI-Daily-Clipping/0.1 (github.com/ai-daily-clipping)",
    "Accept": "application/json",
}

# Request timeout in seconds
REQUEST_TIMEOUT = 15

# Per-source_type article limits (top N by score)
MAX_ARTICLES_PER_TYPE = {
    "official": 20,
    "media": 20,
    "research": 20,
    "community": 20,
    "product": 10,
}

# Minimum score thresholds (articles below this are dropped)
MIN_SCORE = {
    "community": 10,  # Reddit/HN low-effort posts
}

# Jina Reader API (free tier: 20 req/min)
JINA_READER_URL = "https://r.jina.ai/"
JINA_RATE_LIMIT_DELAY = 3.0  # seconds between requests (respects 20/min limit)
# Nav-heavy sites (TechCrunch, The Verge) burn thousands of chars on menus/share
# buttons before reaching body — 12k gives headroom without bloating JSON.
MAX_CONTENT_LENGTH = 12000  # chars (markdown is more verbose than plain text)
BODY_SUMMARY_MAX_CHARS = 600  # body-derived summary target length
RAW_OUTPUT_SUFFIX = ".raw"  # output/YYYY-MM-DD.raw.json

# AI relevance keywords — articles from community sources
# must match at least one keyword in title to be kept
AI_RELEVANCE_KEYWORDS = [
    "ai", "llm", "gpt", "claude", "gemini", "openai", "anthropic",
    "model", "neural", "machine learning", "deep learning", "transformer",
    "diffusion", "language model", "chatbot", "copilot", "agent",
    "rag", "fine-tune", "finetune", "embedding", "reasoning",
    "multimodal", "vision", "huggingface", "mistral", "llama",
    "stable diffusion", "midjourney", "sora", "nvidia", "meta ai",
    "robot", "autonomous", "prompt", "token", "inference",
    "open source", "open-source", "benchmark", "training",
    "lora", "gguf", "quant", "vram", "parameter",
    "arxiv", "paper", "research", "dataset", "alignment", "safety",
    "coding", "code", "developer", "api", "sdk",
]
