import logging
import sys
import os
import pandas as pd
import yfinance as yf
import smtplib
import dotenv
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

dotenv.load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("trading_script.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger()

SENDER_EMAIL = os.getenv("SENDER_EMAIL")
SENDER_PASSWORD = os.getenv("SENDER_PASSWORD")
RECEIVER_EMAIL = "keshavaradha990@gmail.com"
TICKER_FILE = "piece.txt"


BODY_TEMPLATE = """
Action Alert: {action} {symbol}

Current Trend: {trend}
Current Price: {current_price:.2f}
Market Date: {latest_date}

--- Trade Setup ---
Stoploss: {stoploss:.2f}
Target: {target:.2f}

High Reference: {high_date}
Low Reference: {low_date}
"""

def analyze_market(data: pd.DataFrame, threshold=3):
    """
    Analyzes a 30-day window to determine trend based on recency of Highs/Lows
    and checks for a breakout signal.
    """
    try:
        date_of_highest_high = data['High'].idxmax()
        date_of_lowest_low = data['Low'].idxmin()

        highest_high_val = data.loc[date_of_highest_high]['High']
        lowest_low_val = data.loc[date_of_lowest_low]['Low']
        current_trend = None
        
        if date_of_lowest_low > date_of_highest_high:
            current_trend = 'up'
        else:
            current_trend = 'down'
            
        today = data.iloc[-1]
        signal_breakout = False

        if current_trend == 'up':
            if abs(today['Open'] - today['Low']) <= threshold:
                signal_breakout = True
                
        elif current_trend == 'down':
            if abs(today['Open'] - today['High']) <= threshold:
                signal_breakout = True

        action_details = {
            "trend": current_trend,
            "current_price": today['Open'],
            "latest_date": today.name.strftime('%Y-%m-%d'),
            "action": None,
            "stoploss": None,
            "target": None,
            "high_date": date_of_highest_high.strftime('%Y-%m-%d'),
            "low_date": date_of_lowest_low.strftime('%Y-%m-%d')
        }

        if signal_breakout:
            if current_trend == 'up':
                action_details['action'] = 'BUY'
                action_details['stoploss'] = lowest_low_val
                action_details['target'] = highest_high_val
                
            elif current_trend == 'down':
                action_details['action'] = 'SELL'
                action_details['stoploss'] = highest_high_val
                action_details['target'] = lowest_low_val

        return (current_trend, signal_breakout, action_details)
    
    except Exception as e:
        logger.error(f"Error inside market analysis logic: {e}", exc_info=True)
        return (None, False, {})

def get_data(ticker_symbol: str):
    """Fetches 1 month of history."""
    try:
        ticker = yf.Ticker(ticker_symbol)
        data = ticker.history(period="1mo")
        if data.empty:
            logger.warning(f"No data fetched for {ticker_symbol}. Check ticker symbol.")
        return data
    except Exception as e:
        logger.error(f"Failed to fetch data for {ticker_symbol}: {e}")
        return pd.DataFrame()

def get_trend_details(ticker_symbol: str):
    """Wrapper to get data and analyze."""
    data = get_data(ticker_symbol)
    if data.empty:
        return None, False, {}
    trend, signal, details = analyze_market(data)
    return trend, signal, details

def send_mail(subject: str, body: str, to_email: str):
    msg = MIMEMultipart()
    msg['From'] = SENDER_EMAIL
    msg['To'] = to_email
    msg['Subject'] = subject

    msg.attach(MIMEText(body, 'plain'))

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        text = msg.as_string()
        server.sendmail(SENDER_EMAIL, to_email, text)
        server.quit()
        
        logger.info(f"Email sent successfully to {to_email} | Subject: {subject}")
        
    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {e}", exc_info=True)

def load_tickers(filename):
    """Reads ticker symbols from a text file, handling newlines and empty spaces."""
    try:
        with open(filename, 'r') as f:
            tickers = [line.strip() for line in f if line.strip()]
            
        logger.info(f"Loaded {len(tickers)} tickers from {filename}")
        return tickers
    except Exception as e:
        logger.error(f"Error reading {filename}: {e}")
        return []

def main():
    logger.info("--------------------------------------------------")
    logger.info("Script Started: Analyzing Market Conditions")
    
    # Load symbols from the text file instead of hardcoded list
    ticker_symbols = load_tickers(TICKER_FILE)

    if not ticker_symbols:
        logger.warning("No tickers found. Exiting script.")
        return

    for symbol in ticker_symbols:
        try:
            logger.info(f"Analyzing ticker: {symbol}...")
            trend, signal, details = get_trend_details(symbol)
            
            if signal:
                logger.info(f"!! Signal Found for {symbol}. Preparing notification.")
                
                details['symbol'] = symbol
                body = BODY_TEMPLATE.format(**details)
                
                send_mail(
                    subject=f"Trade Signal: {details['action']} {symbol}",
                    body=body,
                    to_email=RECEIVER_EMAIL
                )
            else:
                if trend:
                    logger.info(f"No signal for {symbol}. Current Trend: {trend}")
                else:
                    logger.warning(f"Could not determine trend for {symbol}")
                
        except Exception as e:
            logger.error(f"Critical failure in main loop for {symbol}: {e}", exc_info=True)
            
    logger.info("Analysis Complete. Script Finished.")
    logger.info("--------------------------------------------------")

if __name__ == "__main__":
    main()