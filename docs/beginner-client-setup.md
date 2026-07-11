# Beginner Client Setup

```bash
git clone https://github.com/ZhuLinsen/daily_stock_analysis.git
cd daily_stock_analysis
pip install -r requirements.txt
cp .env.example .env
python main.py --serve
```

Open `http://127.0.0.1:8000` after the server starts. Configure at least one LLM provider and one stock list. Notification channels are optional but recommended for scheduled reports.

Common commands:

```bash
python main.py --dry-run
python main.py --stocks 600519,hk00700,AAPL
python main.py --market-review
python main.py --schedule
python main.py --serve-only
```

If dependencies fail, verify Python version and network access. If analysis fails, check provider keys and data-source availability. If notifications fail, verify webhook or bot settings.
