---
name: "stock_analyzer"
description: "Analyze stocks and markets. Use this skill when the user wants to analyze one or more stocks or perform a market review."
---

# Stock Analyzer

This skill is based on the logic in `src/services/analyzer_service.py`. It provides stock-level analysis and overall market review capabilities.

## Output Structure (`AnalysisResult`)

Analysis functions return an `AnalysisResult` object, or a list of them. The object contains a rich structured result. The `dashboard` property is the core analysis surface and is divided into four main sections:

1. **`core_conclusion`**: one-sentence summary, signal type, and position guidance.
2. **`data_perspective`**: technical data, including trend status, price position, volume analysis, and chip structure.
3. **`intelligence`**: qualitative information such as news, risk warnings, and positive catalysts.
4. **`battle_plan`**: actionable strategy, including target buy/sell points, position strategy, and risk-control checklist.

## Configuration (`Config`)

All analysis functions accept an optional `config` object. It contains application configuration such as API keys, notification settings, and analysis parameters.

If no `config` object is provided, functions use the global singleton loaded from `.env`.

**Reference:** [`Config`](src/config.py)

## Functions

### 1. Analyze One Stock

**Description:** Analyze a single stock and return the analysis result.

**When to use:** When the user asks to analyze a specific stock.

**Input:**

- `stock_code` (str): stock code to analyze.
- `config` (Config, optional): configuration object. Defaults to `None`.
- `full_report` (bool, optional): whether to generate a full report. Defaults to `False`.
- `notifier` (NotificationService, optional): notification service object. Defaults to `None`.

**Output:** `Optional[AnalysisResult]`

Returns an `AnalysisResult` when analysis succeeds, otherwise `None`.

**Example:**

```python
from src.services.analyzer_service import analyze_stock

# Analyze one stock.
result = analyze_stock("600989")
if result:
    print(f"Stock: {result.name} ({result.code})")
    print(f"Sentiment score: {result.sentiment_score}")
    print(f"Operation advice: {result.operation_advice}")
```

**Reference:** [`analyze_stock`](src/services/analyzer_service.py)

### 2. Analyze Multiple Stocks

**Description:** Analyze a list of stocks and return a list of results.

**When to use:** When the user wants to analyze several stocks at once.

**Input:**

- `stock_codes` (List[str]): stock codes to analyze.
- `config` (Config, optional): configuration object. Defaults to `None`.
- `full_report` (bool, optional): whether to generate a full report for each stock. Defaults to `False`.
- `notifier` (NotificationService, optional): notification service object. Defaults to `None`.

**Output:** `List[AnalysisResult]`

**Example:**

```python
from src.services.analyzer_service import analyze_stocks

# Analyze multiple stocks.
results = analyze_stocks(["600989", "000001"])
for result in results:
    print(f"Stock: {result.name}, advice: {result.operation_advice}")
```

**Reference:** [`analyze_stocks`](src/services/analyzer_service.py)

### 3. Perform Market Review

**Description:** Review the overall market and return a report.

**When to use:** When the user asks for a market overview, summary, or review.

**Input:**

- `config` (Config, optional): configuration object. Defaults to `None`.
- `notifier` (NotificationService, optional): notification service object. Defaults to `None`.

**Output:** `Optional[str]`

Returns a market review report string, or `None` on failure.

**Example:**

```python
from src.services.analyzer_service import perform_market_review

# Perform market review.
report = perform_market_review()
if report:
    print(report)
```

**Reference:** [`perform_market_review`](src/services/analyzer_service.py)
