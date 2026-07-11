# Tushare Stock List Guide

Use Tushare as a more stable source for A-share stock metadata and historical data. Configure `TUSHARE_TOKEN` in `.env` or deployment secrets. Do not commit real tokens.

```bash
TUSHARE_TOKEN=your_token_here
```

When configured, supported A-share paths should prefer Tushare. When it is not configured or fails, the system should continue through free providers such as AkShare, Baostock, Pytdx, Efinance, or YFinance where applicable. A single provider failure should not break the whole analysis flow unless fail-fast behavior is explicitly required.

Validate provider changes with the closest tests, `python -m py_compile <changed_python_files>`, and offline fallback checks where possible. Online provider checks are optional because upstream availability varies.
