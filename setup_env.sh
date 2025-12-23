#!/bin/bash
# Forex Bot - Virtual Environment Setup Script
# This script creates a clean Python environment and installs all dependencies

set -e  # Exit on error

echo "🚀 Forex Bot - Environment Setup"
echo "=================================="
echo ""

# Step 1: Create virtual environment
echo "📦 Step 1: Creating virtual environment..."
python3 -m venv forex_env
echo "✅ Virtual environment created: forex_env/"
echo ""

# Step 2: Activate and upgrade pip
echo "🔧 Step 2: Upgrading pip..."
source forex_env/bin/activate
pip install --upgrade pip > /dev/null 2>&1
echo "✅ Pip upgraded"
echo ""

# Step 3: Install core dependencies
echo "📚 Step 3: Installing dependencies..."
echo "   This may take 2-3 minutes..."
pip install -r requirements.txt > /dev/null 2>&1
echo "✅ Core dependencies installed"
echo ""

# Step 4: Install backtest dependencies
echo "📊 Step 4: Installing backtest tools..."
pip install yfinance pandas numpy matplotlib > /dev/null 2>&1
echo "✅ Backtest tools installed"
echo ""

# Step 5: Verify installation
echo "🔍 Step 5: Verifying installation..."
python -c "import pandas; import yfinance; import numpy; print('✅ All packages working')"
echo ""

# Done
echo "=================================="
echo "✅ Setup complete!"
echo ""
echo "To activate the environment:"
echo "   source forex_env/bin/activate"
echo ""
echo "To run backtest:"
echo "   python backtest_edge.py"
echo ""
echo "To deactivate when done:"
echo "   deactivate"
echo "=================================="
