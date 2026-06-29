import streamlit as st
from datetime import datetime
import time
import pytz
import random

# Versuche MetaTrader5 zu laden (wird nur lokal klappen)
try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ModuleNotFoundError:
    MT5_AVAILABLE = False

# Fallback für die Cloud
try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ModuleNotFoundError:
    YFINANCE_AVAILABLE = False
