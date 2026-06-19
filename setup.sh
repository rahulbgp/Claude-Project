#!/usr/bin/env bash
set -e

echo "==> Setting up Loan Eligibility AI Agent"

python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "==> Python $python_version"

if [ ! -d ".venv" ]; then
  echo "==> Creating virtual environment"
  python3 -m venv .venv
fi

source .venv/bin/activate

echo "==> Installing dependencies"
pip install --upgrade pip -q
pip install -r requirements.txt -q

if [ ! -f ".env" ]; then
  echo "==> Creating .env from .env.example"
  cp .env.example .env
  echo "    !! Add your ANTHROPIC_API_KEY to .env before running"
fi

mkdir -p logs reports

echo ""
echo "==> Setup complete!"
echo "    1. Edit .env and set ANTHROPIC_API_KEY"
echo "    2. source .venv/bin/activate"
echo "    3. streamlit run frontend/app.py"
