# Polymarket Signals for Equity Trading 🎰📈

A Python tool that monitors Polymarket prediction markets and generates trading signals for US equities.

## What It Does

- **Fetches** active prediction markets from Polymarket API
- **Categorizes** markets by topic (Fed policy, crypto, tariffs, AI regulation, etc.)
- **Maps** probability changes to affected stocks
- **Generates** daily signal reports highlighting major moves

## Signal Logic

| Probability Change | Classification |
|-------------------|----------------|
| > 5%              | 🔴 Major       |
| 2-5%              | 🟡 Notable     |
| < 2%              | ⚪ Stable      |

## Tracked Categories → Stock Impact

| Category | Keywords | Affected Stocks |
|----------|----------|-----------------|
| Fed Policy | fed, fomc, rate cut | QQQ, TLT, XLF, ARKK |
| Crypto/Bitcoin | bitcoin, mstr, coinbase | COIN, MSTR, RIOT, MARA |
| Tariffs/Trade | tariff, china trade | BABA, JD, AAPL, NIO |
| AI Regulation | ai regulation, ai safety | NVDA, MSFT, GOOG, META |
| Antitrust | breakup, doj, ftc | GOOG, META, AAPL, AMZN |
| Geopolitical | taiwan, ukraine, war | LMT, RTX, TSM, XLE |
| Trump Policy | deportation, executive order | GEO, CXW, CAT |
| ... | ... | ... |

## Installation

```bash
# Clone
git clone https://github.com/yourusername/polymarket-signals.git
cd polymarket-signals

# Setup virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## Usage

```bash
# Activate venv
source venv/bin/activate

# Generate daily report
python polymarket.py

# Run backtest (after accumulating data)
python backtest.py
```

## Output Example

```
🎰 Polymarket 每日信号 | 2026-01-29

🔴 重大变化 (>5% 概率变动)
📈 Fed to cut rates in March?
   概率: 65.2% (+7.3%)
   关联股票: QQQ, TLT, ARKK

🟡 值得关注 (2-5% 变动)
• Bitcoin ETF approval delayed?
  32.0% (-3.5%) | 股票: COIN, MSTR, RIOT

📊 追踪市场: 18 | 重大变化: 1 | 值得关注: 2
```

## Configuration

Edit `config.json` to:
- Add/remove tracked categories
- Modify stock mappings
- Adjust alert thresholds
- Change minimum volume filters

## Data Storage

- `data/markets.db` - SQLite database for historical snapshots
- `data/history/` - Daily JSON signal files

## Scheduled Runs

Use cron or your preferred scheduler:

```bash
# Daily at 7:30 AM
30 7 * * * cd /path/to/polymarket-signals && ./run.sh
```

## Disclaimer

This tool is for informational purposes only. Prediction market probabilities are not investment advice. Always do your own research.

## License

MIT
