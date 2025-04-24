#!/bin/bash

# Exit on error
set -e

echo "📦 Setting up trading charts deployment..."

# Create directory structure
mkdir -p assets logs charts

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "🔧 Creating virtual environment..."
    python -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install/upgrade pip
python -m pip install --upgrade pip

# Install requirements
echo "📚 Installing dependencies..."
pip install -r requirements.txt

# Check for .env file
if [ ! -f ".env" ]; then
    echo "⚙️ Creating .env file from template..."
    cp .env.example .env
    echo "⚠️ Please edit .env file with your configuration"
fi

# Check for credentials.json
if [ ! -f "credentials.json" ]; then
    echo "⚠️ credentials.json not found!"
    echo "Please place your Google Sheets credentials file in the project directory"
fi

# Check for logo file
if [ ! -f "assets/utgl.png" ]; then
    if [ -f "utgl.png" ]; then
        echo "🖼️ Moving logo to assets directory..."
        cp utgl.png assets/utgl.png
    else
        echo "⚠️ utgl.png not found!"
        echo "Please place your logo file in the project directory or assets directory"
    fi
fi

# Set file permissions
chmod +x run.sh
chmod 600 .env
chmod 600 credentials.json

echo "✅ Setup complete!"
echo "Please ensure:"
echo "1. .env file is configured with your settings"
echo "2. credentials.json is in place"
echo "3. utgl.png is in the assets directory"
echo ""
echo "To run the script:"
echo "./run.sh" 