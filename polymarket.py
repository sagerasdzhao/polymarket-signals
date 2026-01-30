#!/usr/bin/env python3
"""
Polymarket Signal Generator for US Equity Trading
v2.1 - Track specific events + keyword matching
"""

import json
import requests
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import sqlite3

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.json"
DB_PATH = BASE_DIR / "data" / "markets.db"
HISTORY_PATH = BASE_DIR / "data" / "history"

API_BASE = "https://gamma-api.polymarket.com"

def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return json.load(f)

def init_db():
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
        volume_24h REAL,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.commit()
    conn.close()

def fetch_tracked_events(config: dict) -> List[dict]:
    """Fetch specific tracked events by slug"""
    results = []
    
    for event_config in config.get("tracked_events", []):
        slug = event_config["slug"]
        try:
            resp = requests.get(f"{API_BASE}/events?slug={slug}", timeout=30)
            resp.raise_for_status()
            data = resp.json()
            
            if data and len(data) > 0:
                event = data[0]
                # Get top markets from this event
                markets = event.get("markets", [])
                
                # Sort by price (highest probability first)
                for market in markets[:5]:  # Top 5 outcomes
                    try:
                        prices = json.loads(market.get("outcomePrices", "[]"))
                        yes_price = float(prices[0]) if prices else 0
                    except:
                        yes_price = 0
                    
                    if yes_price > 0.001:  # Skip near-zero outcomes
                        results.append({
                            "id": market.get("id"),
                            "event_name": event_config["name"],
                            "question": market.get("groupItemTitle") or market.get("question", "")[:50],
                            "category": event_config["name"],
                            "stocks": event_config.get("stocks", []),
                            "notes": event_config.get("notes", ""),
                            "current_prob": round(yes_price * 100, 1),
                            "day_change": round((market.get("oneDayPriceChange") or 0) * 100, 2),
                            "week_change": round((market.get("oneWeekPriceChange") or 0) * 100, 2),
                            "volume_24h": market.get("volume24hr", 0) or 0,
                            "slug": market.get("slug"),
                        })
        except Exception as e:
            print(f"Error fetching {slug}: {e}")
    
    return results

def fetch_keyword_markets(config: dict) -> List[dict]:
    """Fetch markets matching keywords"""
    results = []
    
    try:
        resp = requests.get(f"{API_BASE}/markets?limit=300&active=true&closed=false", timeout=30)
        resp.raise_for_status()
        markets = resp.json()
    except Exception as e:
        print(f"Error fetching markets: {e}")
        return results
    
    exclude_keywords = [kw.lower() for kw in config.get("exclude_keywords", [])]
    
    for market in markets:
        question = market.get("question", "")
        text = question.lower()
        
        # Check exclusions
        if any(ex in text for ex in exclude_keywords):
            continue
        
        # Check volume
        volume_24h = market.get("volume24hr", 0) or 0
        if volume_24h < config.get("alert_thresholds", {}).get("min_volume_24h", 10000):
            continue
        
        # Match keywords
        for cat_name, cat_config in config.get("keyword_watchlist", {}).items():
            keywords = cat_config.get("keywords", [])
            
            for keyword in keywords:
                if keyword.lower() in text:
                    try:
                        prices = json.loads(market.get("outcomePrices", "[]"))
                        yes_price = float(prices[0]) if prices else 0
                    except:
                        yes_price = 0
                    
                    results.append({
                        "id": market.get("id"),
                        "event_name": cat_name,
                        "question": question[:60],
                        "category": cat_name,
                        "stocks": cat_config.get("stocks", []),
                        "current_prob": round(yes_price * 100, 1),
                        "day_change": round((market.get("oneDayPriceChange") or 0) * 100, 2),
                        "week_change": round((market.get("oneWeekPriceChange") or 0) * 100, 2),
                        "volume_24h": volume_24h,
                        "slug": market.get("slug"),
                    })
                    break
            else:
                continue
            break
    
    return results

def generate_report(config: dict) -> str:
    """Generate the daily signal report"""
    init_db()
    
    print("Fetching tracked events...")
    tracked = fetch_tracked_events(config)
    print(f"Found {len(tracked)} tracked market outcomes")
    
    print("Fetching keyword-matched markets...")
    keyword_matched = fetch_keyword_markets(config)
    print(f"Found {len(keyword_matched)} keyword-matched markets")
    
    # Combine and dedupe
    all_markets = tracked + keyword_matched
    seen_ids = set()
    unique_markets = []
    for m in all_markets:
        if m["id"] not in seen_ids:
            seen_ids.add(m["id"])
            unique_markets.append(m)
    
    # Classify by change magnitude
    major_threshold = config.get("alert_thresholds", {}).get("major_change", 5.0)
    notable_threshold = config.get("alert_thresholds", {}).get("notable_change", 2.0)
    
    major = []
    notable = []
    stable = []
    
    for m in unique_markets:
        abs_change = abs(m["day_change"])
        if abs_change >= major_threshold:
            major.append(m)
        elif abs_change >= notable_threshold:
            notable.append(m)
        else:
            stable.append(m)
    
    # Sort by change magnitude
    major = sorted(major, key=lambda x: abs(x["day_change"]), reverse=True)
    notable = sorted(notable, key=lambda x: abs(x["day_change"]), reverse=True)
    stable = sorted(stable, key=lambda x: x["current_prob"], reverse=True)
    
    # Format report
    lines = []
    now = datetime.now()
    lines.append(f"🎰 **Polymarket 信号** | {now.strftime('%Y-%m-%d %H:%M')}")
    lines.append("")
    
    if major:
        lines.append("🔴 **重大变化 (>5%)**")
        for m in major[:5]:
            sign = "+" if m["day_change"] > 0 else ""
            emoji = "📈" if m["day_change"] > 0 else "📉"
            lines.append(f"{emoji} **{m['event_name']}**: {m['question']}")
            lines.append(f"   概率: {m['current_prob']}% ({sign}{m['day_change']}%)")
            lines.append(f"   关联: {', '.join(m['stocks'][:4])}")
            lines.append("")
    else:
        lines.append("🔴 **重大变化**: 无")
        lines.append("")
    
    if notable:
        lines.append("🟡 **值得关注 (2-5%)**")
        for m in notable[:5]:
            sign = "+" if m["day_change"] > 0 else ""
            lines.append(f"• {m['event_name']}: {m['question'][:40]}...")
            lines.append(f"  {m['current_prob']}% ({sign}{m['day_change']}%) | {', '.join(m['stocks'][:3])}")
        lines.append("")
    
    if stable:
        lines.append("📊 **追踪中 (稳定)**")
        for m in stable[:8]:
            lines.append(f"• {m['event_name']}: {m['question'][:35]}... → {m['current_prob']}%")
        lines.append("")
    
    lines.append(f"**总计**: {len(unique_markets)} 个市场 | 重大: {len(major)} | 关注: {len(notable)}")
    
    # Save to history
    today = now.strftime("%Y-%m-%d")
    signals = {
        "major": major,
        "notable": notable,
        "stable": stable,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    with open(HISTORY_PATH / f"signals_{today}.json", "w") as f:
        json.dump(signals, f, indent=2, ensure_ascii=False)
    
    return "\n".join(lines)

def main():
    config = load_config()
    report = generate_report(config)
    print(report)

if __name__ == "__main__":
    main()
