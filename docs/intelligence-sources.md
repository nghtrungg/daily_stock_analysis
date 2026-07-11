# Intelligence Sources

Intelligence sources provide news, announcements, social sentiment, and event context for reports. Supported source families include search APIs such as Anspire, SerpAPI, Tavily, Bocha, Brave, MiniMax, SearXNG, provider-specific announcements, financial news, and optional social sentiment sources.

Search failures should degrade gracefully. Results should identify source and limitations where possible. Missing news is not positive or negative evidence by itself. Do not expose provider keys or private request metadata.
