import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import os
import numpy as np
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import pickle
from telegram import Bot
import asyncio
import logging
import matplotlib.dates as mdates
from google.oauth2 import service_account
from googleapiclient.errors import HttpError
import urllib.parse
import sys
from dotenv import load_dotenv
from pathlib import Path
import logging.handlers
import shutil

# Load environment variables
load_dotenv()

# Configure logging with rotation
BASE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = BASE_DIR / 'assets'
LOG_DIR = BASE_DIR / 'logs'
CHARTS_DIR = BASE_DIR / 'charts'

# Create necessary directories
ASSETS_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)
CHARTS_DIR.mkdir(exist_ok=True)

# Update the logo path configuration
LOGO_PATH = os.getenv('LOGO_PATH', str(ASSETS_DIR / 'utgl.png'))

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.handlers.RotatingFileHandler(
            LOG_DIR / 'hei_chart.log',
            maxBytes=1024*1024,  # 1MB
            backupCount=5
        ),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Configuration from environment variables
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
SPREADSHEET_ID = os.getenv('SPREADSHEET_ID')
CREDENTIALS_PATH = os.getenv('GOOGLE_CREDENTIALS_PATH', str(BASE_DIR / 'credentials.json'))

# Ensure required environment variables are set
required_env_vars = ['TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID', 'SPREADSHEET_ID']
missing_vars = [var for var in required_env_vars if not os.getenv(var)]
if missing_vars:
    raise EnvironmentError(f"Missing required environment variables: {', '.join(missing_vars)}")

# Create necessary directories
CHARTS_DIR.mkdir(exist_ok=True)

async def send_telegram_message(message):
    """Send a message to Telegram."""
    try:
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        logger.info("Message sent successfully")
    except Exception as e:
        logger.error(f"Error sending message: {str(e)}")

async def send_telegram_photo(photo_path, caption=None):
    """Send a photo to Telegram."""
    try:
        logger.info(f"Attempting to send photo: {photo_path}")
        if not os.path.exists(photo_path):
            logger.error(f"File not found: {photo_path}")
            return
            
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        with open(photo_path, 'rb') as photo:
            await bot.send_photo(
                chat_id=TELEGRAM_CHAT_ID,
                photo=photo,
                caption=caption
            )
        logger.info(f"Photo {photo_path} sent successfully")
    except Exception as e:
        logger.error(f"Error sending photo {photo_path}: {str(e)}")

# If modifying these scopes, delete the file token.pickle.
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive.readonly'
]

def get_google_sheets_service():
    """Get or create Google Sheets service."""
    creds = None
    
    # The file token.pickle stores the user's access and refresh tokens
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
            
    # If there are no (valid) credentials available, let the user log in
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
            
        # Save the credentials for the next run
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)

    return build('sheets', 'v4', credentials=creds)

def excel_number_to_datetime(excel_date, excel_time=0):
    """Convert Excel serial number date and time to datetime."""
    from datetime import datetime, timedelta
    
    # Excel's date system has two epochs:
    # 1. 1900 system: day 1 is 1/1/1900 (most common)
    # 2. 1904 system: day 1 is 1/1/1904
    
    # We'll use the 1900 system
    excel_epoch = datetime(1899, 12, 30)  # Excel's epoch is actually 12/30/1899
    
    try:
        # Convert Excel date (days since epoch)
        if isinstance(excel_date, str):
            excel_date = float(excel_date)
        days = timedelta(days=int(excel_date))
        
        # Convert Excel time (fraction of a day)
        if isinstance(excel_time, str):
            excel_time = float(excel_time) if excel_time else 0
        seconds = int(excel_time * 24 * 3600)  # Convert to seconds
        time_delta = timedelta(seconds=seconds)
        
        # Combine date and time
        return excel_epoch + days + time_delta
    except Exception as e:
        print(f"Error converting Excel date/time: {excel_date}, {excel_time}")
        print(f"Error details: {str(e)}")
        return None

def load_data_from_sheets(SPREADSHEET_ID, RANGE_NAME):
    """Load data from Google Sheets."""
    try:
        # Check if credentials file exists
        if not os.path.exists(CREDENTIALS_PATH):
            raise FileNotFoundError(f"Credentials file not found at {CREDENTIALS_PATH}")

        # Load credentials with broader scope
        credentials = service_account.Credentials.from_service_account_file(
            CREDENTIALS_PATH,
            scopes=[
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/drive.readonly'
            ]
        )

        # Build the service
        service = build('sheets', 'v4', credentials=credentials)

        # Call the Sheets API
        sheet = service.spreadsheets()
        
        print(f"Requesting range: {RANGE_NAME}")  # Debug print
        
        result = sheet.values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=RANGE_NAME,
            valueRenderOption='UNFORMATTED_VALUE'
        ).execute()
        values = result.get('values', [])

        if not values:
            print('No data found.')
            return pd.DataFrame()

        # Get headers and handle duplicates
        headers = values[0]
        unique_headers = []
        header_counts = {}
        
        # Keep track of which columns to drop
        columns_to_drop = []
        
        for i, header in enumerate(headers):
            if not header:  # Skip empty headers
                unique_headers.append(f"Column_{i}")
                continue
                
            if header in header_counts:
                header_counts[header] += 1
                # For Date and Time columns, use number suffix
                if header in ['Date', 'Time']:
                    unique_headers.append(f"{header}{header_counts[header]}")
                    columns_to_drop.append(i)
                else:
                    unique_headers.append(f"{header}_{header_counts[header]}")
            else:
                header_counts[header] = 1
                unique_headers.append(header)

        # Print column names for debugging
        print("Original columns:", headers)
        print("Unique columns:", unique_headers)
        
        # Convert to DataFrame with unique column names
        df = pd.DataFrame(values[1:], columns=unique_headers)
        
        # Drop duplicate Date and Time columns
        columns_to_keep = [col for i, col in enumerate(unique_headers) if i not in columns_to_drop]
        df = df[columns_to_keep]
        
        # Replace empty strings with NaN
        df = df.replace('', pd.NA)
        
        # Drop rows where Date or Time is NaN
        df = df.dropna(subset=['Date', 'Time'])
        
        # Print first few rows for debugging
        print("\nFirst few rows of data:")
        print(df[['Date', 'Time']].head())
        
        # Convert Excel dates to datetime
        try:
            # Convert Date and Time columns to proper datetime
            df['DateTime'] = df.apply(
                lambda row: excel_number_to_datetime(
                    row['Date'],
                    row['Time'] if pd.notna(row['Time']) else 0
                ),
                axis=1
            )
            
            # Print converted dates for verification
            print("\nConverted dates:")
            print(df[['Date', 'Time', 'DateTime']].head())
            
        except Exception as e:
            print(f"Error during date conversion: {str(e)}")
            raise
        
        # Convert Est. Fee to numeric, removing any currency symbols and commas
        if 'Est. Fee' in df.columns:
            df['Est. Fee'] = pd.to_numeric(df['Est. Fee'].astype(str).str.replace('$', '').str.replace(',', ''), errors='coerce')
            # Fill NaN values with 0 for Est. Fee
            df['Est. Fee'] = df['Est. Fee'].fillna(0)
        
        # Ensure DateTime column exists and is not null
        if 'DateTime' not in df.columns or df['DateTime'].isna().all():
            raise ValueError("DateTime column is missing or contains no valid dates")
        
        return df

    except HttpError as err:
        print(f"An error occurred: {err}")
        raise
    except Exception as e:
        print(f"Error processing data: {str(e)}")
        if 'df' in locals():
            print("DataFrame columns:", df.columns.tolist())
            print("\nSample data:")
            print(df.head())
        raise

def add_utg_logo(fig, position='lower right', ax=None):
    """Add UTG logo to the figure."""
    try:
        # Check if logo file exists
        if not os.path.exists(LOGO_PATH):
            logger.warning(f"Logo file not found at {LOGO_PATH}")
            return
            
        # Load and add the logo
        logo = plt.imread(LOGO_PATH)
        
        # Create a new axes for the logo
        if position == 'lower right':
            logo_ax = fig.add_axes([0.85, 0.02, 0.1, 0.1])
        elif position == 'upper right':
            logo_ax = fig.add_axes([0.85, 0.88, 0.1, 0.1])
        elif position == 'bar chart':
            y_min, y_max = ax.get_ylim()
            total_height = y_max - y_min
            y_pos = 650 / total_height
            logo_ax = fig.add_axes([0.85, y_pos, 0.1, 0.1])
        elif position == 'center':
            logo_ax = fig.add_axes([0.45, 0.45, 0.1, 0.1])
            
        # Display the logo
        logo_ax.imshow(logo)
        logo_ax.axis('off')
        
    except Exception as e:
        logger.error(f"Error adding logo: {str(e)}")

def create_win_rate_chart(df, title):
    # Calculate win rate statistics
    total_trades = len(df)
    winning_trades = len(df[df['Win Rate'] == 'Yes'])
    losing_trades = total_trades - winning_trades
    win_rate = (winning_trades / total_trades) * 100
    
    # Create figure with dark background
    plt.style.use('dark_background')
    fig = plt.figure(figsize=(12, 7))
    fig.patch.set_facecolor('#000000FA')  # 98% opaque black
    
    # Add padding at the top for title
    gs = fig.add_gridspec(2, 2, height_ratios=[0.15, 1], width_ratios=[2, 1], wspace=0.1, hspace=0)
    
    # Create title subplot
    ax_title = fig.add_subplot(gs[0, :])
    ax_title.axis('off')
    ax_title.set_facecolor('#000000FA')  # 98% opaque black
    ax_title.text(
        0.5, 0.2,
        f'{title} - Trading Statistics',
        ha='center',
        va='center',
        fontsize=14,
        fontweight='bold',
        color='white'
    )
    
    # Create main pie chart subplot
    ax_pie = fig.add_subplot(gs[1, 0])
    ax_pie.set_facecolor('#000000FA')  # 98% opaque black
    
    # Create info subplot for statistics
    ax_info = fig.add_subplot(gs[1, 1])
    ax_info.set_facecolor('#000000FA')  # 98% opaque black
    ax_info.axis('off')
    
    # Define colors and style
    colors = ['#00B800', '#FF0000']  # Softer green and red for trading
    
    # Create pie chart with enhanced styling
    wedges, texts, autotexts = ax_pie.pie(
        x=[winning_trades, losing_trades],
        colors=colors,
        autopct='%1.1f%%',
        startangle=90,
        labels=['', ''],
        pctdistance=0.75,
        wedgeprops=dict(width=0.7, edgecolor='none', linewidth=0)
    )
    
    # Customize percentage labels
    plt.setp(autotexts, size=11, weight="bold", color="white")
    
    # Add center text showing total trades
    center_text = f'Total Trades\n{total_trades}'
    ax_pie.text(0, 0, center_text,
        ha='center', va='center',
        fontsize=12, fontweight='bold',
        color='white'
    )
    
    # Add statistics in the info subplot
    info_text = (
        f"Trading Performance\n"
        f"━━━━━━━━━━━━━━━━━\n\n"
        f"Win Rate: {win_rate:.1f}%\n\n"
        f"Winning Trades: {winning_trades}\n"
        f"Losing Trades: {losing_trades}\n"
        f"Total Trades: {total_trades}"
    )
    
    ax_info.text(
        0, 0.5, info_text,
        ha='left', va='center',
        fontsize=11,
        fontfamily='monospace',
        linespacing=2,
        color='white'
    )
    
    # Before saving, add the logo
    add_utg_logo(fig, 'lower right')
    
    # Save the chart
    filename = f'win_rate_{title.replace(" ", "_").replace("(", "").replace(")", "")}.png'
    plt.savefig(
        filename,
        bbox_inches='tight',
        dpi=300,
        facecolor='#000000FA',
        edgecolor='none',
        transparent=True
    )
    plt.close()
    return filename

def create_fee_distribution_chart(df, title):
    # Set the style
    plt.style.use('dark_background')
    
    # Create figure and axis with dark background
    fig, ax = plt.subplots(figsize=(12, 6))
    fig.patch.set_facecolor('#000000FA')  # 98% opaque black
    ax.set_facecolor('#000000FA')  # 98% opaque black
    
    # Calculate bin edges at $2 intervals
    min_fee = np.floor(df['Est. Fee'].min())
    max_fee = np.ceil(df['Est. Fee'].max())
    bins = np.arange(min_fee, max_fee + 2, 2)  # $2 intervals
    
    # Create the histogram with custom colors and style
    sns.histplot(
        data=df,
        x='Est. Fee',
        bins=bins,
        kde=True,
        ax=ax,
        color='#00B800',  # Softer green for positive fees
        edgecolor='#404040',
        alpha=0.7
    )
    
    # Add KDE line with custom style
    kde = sns.kdeplot(data=df, x='Est. Fee', ax=ax, color='#FFD700', linewidth=2, alpha=0.7)  # Gold
    
    # Calculate average fee
    avg_fee = df['Est. Fee'].mean()
    
    # Add vertical line for average fee
    ax.axvline(x=avg_fee, color='#00FFFF', linestyle='--', linewidth=2, alpha=0.7)  # Cyan
    
    # Add average fee annotation with dark background
    bbox_props = dict(boxstyle='round,pad=0.5', facecolor='#000000FA', edgecolor='#404040', alpha=0.98)
    ax.annotate(
        f'Avg Fee: ${avg_fee:.2f}',
        xy=(avg_fee, ax.get_ylim()[1] * 0.7),
        xytext=(avg_fee + 1, ax.get_ylim()[1] * 0.8),
        bbox=bbox_props,
        color='white',
        arrowprops=dict(
            facecolor='#00FFFF',
            shrink=0.05,
            width=2,
            headwidth=8,
            headlength=10,
            alpha=0.7
        ),
        fontsize=10,
        fontweight='bold'
    )
    
    # Add total trades count in top right
    total_trades = len(df)
    ax.text(
        0.95, 0.95,
        f'Total Trades: {total_trades}',
        transform=ax.transAxes,
        ha='right',
        va='top',
        fontsize=10,
        fontweight='bold',
        color='white'
    )
    
    # Customize the plot
    ax.set_title(f'{title} - Fee Distribution', pad=20, fontsize=12, fontweight='bold', color='white')
    ax.set_xlabel('Estimated Fee (US$)', fontsize=10, color='white')
    ax.set_ylabel('Frequency', fontsize=10, color='white')
    
    # Set x-axis ticks at $2 intervals with better formatting
    xticks = np.arange(min_fee, max_fee + 2, 2)
    plt.xticks(xticks, [f'${x:g}' for x in xticks], rotation=0, color='white')
    
    # Set reasonable x-axis limits
    ax.set_xlim(min_fee - 0.5, min(max_fee + 0.5, 30))
    
    # Customize grid
    ax.grid(True, linestyle='--', alpha=0.1, color='white')
    
    # Add a note if there are fees beyond the visible range
    if max_fee > 30:
        ax.text(
            0.95, 0.85,
            f'Note: Some fees extend beyond ${30:g}',
            transform=ax.transAxes,
            ha='right',
            va='top',
            fontsize=8,
            fontstyle='italic',
            color='white'
        )
    
    # Set spine colors
    for spine in ax.spines.values():
        spine.set_color('#404040')
    
    # Adjust layout to prevent label cutoff
    plt.tight_layout()
    
    # Before saving, add the logo
    add_utg_logo(fig, 'upper right')
    
    # Save the chart
    filename = f'fee_distribution_{title.replace(" ", "_").replace("(", "").replace(")", "")}.png'
    plt.savefig(
        filename,
        bbox_inches='tight',
        dpi=300,
        facecolor='#000000FA',
        edgecolor='none',
        transparent=True
    )
    plt.close()
    return filename

def create_combined_win_rate_chart(df_3m, df_5m, title_prefix):
    """Create a combined win rate chart for 3m and 5m data."""
    # Create figure with dark background
    plt.style.use('dark_background')
    fig = plt.figure(figsize=(15, 8))
    fig.patch.set_facecolor('#000000FA')  # 98% opaque black
    
    # Create two subplots side by side
    gs = fig.add_gridspec(2, 2, height_ratios=[0.15, 1], width_ratios=[1, 1], wspace=0.2, hspace=0)
    
    # Create title
    ax_title = fig.add_subplot(gs[0, :])
    ax_title.axis('off')
    ax_title.set_facecolor('#000000FA')  # 98% opaque black
    ax_title.text(
        0.5, 0.2,
        f'{title_prefix} - Trading Statistics Comparison',
        ha='center',
        va='center',
        fontsize=16,
        fontweight='bold',
        color='white'
    )
    
    # Create subplots for 3m and 5m
    for i, (df, timeframe) in enumerate([(df_3m, '3m'), (df_5m, '5m')]):
        # Calculate statistics
        total_trades = len(df)
        
        # Check if Win Rate column exists and handle missing data
        if 'Win Rate' in df.columns:
            winning_trades = len(df[df['Win Rate'] == 'Yes'])
        else:
            print(f"Win Rate column not found in {timeframe} data")
            winning_trades = 0
            
        losing_trades = total_trades - winning_trades
        win_rate = (winning_trades / total_trades) * 100 if total_trades > 0 else 0
        
        # Skip empty dataframes
        if total_trades == 0:
            print(f"No data available for {timeframe}")
            continue
        
        # Create pie chart subplot
        ax_pie = fig.add_subplot(gs[1, i])
        ax_pie.set_facecolor('#000000FA')  # 98% opaque black
        
        # Add timeframe title
        ax_pie.text(
            0.5, 1.1,
            f'{timeframe} Trading Performance',
            ha='center',
            va='bottom',
            fontsize=14,
            fontweight='bold',
            color='white',
            transform=ax_pie.transAxes
        )
        
        # Define colors
        colors = ['#00B800', '#FF0000']  # Softer green and red for trading
        
        # Create pie chart
        wedges, texts, autotexts = ax_pie.pie(
            x=[winning_trades, losing_trades],
            colors=colors,
            autopct='%1.1f%%',
            startangle=90,
            labels=['Win', 'Loss'],
            pctdistance=0.75,
            wedgeprops=dict(width=0.7, edgecolor='none', linewidth=0),
            textprops={'fontsize': 12, 'fontweight': 'bold', 'color': 'white'}
        )
        
        # Customize percentage labels
        plt.setp(autotexts, size=12, weight="bold", color="white")
        
        # Add center text without box
        center_text = f'Total\nTrades\n{total_trades}'
        ax_pie.text(0, 0, center_text,
            ha='center',
            va='center',
            fontsize=13,
            fontweight='bold',
            color='white'
        )
        
        # Add statistics in a box
        stats_text = (
            f"Win Rate: {win_rate:.1f}%\n"
            f"Winning Trades: {winning_trades}\n"
            f"Losing Trades: {losing_trades}"
        )
        
        # Create a box with statistics
        bbox_props = dict(
            boxstyle='round,pad=0.8',
            facecolor='#000000FA',  # 98% opaque black
            edgecolor='#404040',
            alpha=0.98
        )
        
        ax_pie.text(
            0.98, 0.02,
            stats_text,
            ha='right',
            va='bottom',
            fontsize=12,
            fontweight='bold',
            color='white',
            transform=ax_pie.transAxes,
            bbox=bbox_props,
            linespacing=1.5
        )
    
    # Before saving, add the logo
    add_utg_logo(fig, 'lower right')
    
    # Save the chart
    filename = f'win_rate_comparison_{title_prefix.replace(" ", "_").replace("(", "").replace(")", "")}.png'
    plt.savefig(
        filename,
        bbox_inches='tight',
        dpi=300,
        facecolor='#000000FA',
        edgecolor='none',
        transparent=True
    )
    plt.close()
    return filename

def create_combined_fee_distribution_chart(df_3m, df_5m, title_prefix):
    """Create a combined fee distribution chart for 3m and 5m data."""
    # Set the style
    plt.style.use('dark_background')
    
    # Create figure with two subplots
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))
    fig.patch.set_facecolor('#000000FA')  # 98% opaque black
    ax1.set_facecolor('#000000FA')  # 98% opaque black
    ax2.set_facecolor('#000000FA')  # 98% opaque black
    
    # Set title
    fig.suptitle(f'{title_prefix} - Fee Distribution Comparison', 
                 fontsize=16, fontweight='bold', y=1.02, color='white')
    
    # Process both timeframes
    for ax, df, timeframe in [(ax1, df_3m, '3m'), (ax2, df_5m, '5m')]:
        # Calculate bin edges
        min_fee = np.floor(df['Est. Fee'].min())
        max_fee = np.ceil(df['Est. Fee'].max())
        bins = np.arange(min_fee, max_fee + 2, 2)
        
        # Create histogram
        sns.histplot(
            data=df,
            x='Est. Fee',
            bins=bins,
            kde=True,
            ax=ax,
            color='#00B800',  # Softer green for positive fees
            edgecolor='#404040',
            alpha=0.7
        )
        
        # Add KDE line
        sns.kdeplot(data=df, x='Est. Fee', ax=ax, color='#FFD700', linewidth=2, alpha=0.7)  # Gold
        
        # Calculate and add average fee
        avg_fee = df['Est. Fee'].mean()
        ax.axvline(x=avg_fee, color='#00FFFF', linestyle='--', linewidth=2, alpha=0.7)  # Cyan
        
        # Add average fee annotation with arrow
        y_max = ax.get_ylim()[1]
        ax.annotate(
            f'Average Fee: ${avg_fee:.2f}',
            xy=(avg_fee, y_max * 0.5),
            xytext=(avg_fee + 2, y_max * 0.7),
            fontsize=12,
            fontweight='bold',
            color='white',
            bbox=dict(facecolor='#000000FA', edgecolor='#404040', alpha=0.98),
            arrowprops=dict(
                arrowstyle='->',
                color='#00FFFF',
                lw=2,
                alpha=0.8
            )
        )
        
        # Add timeframe and total trades info
        ax.text(
            0.95, 0.95,
            f'Total Trades: {len(df)}',
            transform=ax.transAxes,
            ha='right',
            va='top',
            fontsize=12,
            fontweight='bold',
            color='white'
        )
        
        # Customize the plot
        ax.set_title(f'{timeframe} Fee Distribution', pad=10, fontsize=14, fontweight='bold', color='white')
        ax.set_xlabel('Estimated Fee (US$)', fontsize=12, color='white')
        ax.set_ylabel('Frequency', fontsize=12, color='white')
        ax.grid(True, linestyle='--', alpha=0.1, color='white')
        ax.tick_params(axis='both', labelsize=10, colors='white')
        
        # Set spine colors
        for spine in ax.spines.values():
            spine.set_color('#404040')
        
        # Set x-axis limits
        ax.set_xlim(min_fee - 0.5, min(max_fee + 0.5, 30))
    
    # Adjust layout
    plt.tight_layout()
    
    # Before saving, add the logo
    add_utg_logo(fig, 'upper right')
    
    # Save the chart
    filename = f'fee_distribution_comparison_{title_prefix.replace(" ", "_").replace("(", "").replace(")", "")}.png'
    plt.savefig(
        filename,
        bbox_inches='tight',
        dpi=300,
        facecolor='#000000FA',
        edgecolor='none',
        transparent=True
    )
    plt.close()
    return filename

def create_gap_tracking_chart(df_3m, df_5m, title_prefix):
    """Create a clean, professional chart tracking cumulative fees over time."""
    plt.style.use('dark_background')
    
    # Create figure
    fig, ax = plt.subplots(figsize=(15, 8))
    fig.patch.set_facecolor('#000000FA')  # 98% opaque black
    ax.set_facecolor('#000000FA')  # 98% opaque black
    
    # Process data
    df_3m = df_3m.sort_values('DateTime')
    df_5m = df_5m.sort_values('DateTime')
    df_3m['Cumulative_Fee'] = df_3m['Est. Fee'].cumsum()
    df_5m['Cumulative_Fee'] = df_5m['Est. Fee'].cumsum()
    
    # Calculate statistics
    trades_3m = len(df_3m)
    trades_5m = len(df_5m)
    total_fee_3m = df_3m['Est. Fee'].sum()
    total_fee_5m = df_5m['Est. Fee'].sum()
    avg_fee_3m = total_fee_3m / trades_3m if trades_3m > 0 else 0
    avg_fee_5m = total_fee_5m / trades_5m if trades_5m > 0 else 0
    
    # Create border effect
    border_color = '#404040'
    for spine in ax.spines.values():
        spine.set_color(border_color)
        spine.set_linewidth(1)
    
    # Plot lines
    line_3m = ax.plot(df_3m['DateTime'], df_3m['Cumulative_Fee'], 
                     color='#00FFFF', linewidth=1.5, label='3m')  # Cyan for 3m
    line_5m = ax.plot(df_5m['DateTime'], df_5m['Cumulative_Fee'], 
                     color='#FF1493', linewidth=1.5, label='5m')  # Pink for 5m
    
    # Add subtle grid
    ax.grid(True, linestyle='-', alpha=0.1, color='white')
    
    # Format axes
    ax.set_xlabel('', fontsize=10)  # Remove x-label as it's redundant
    ax.set_ylabel('Cumulative Fee (US$)', fontsize=10, color='white')
    
    # Format x-axis
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
    ax.tick_params(axis='both', colors='white', labelsize=10)
    
    # Add title
    plt.title(f'{title_prefix} - Cumulative Fee Performance',
              fontsize=14, fontweight='bold', color='white', pad=20)
    
    # Create statistics box
    stats_3m = (
        f'3m Performance\n'
        f'Trades: {trades_3m}\n'
        f'Total: ${total_fee_3m:,.2f}\n'
        f'Avg: ${avg_fee_3m:.2f}'
    )
    
    stats_5m = (
        f'5m Performance\n'
        f'Trades: {trades_5m}\n'
        f'Total: ${total_fee_5m:,.2f}\n'
        f'Avg: ${avg_fee_5m:.2f}'
    )
    
    # Add statistics boxes with clean styling
    box_style = dict(
        boxstyle='round,pad=0.5',
        facecolor='#000000FA',  # 98% opaque black
        edgecolor=border_color,
        alpha=0.98  # 98% opacity
    )
    
    # Position stats at the top left
    ax.text(0.02, 0.98, stats_3m,
            transform=ax.transAxes,
            color='white',
            fontsize=10,
            fontweight='bold',
            va='top',
            linespacing=1.5,
            bbox=box_style)
    
    ax.text(0.02, 0.80, stats_5m,
            transform=ax.transAxes,
            color='white',
            fontsize=10,
            fontweight='bold',
            va='top',
            linespacing=1.5,
            bbox=box_style)
    
    # Set y-axis limits with some padding
    ymax = max(df_3m['Cumulative_Fee'].max(), df_5m['Cumulative_Fee'].max())
    ax.set_ylim(0, ymax * 1.1)
    
    # Add horizontal line at y=0
    ax.axhline(y=0, color=border_color, linewidth=1)
    
    # Rotate x-axis labels
    plt.xticks(rotation=45)
    
    # Adjust layout
    plt.tight_layout()
    
    # Before saving, add the logo
    add_utg_logo(fig, 'lower right')
    
    # Save the chart
    filename = f'fee_tracking_{title_prefix.replace(" ", "_").replace("(", "").replace(")", "")}.png'
    plt.savefig(
        filename,
        bbox_inches='tight',
        dpi=300,
        facecolor='#000000FA',
        edgecolor='none',
        transparent=True
    )
    plt.close()
    return filename

def filter_data_by_date(df, start_date):
    """Filter DataFrame to include data from start_date onwards."""
    return df[df['DateTime'] >= pd.to_datetime(start_date)]

def create_comparative_bar_chart(df_50_3m, df_50_5m, df_110_3m, df_110_5m, start_date):
    """Create a comparative bar chart showing performance of different strategies."""
    plt.style.use('dark_background')
    fig, ax = plt.subplots(figsize=(12, 6))
    
    # Set background colors
    ax.set_facecolor('#000000FA')  # 98% opaque black
    fig.patch.set_facecolor('#000000FA')  # 98% opaque black
    
    # Calculate total fees for each strategy after start_date
    fees = []
    labels = []
    
    # Function to safely calculate total fees
    def get_total_fees(df, strategy_name):
        if df.empty:
            print(f"No data available for {strategy_name}")
            return 0
        if 'DateTime' not in df.columns:
            print(f"DateTime column missing in {strategy_name}")
            return 0
        if 'Est. Fee' not in df.columns:
            print(f"Est. Fee column missing in {strategy_name}")
            return 0
            
        filtered_df = df[df['DateTime'] >= start_date]
        total = filtered_df['Est. Fee'].sum()
        return total if not pd.isna(total) else 0
    
    # Calculate fees for each strategy
    fees_50_3m = get_total_fees(df_50_3m, "ETH +50 3m")
    fees_50_5m = get_total_fees(df_50_5m, "ETH +50 5m")
    fees_110_3m = get_total_fees(df_110_3m, "ETH +110 3m")
    fees_110_5m = get_total_fees(df_110_5m, "ETH +110 5m")
    
    # Add non-zero fees to the chart
    if fees_50_3m > 0:
        fees.append(fees_50_3m)
        labels.append("ETH +50 3m")
    if fees_50_5m > 0:
        fees.append(fees_50_5m)
        labels.append("ETH +50 5m")
    if fees_110_3m > 0:
        fees.append(fees_110_3m)
        labels.append("ETH +110 3m")
    if fees_110_5m > 0:
        fees.append(fees_110_5m)
        labels.append("ETH +110 5m")
    
    if not fees:
        raise ValueError("No fee data available for any strategy")
    
    # Define colors for bars
    bar_colors = ['#00B8FF', '#00FF00', '#FF1493', '#FFD700']  # Cyan, Green, Pink, Gold
    
    # Create bars
    bars = ax.bar(labels, fees, color=bar_colors)
    
    # Customize the chart
    ax.set_ylabel('Total Fees ($)', color='white', fontsize=12)
    ax.set_title(f'Strategy Comparison - Total Fees\n(Since {start_date.strftime("%Y-%m-%d")})',
                 color='white', fontsize=14, pad=20)
    
    # Add value labels on top of bars
    for bar in bars:
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height,
                f'${height:,.2f}',
                ha='center', va='bottom',
                color='white',
                fontsize=10,
                fontweight='bold')
    
    # Customize grid and spines
    ax.grid(True, axis='y', linestyle='--', alpha=0.1, color='white')
    for spine in ax.spines.values():
        spine.set_color('#404040')
    
    # Customize tick labels
    ax.tick_params(axis='both', colors='white')
    
    # Add UTG logo in top right
    add_utg_logo(fig, 'upper right')
    
    # Save the chart
    output_file = os.path.join('charts', 'strategy_comparison.png')
    plt.savefig(
        output_file,
        bbox_inches='tight',
        dpi=300,
        facecolor='#000000FA',
        edgecolor='none',
        transparent=True
    )
    plt.close()
    
    return output_file

def check_and_create_assets():
    """Ensure all required assets are in place."""
    logger.info("Checking required assets...")
    
    # Check if logo exists in assets directory
    if not os.path.exists(LOGO_PATH):
        default_logo = BASE_DIR / 'utgl.png'
        if os.path.exists(default_logo):
            # Copy logo to assets directory
            shutil.copy2(default_logo, LOGO_PATH)
            logger.info(f"Copied logo to assets directory: {LOGO_PATH}")
        else:
            logger.warning(f"Logo file not found at {default_logo}")

def main():
    """
    Main function to generate trading analysis charts and send them to Telegram.
    """
    logger.info("Starting chart generation process")
    
    try:
        # Ensure assets are in place
        check_and_create_assets()
        
        # Set start date
        start_date = pd.to_datetime('2025-04-13')
        
        # Send initial message to Telegram
        asyncio.run(send_telegram_message("📊 Liquidity Provider Analysis Charts Update"))
        
        # Load all data first
        logger.info("Loading data from Google Sheets...")
        
        # Define sheet names exactly as they appear in Google Sheets
        sheets = {
            'ETH_110_3m': "(+110) ETH 3m!A:L",
            'ETH_110_5m': "(+110) ETH 5m!A:L",
            'ETH_50_3m': "(+50) ETH 3m!A:L",
            'ETH_50_5m': "(+50) ETH 5m!A:L"
        }
        
        # Load data for each sheet
        data = {}
        for name, range_name in sheets.items():
            try:
                logger.info(f"Loading {name} data...")
                logger.debug(f"Requesting range: {range_name}")
                data[name] = load_data_from_sheets(SPREADSHEET_ID, range_name)
                logger.info(f"✅ {name} data loaded successfully")
            except Exception as e:
                error_msg = f"❌ Error loading {name}: {str(e)}"
                logger.error(error_msg)
                asyncio.run(send_telegram_message(error_msg))
                continue
        
        if not data:
            raise Exception("No data could be loaded from any sheet")
            
        try:
            # Create and send comparative bar chart
            logger.info("Creating comparative bar chart...")
            comparison_file = create_comparative_bar_chart(
                data.get('ETH_50_3m', pd.DataFrame()),
                data.get('ETH_50_5m', pd.DataFrame()),
                data.get('ETH_110_3m', pd.DataFrame()),
                data.get('ETH_110_5m', pd.DataFrame()),
                start_date
            )
            
            # Ensure the chart file was created
            if not os.path.exists(comparison_file):
                raise FileNotFoundError(f"Chart file not created: {comparison_file}")
                
            asyncio.run(send_telegram_photo(
                comparison_file,
                f"Strategy Comparison - Total Fee Performance (Since {start_date.strftime('%d/%m/%Y')})"
            ))
            
            # Process each strategy (+110 and +50)
            strategies = [
                ('+50', data.get('ETH_50_3m', pd.DataFrame()), data.get('ETH_50_5m', pd.DataFrame())),
                ('+110', data.get('ETH_110_3m', pd.DataFrame()), data.get('ETH_110_5m', pd.DataFrame()))
            ]
            
            for strategy, df_3m, df_5m in strategies:
                if df_3m.empty and df_5m.empty:
                    print(f"\nSkipping {strategy} strategy - no data available")
                    continue
                    
                print(f"\nProcessing {strategy} strategy...")
                
                # Filter data by date
                filtered_3m = filter_data_by_date(df_3m, start_date) if not df_3m.empty else df_3m
                filtered_5m = filter_data_by_date(df_5m, start_date) if not df_5m.empty else df_5m
                
                try:
                    # Check required columns before creating charts
                    required_columns = ['Win Rate', 'Est. Fee']
                    for df, timeframe in [(filtered_3m, '3m'), (filtered_5m, '5m')]:
                        if not df.empty:
                            missing_cols = [col for col in required_columns if col not in df.columns]
                            if missing_cols:
                                raise ValueError(f"Missing required columns in {timeframe} data: {', '.join(missing_cols)}")
                    
                    # Create combined charts
                    win_rate_file = create_combined_win_rate_chart(filtered_3m, filtered_5m, f"ETH {strategy}")
                    fee_dist_file = create_combined_fee_distribution_chart(filtered_3m, filtered_5m, f"ETH {strategy}")
                    
                    # Send charts to Telegram
                    logger.info(f"Sending charts for {strategy} strategy")
                    asyncio.run(send_telegram_photo(win_rate_file, f"ETH {strategy} - Trading Statistics Comparison"))
                    asyncio.run(send_telegram_photo(fee_dist_file, f"ETH {strategy} - Fee Distribution Comparison"))
                    
                    print(f"✅ Charts for {strategy} strategy have been generated and sent successfully!")
                except Exception as e:
                    error_msg = f"❌ Error processing charts for {strategy} strategy: {str(e)}"
                    print(error_msg)
                    logger.error(error_msg)
                    asyncio.run(send_telegram_message(error_msg))
                    continue
            
            logger.info("All charts have been generated and sent successfully!")
            
        except Exception as e:
            error_msg = f"❌ Error processing charts: {str(e)}"
            logger.error(error_msg, exc_info=True)
            asyncio.run(send_telegram_message(error_msg))
        
    except Exception as e:
        error_msg = f"❌ An error occurred: {str(e)}"
        logger.error(error_msg, exc_info=True)
        asyncio.run(send_telegram_message(error_msg))

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Process interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.critical("Unhandled exception", exc_info=True)
        sys.exit(1)
