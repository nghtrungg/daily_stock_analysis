# LLM Providers

The project can route analysis through Anspire, AIHubMix, Gemini, Anthropic Claude, OpenAI-compatible providers, DeepSeek, Tongyi Qianwen, Ollama, or other local compatible deployments depending on configuration.

Configure at least one provider before running analysis. Do not hardcode model names or keys in code. Prefer configuration-driven routing and fallback. Redact API keys, authorization headers, cookies, and private base URLs in diagnostics when needed.

Provider changes should cover routing, fallback, timeout, error reporting, and prompt compatibility.
