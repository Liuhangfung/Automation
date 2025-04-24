#!/bin/bash

# Change to the script directory
cd "$(dirname "$0")"

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Run the script
python hei_chart.py

# Deactivate virtual environment
if [ -d "venv" ]; then
    deactivate
fi 