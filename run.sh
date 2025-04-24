#!/bin/bash

# Exit on error
set -e

# Activate virtual environment
source myenv/bin/activate

# Run the script
echo "🚀 Starting trading charts script..."
python hei_chart.py

# Keep the script running
while true; do
    echo "⏰ Waiting for next update..."
    sleep 3600  # Wait for 1 hour
    echo "🔄 Running update..."
    python hei_chart.py
done 