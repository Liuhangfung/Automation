# Trading Analysis Charts

Automated trading analysis tool that generates and distributes performance charts via Telegram.

## Features

- Fetches trading data from Google Sheets
- Generates performance charts for multiple trading strategies
- Automatically sends charts to Telegram group
- Supports multiple timeframes (3m and 5m)
- Filters data for specific date ranges

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Configure environment variables:
- Copy `.env.example` to `.env`
- Update the following variables:
  - `TELEGRAM_BOT_TOKEN`: Your Telegram bot token
  - `TELEGRAM_CHAT_ID`: Your Telegram group chat ID
  - `SPREADSHEET_ID`: Your Google Sheets document ID

3. Set up Google Sheets credentials:
- Place your `credentials.json` file in the project root
- Share your Google Sheet with the service account email

## Usage

Run the script to generate and send charts:
```bash
python hei_chart.py
```

## Directory Structure

```
hei_chart/
├── hei_chart.py      # Main script
├── credentials.json  # Google Sheets credentials
├── .env             # Environment variables
├── requirements.txt # Dependencies
└── charts/         # Generated charts directory
```

## Environment Variables

- `TELEGRAM_BOT_TOKEN`: Telegram bot authentication token
- `TELEGRAM_CHAT_ID`: Target Telegram chat/group ID
- `SPREADSHEET_ID`: Google Sheets document ID
- `GOOGLE_CREDENTIALS_PATH`: Path to Google credentials file
- `CHARTS_DIR`: Directory for generated charts
- `LOG_LEVEL`: Logging level (default: INFO) 