#!/bin/bash

# Exit on error
set -e

echo "🚀 Starting deployment..."

# Update from git
echo "📥 Pulling latest changes..."
git pull origin main

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "🔧 Creating virtual environment..."
    python -m venv venv
fi

# Activate virtual environment
echo "🔌 Activating virtual environment..."
source venv/bin/activate

# Install/update dependencies
echo "📦 Installing dependencies..."
pip install -r requirements.txt

# Create necessary directories
echo "📁 Creating directories..."
mkdir -p charts logs

# Copy environment file if it doesn't exist
if [ ! -f ".env" ]; then
    echo "⚙️ Setting up environment file..."
    cp .env.example .env
    echo "⚠️ Please update .env with your configuration"
fi

# Check for credentials file
if [ ! -f "credentials.json" ]; then
    echo "⚠️ Warning: credentials.json not found"
    echo "Please place your Google Sheets credentials.json file in the project root"
fi

echo "✅ Deployment complete!"
echo "To start the script, run: ./run.sh" 