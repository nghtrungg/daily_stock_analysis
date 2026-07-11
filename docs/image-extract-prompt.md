# Image Stock Extraction Prompt

This document records the prompt contract for extracting stock symbols from images. The extractor should identify stock codes, stock names, market hints, and confidence from screenshots or images containing watchlists, portfolio tables, or stock-related text.

Do not invent symbols. Preserve uncertain results with low confidence instead of silently dropping them. If `src/services/image_stock_extractor.py` changes `EXTRACT_PROMPT`, the PR description must include the full latest prompt.
