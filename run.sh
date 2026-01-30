#!/bin/bash
# Run Polymarket signal generator
cd "$(dirname "$0")"
source venv/bin/activate
python polymarket.py
