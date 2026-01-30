#!/usr/bin/env python3
"""
Polymarket Signal Generator for Secondary Market Investment
"""

import json
import requests
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import sqlite3
import re

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.json"
DB_PATH = BASE_DIR / "data" / "markets.db"
HISTORY_PATH = BASE_DIR / "data" / "history"

API_BASE = "https://gamma-api.polymarket.com"

def load_config() -> dict:
    """Load configuration file"""
    with open(CONFIG_PATH) as f:
        return json.load(f)

def init_db():
    """Initialize SQLite database for historical tracking"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_PATH.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS market_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        market_id TEXT NOT NULL,
        question TEXT NOT NULL,
        category TEXT,
        yes_price REAL,
        no_price REAL,
        volume_24h REAL,
        volume_total REAL,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(market_id, timestamp)
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        market_id TEXT NOT NULL,
        question TEXT NOT NULL,
        change_type TEXT,
        old_price REAL,
        new_price REAL,
        change_pct REAL,
        stocks_affected TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    
    c.execute('''CREATE INDEX IF NOT EXISTS idx_market_time 
                 ON market_snapshots(market_id, timestamp)''')
    
    conn.commit()
    conn.close()

def fetch_markets(limit: int = 200, active_only: bool = True) -> List[dict]:
    """Fetch active markets from Polymarket API"""
    params = {
        "limit": limit,
        "active": str(active_only).lower(),
        "closed": "false"
    }
    
    try:
        resp = requests.get(f"{API_BASE}/markets", params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"Error fetching markets: {e}")
        return []

def categorize_market(question: str, description: str, config: dict) -> Tuple[Optional[str], List[str]]:
    """
    Categorize a market based on keywords and return relevant stocks
    Returns: (category_name, list_of_affected_stocks)
    """
    text = f"{question} {description}".lower()
    
    for category, cat_config in config["watchlist"].items():
        keywords = cat_config.get("keywords", [])
        for keyword in keywords:
            if keyword.lower() in text:
                # Collect all potentially affected stocks
                stocks = []
                impact = cat_config.get("stock_impact", {})
                for key, value in impact.items():
                    if isinstance(value, list):
                        stocks.extend(value)
                return category, list(set(stocks))
    
    return None, []

def filter_relevant_markets(markets: List[dict], config: dict) -> List[dict]:
    """Filter markets relevant to US equity investment"""
    relevant = []
    
    for market in markets:
        question = market.get("question", "")
        description = market.get("description", "")
        volume_24h = market.get("volume24hr", 0) or 0
        
        # Skip low volume markets
        if volume_24h < config["alert_thresholds"]["min_volume_24h"]:
            continue
        
        category, stocks = categorize_market(question, description, config)
        
        if category:
            market["_category"] = category
            market["_affected_stocks"] = stocks
            relevant.append(market)
    
    return relevant

def calculate_signals(markets: List[dict], config: dict) -> dict:
    """
    Calculate trading signals from market data
    Returns structured signal data
    """
    major_threshold = config["alert_thresholds"]["major_change"]
    notable_threshold = config["alert_thresholds"]["notable_change"]
    
    signals = {
        "major": [],      # >5% change
        "notable": [],    # 2-5% change
        "stable": [],     # <2% change
        "timestamp": datetime.utcnow().isoformat()
    }
    
    for market in markets:
        # Parse outcome prices
        try:
            prices = json.loads(market.get("outcomePrices", "[]"))
            yes_price = float(prices[0]) if prices else 0
        except:
            yes_price = 0
        
        # Get price changes
        day_change = (market.get("oneDayPriceChange") or 0) * 100  # Convert to percentage
        week_change = (market.get("oneWeekPriceChange") or 0) * 100
        
        signal = {
            "id": market.get("id"),
            "question": market.get("question"),
            "category": market.get("_category"),
            "affected_stocks": market.get("_affected_stocks", []),
            "current_prob": round(yes_price * 100, 1),  # As percentage
            "day_change": round(day_change, 2),
            "week_change": round(week_change, 2),
            "volume_24h": market.get("volume24hr", 0),
            "volume_total": market.get("volumeNum", 0),
            "slug": market.get("slug"),
        }
        
        # Classify by magnitude of change
        abs_change = abs(day_change)
        if abs_change >= major_threshold:
            signals["major"].append(signal)
        elif abs_change >= notable_threshold:
            signals["notable"].append(signal)
        else:
            signals["stable"].append(signal)
    
    # Sort by absolute change magnitude
    for key in ["major", "notable"]:
        signals[key] = sorted(signals[key], key=lambda x: abs(x["day_change"]), reverse=True)
    
    return signals

def format_signal_report(signals: dict, config: dict) -> str:
    """Format signals into a readable Telegram message"""
    lines = []
    now = datetime.now()
    
    lines.append(f"🎰 **Polymarket 每日信号** | {now.strftime('%Y-%m-%d')}")
    lines.append("")
    
    # Major changes
    if signals["major"]:
        lines.append("🔴 **重大变化 (>5% 概率变动)**")
        for s in signals["major"][:5]:  # Top 5
            direction = "📈" if s["day_change"] > 0 else "📉"
            sign = "+" if s["day_change"] > 0 else ""
            lines.append(f"{direction} **{s['question'][:60]}...**" if len(s['question']) > 60 else f"{direction} **{s['question']}**")
            lines.append(f"   概率: {s['current_prob']}% ({sign}{s['day_change']}%)")
            if s["affected_stocks"]:
                lines.append(f"   关联股票: {', '.join(s['affected_stocks'][:5])}")
            lines.append("")
    else:
        lines.append("🔴 **重大变化**: 无")
        lines.append("")
    
    # Notable changes
    if signals["notable"]:
        lines.append("🟡 **值得关注 (2-5% 变动)**")
        for s in signals["notable"][:5]:  # Top 5
            direction = "↑" if s["day_change"] > 0 else "↓"
            sign = "+" if s["day_change"] > 0 else ""
            lines.append(f"• {s['question'][:50]}...")
            lines.append(f"  {s['current_prob']}% ({sign}{s['day_change']}%) | 股票: {', '.join(s['affected_stocks'][:3]) if s['affected_stocks'] else 'N/A'}")
        lines.append("")
    
    # Summary stats
    total_tracked = len(signals["major"]) + len(signals["notable"]) + len(signals["stable"])
    lines.append(f"📊 **追踪市场**: {total_tracked} | 重大变化: {len(signals['major'])} | 值得关注: {len(signals['notable'])}")
    
    return "\n".join(lines)

def save_snapshot(markets: List[dict]):
    """Save current market state to database"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    for market in markets:
        try:
            prices = json.loads(market.get("outcomePrices", "[]"))
            yes_price = float(prices[0]) if prices else 0
            no_price = float(prices[1]) if len(prices) > 1 else 0
        except:
            yes_price, no_price = 0, 0
        
        c.execute('''INSERT OR IGNORE INTO market_snapshots 
                     (market_id, question, category, yes_price, no_price, volume_24h, volume_total)
                     VALUES (?, ?, ?, ?, ?, ?, ?)''',
                  (market.get("id"), 
                   market.get("question"),
                   market.get("_category"),
                   yes_price,
                   no_price,
                   market.get("volume24hr", 0),
                   market.get("volumeNum", 0)))
    
    conn.commit()
    conn.close()

def get_historical_changes(market_id: str, days: int = 7) -> List[dict]:
    """Get historical price data for a market"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
    
    c.execute('''SELECT yes_price, timestamp FROM market_snapshots 
                 WHERE market_id = ? AND timestamp > ?
                 ORDER BY timestamp''', (market_id, cutoff))
    
    rows = c.fetchall()
    conn.close()
    
    return [{"price": r[0], "timestamp": r[1]} for r in rows]

def generate_daily_report() -> str:
    """Main function to generate daily report"""
    config = load_config()
    init_db()
    
    # Fetch and process markets
    print("Fetching markets from Polymarket...")
    raw_markets = fetch_markets(limit=300)
    print(f"Fetched {len(raw_markets)} markets")
    
    # Filter relevant ones
    relevant = filter_relevant_markets(raw_markets, config)
    print(f"Found {len(relevant)} relevant markets")
    
    # Save snapshot
    save_snapshot(relevant)
    
    # Calculate signals
    signals = calculate_signals(relevant, config)
    
    # Format report
    report = format_signal_report(signals, config)
    
    # Also save JSON for analysis
    today = datetime.now().strftime("%Y-%m-%d")
    json_path = HISTORY_PATH / f"signals_{today}.json"
    with open(json_path, "w") as f:
        json.dump(signals, f, indent=2, ensure_ascii=False)
    
    return report

def check_for_alerts(threshold_pct: float = 5.0) -> List[dict]:
    """Check for sudden large moves that warrant immediate alert"""
    config = load_config()
    raw_markets = fetch_markets(limit=300)
    relevant = filter_relevant_markets(raw_markets, config)
    
    alerts = []
    for market in relevant:
        day_change = abs((market.get("oneDayPriceChange") or 0) * 100)
        if day_change >= threshold_pct:
            try:
                prices = json.loads(market.get("outcomePrices", "[]"))
                yes_price = float(prices[0]) if prices else 0
            except:
                yes_price = 0
            
            alerts.append({
                "question": market.get("question"),
                "category": market.get("_category"),
                "stocks": market.get("_affected_stocks", []),
                "current_prob": round(yes_price * 100, 1),
                "change": round((market.get("oneDayPriceChange") or 0) * 100, 2),
                "volume_24h": market.get("volume24hr", 0)
            })
    
    return alerts

if __name__ == "__main__":
    report = generate_daily_report()
    print(report)
