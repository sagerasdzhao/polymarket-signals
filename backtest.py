#!/usr/bin/env python3
"""
Backtest Polymarket signals against actual stock performance
"""

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple
import requests

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "data" / "markets.db"
BACKTEST_PATH = BASE_DIR / "data" / "backtest"

# Alpha Vantage or Yahoo Finance for stock data
# For simplicity, we'll use a mock or yfinance

def get_stock_returns(ticker: str, start_date: str, end_date: str) -> Dict[str, float]:
    """
    Get stock returns for a period
    Returns: {date: return_pct}
    
    Note: In production, use yfinance or Alpha Vantage API
    """
    try:
        import yfinance as yf
        stock = yf.Ticker(ticker)
        hist = stock.history(start=start_date, end=end_date)
        
        if hist.empty:
            return {}
        
        returns = {}
        prev_close = None
        for date, row in hist.iterrows():
            if prev_close:
                daily_return = (row['Close'] - prev_close) / prev_close * 100
                returns[date.strftime('%Y-%m-%d')] = round(daily_return, 2)
            prev_close = row['Close']
        
        return returns
    except ImportError:
        print("yfinance not installed. Install with: pip install yfinance")
        return {}
    except Exception as e:
        print(f"Error fetching {ticker}: {e}")
        return {}

def analyze_signal_performance(signals_file: str) -> dict:
    """
    Analyze how well Polymarket signals predicted stock moves
    """
    with open(signals_file) as f:
        signals = json.load(f)
    
    signal_date = signals.get("timestamp", "")[:10]
    if not signal_date:
        return {"error": "No timestamp in signals"}
    
    # Look at next 1-5 days after signal
    results = {
        "signal_date": signal_date,
        "major_signals": [],
        "hit_rate": 0,
        "avg_return": 0
    }
    
    # Analyze major signals
    for signal in signals.get("major", []):
        stocks = signal.get("affected_stocks", [])
        direction = "bullish" if signal["day_change"] > 0 else "bearish"
        
        for ticker in stocks[:3]:  # Top 3 stocks per signal
            # Get 5-day forward returns
            end_date = (datetime.strptime(signal_date, '%Y-%m-%d') + timedelta(days=7)).strftime('%Y-%m-%d')
            returns = get_stock_returns(ticker, signal_date, end_date)
            
            if returns:
                total_return = sum(returns.values())
                
                # Did the signal direction match stock move?
                correct = (direction == "bullish" and total_return > 0) or \
                         (direction == "bearish" and total_return < 0)
                
                results["major_signals"].append({
                    "question": signal["question"][:50],
                    "ticker": ticker,
                    "signal_direction": direction,
                    "prob_change": signal["day_change"],
                    "5d_stock_return": round(total_return, 2),
                    "correct_direction": correct
                })
    
    # Calculate hit rate
    if results["major_signals"]:
        correct_count = sum(1 for s in results["major_signals"] if s["correct_direction"])
        results["hit_rate"] = round(correct_count / len(results["major_signals"]) * 100, 1)
        results["avg_return"] = round(
            sum(s["5d_stock_return"] for s in results["major_signals"]) / len(results["major_signals"]), 
            2
        )
    
    return results

def run_historical_backtest(days: int = 30) -> dict:
    """
    Run backtest on all historical signal files
    """
    BACKTEST_PATH.mkdir(parents=True, exist_ok=True)
    history_path = BASE_DIR / "data" / "history"
    
    all_results = {
        "total_signals": 0,
        "correct_signals": 0,
        "by_category": {},
        "by_stock": {},
        "details": []
    }
    
    # Find all signal files
    signal_files = sorted(history_path.glob("signals_*.json"))
    
    for sf in signal_files[-days:]:  # Last N days
        result = analyze_signal_performance(str(sf))
        all_results["details"].append(result)
        
        for sig in result.get("major_signals", []):
            all_results["total_signals"] += 1
            if sig.get("correct_direction"):
                all_results["correct_signals"] += 1
            
            # Track by stock
            ticker = sig["ticker"]
            if ticker not in all_results["by_stock"]:
                all_results["by_stock"][ticker] = {"total": 0, "correct": 0, "returns": []}
            all_results["by_stock"][ticker]["total"] += 1
            if sig.get("correct_direction"):
                all_results["by_stock"][ticker]["correct"] += 1
            all_results["by_stock"][ticker]["returns"].append(sig["5d_stock_return"])
    
    # Calculate overall hit rate
    if all_results["total_signals"] > 0:
        all_results["overall_hit_rate"] = round(
            all_results["correct_signals"] / all_results["total_signals"] * 100, 1
        )
    
    # Calculate per-stock stats
    for ticker, stats in all_results["by_stock"].items():
        if stats["total"] > 0:
            stats["hit_rate"] = round(stats["correct"] / stats["total"] * 100, 1)
            stats["avg_return"] = round(sum(stats["returns"]) / len(stats["returns"]), 2)
    
    return all_results

def generate_backtest_report() -> str:
    """Generate a readable backtest report"""
    results = run_historical_backtest(30)
    
    lines = []
    lines.append("📊 **Polymarket 信号回测报告**")
    lines.append("")
    lines.append(f"**总体表现** (过去30天)")
    lines.append(f"• 总信号数: {results['total_signals']}")
    lines.append(f"• 方向正确: {results['correct_signals']}")
    lines.append(f"• 准确率: {results.get('overall_hit_rate', 'N/A')}%")
    lines.append("")
    
    if results["by_stock"]:
        lines.append("**按股票表现**")
        sorted_stocks = sorted(
            results["by_stock"].items(), 
            key=lambda x: x[1].get("total", 0), 
            reverse=True
        )
        for ticker, stats in sorted_stocks[:10]:
            lines.append(f"• {ticker}: {stats['hit_rate']}% 准确率 ({stats['total']}个信号), 平均回报: {stats['avg_return']}%")
    
    return "\n".join(lines)

if __name__ == "__main__":
    # Run backtest
    report = generate_backtest_report()
    print(report)
