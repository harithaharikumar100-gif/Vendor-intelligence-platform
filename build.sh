#!/usr/bin/env bash
# Exit on error
set -euo pipefail
cd "$(dirname "$0")"

echo "📦 Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo "🎨 Building React Frontend..."
cd frontend
npm ci --no-audit --no-fund
npm run build
cd ..

echo "✅ Build completed successfully!"
