import streamlit as st
from datetime import datetime
import time
import pytz
import google.generativeai as genai
from openai import OpenAI
import random

# Versuche MetaTrader5 zu laden (klappt lokal, schlägt online fehl)
try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ModuleNotFoundError:
    MT5_AVAILABLE = False

# Versuche yfinance für den Online-Fallback zu laden
try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ModuleNotFoundError:
    YFINANCE_AVAILABLE = False

# ==========================================
# KONFIGURATION
# ==========================================
GOLD_FOTO_URL = "https://images.unsplash.com/photo-1610374792793-f016b77ca51a?q=80&w=100&auto=format&fit=crop"
ATR_PERIOD = 10
KEY_VALUE = 1.0
TRADE_TIMER_SEC = 10
BROKER_SYMBOL = "XAUUSD"

st.set_page_config(
    page_title="Fisiget Bot – Gold AI",
    page_icon="🪙",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
    html, body, [class*="css"] { background-color: #0a0f1a !important; }
    .stApp { background-color: #0a0f1a; }
    .block-container { padding: 0 !important; max-width: 100% !important; }
    header[data-testid="stHeader"] { background: transparent; }
    .stButton { display: none !important; }
    * { box-sizing: border-box; margin: 0; padding: 0; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# API SETUP
# ==========================================
@st.cache_resource
def init_clients():
    keys = {"gemini": None, "groq": None}
    groq_client = None
    if hasattr(st, "secrets"):
        keys["gemini"] = st.secrets.get("GEMINI_API_KEY")
        keys["groq"] = st.secrets.get("GROQ_API_KEY")
    if keys["gemini"]:
        genai.configure(api_key=keys["gemini"])
    if keys["groq"]:
        groq_client = OpenAI(base_url="https://api.groq.com/openai/v1", api_key=keys["groq"])
    return keys, groq_client

keys, groq_client = init_clients()

# ==========================================
# STATE INIT
# ==========================================
if "src_history" not in st.session_state:
    st.session_state.src_history = [2330.0] * 15
if "trail" not in st.session_state:
    st.session_state.trail = 2325.0
if "pos" not in st.session_state:
    st.session_state.pos = 1
if "ki_signal" not in st.session_state:
    st.session_state.ki_signal = "BUY (LONG)"
if "ki_reason" not in st.session_state:
    st.session_state.ki_reason = "Initialisiere AI Pipeline…"
if "last_ai_run" not in st.session_state:
    st.session_state.last_ai_run = 0.0  
if "force_ai" not in st.session_state: 
    st.session_state.force_ai = False
if "trade_timer" not in st.session_state: 
    st.session_state.trade_timer = TRADE_TIMER_SEC

if "broker_sell" not in st.session_state: st.session_state.broker_sell = 2330.0
if "broker_buy" not in st.session_state: st.session_state.broker_buy = 2330.85
if "broker_spread" not in st.session_state: st.session_state.broker_spread = 0.85
if "connection_status" not in st.session_state: st.session_state.connection_status = "⚠️ Initialisiere..."

if st.button("Hidden Trigger", key="hidden_trigger", type="secondary"):
    st.session_state.force_ai = True
    st.rerun()

# ==========================================
# HYBRIDER DATA FEED (MT5 LOKAL / YFINANCE ONLINE)
# ==========================================
def check_market_state() -> str:
    tz = pytz.timezone("Europe/Berlin")
    now = datetime.now(tz)
    if (now.weekday() == 4 and now.hour >= 23) or now.weekday() == 5 or (now.weekday() == 6 and now.hour < 23):
        return "OTC"
    return "LIVE"

def get_broker_market_data():
    # WEG 1: LOKAL MIT METATRADER 5
    if MT5_AVAILABLE:
        if hasattr(st, "secrets") and "pepperstone" in st.secrets:
            account_number = st.secrets["pepperstone"]["account"]
            trading_password = st.secrets["pepperstone"]["password"]
            broker_server = st.secrets["pepperstone"]["server"]
        else:
            st.session_state.connection_status = "❌ Fehler: secrets.toml fehlt lokal!"
            return None

        if not mt5.initialize():
            st.session_state.connection_status = "❌ MT5 App nicht geöffnet!"
            return None
            
        try:
            clean_account = int(str(account_number).strip())
            clean_password = str(trading_password).strip()
            clean_server = str(broker_server).strip()
            login_success = mt5.login(account=clean_account, password=clean_password, server=clean_server)
        except Exception:
            login_success = False
        
        if not login_success:
            st.session_state.connection_status = "❌ Pepperstone Login fehlgeschlagen!"
            return None
        
        tick = mt5.symbol_info_tick(BROKER_SYMBOL)
        if tick is not None:
            st.session_state.broker_sell = round(tick.bid, 2)
            st.session_state.broker_buy = round(tick.ask, 2)
            st.session_state.broker_spread = round((tick.ask - tick.bid), 2)
            st.session_state.connection_status = "🟢 Verbunden: Pepperstone MT5 (Lokal)"
            return round((tick.bid + tick.ask) / 2, 2)

    # WEG 2: ONLINE CLOUD FALLBACK MIT YFINANCE
    if YFINANCE_AVAILABLE:
        try:
            gold = yf.Ticker("GC=F")
            data = gold.fast_info
            current_price = round(data.last_price, 2)
            
            st.session_state.broker_sell = round(current_price - 0.4, 2)
            st.session_state.broker_buy = round(current_price + 0.4, 2)
            st.session_state.broker_spread = 0.80
            st.session_state.connection_status = "🟢 Verbunden: Yahoo Finance Live Feed (Cloud Mode)"
            return current_price
        except Exception:
            pass

    # WEG 3: SIMULATION ALS LETZTER AUSWEG
    st.session_state.connection_status = "⚠️ Keine Live-Verbindung. Simuliere Daten..."
    return round(st.session_state.src_history[-1] + random.uniform(-0.2, 0.2), 2)

# ==========================================
# INDIKATOREN & AI MODUL
# ==========================================
def calculate_rsi(prices, period=14):
    if len(prices) < period + 1: return 50.0
    gains, losses = [], []
    for i in range(1, len(prices)):
        d = prices[i] - prices[i-1]
        gains.append(max(d, 0)); losses.append(max(-d, 0))
    ag = sum(gains[-period:]) / period
    al = sum(losses[-period:]) / period
    return 100.0 if al == 0 else round(100.0 - (100.0 / (1.0 + ag/al)), 1)

def calculate_atr(prices, period):
    diffs = [abs(prices[i]-prices[i-1]) for i in range(1, len(prices))]
    return sum(diffs[-period:]) / period if len(diffs) >= period else 1.5

def ut_bot_step(src, last_src, trail, pos, atr):
    n = KEY_VALUE * atr
    if src > trail and last_src > trail: trail = max(trail, src - n)
    elif src < trail and last_src < trail: trail = min(trail, src + n)
    else: trail = src - n if src > trail else src + n
    if last_src < trail and src > trail: pos = 1
    elif last_src > trail and src < trail: pos = -1
    return trail, pos

AI_PROMPT = """Du bist ein algorithmischer Handels-Bot für Gold (XAU/USD).
DATEN: Gold=${preis:.2f} | RSI={rsi} | Signal: {signal}
Antworte NUR so:
SIGNAL: [BUY|SELL|WAIT]
BEGRÜNDUNG: [max. 15 Wörter]"""

def parse_ai_response(text, source):
    signal, reason = "WAIT", "Analyse abgeschlossen."
    for line in text.strip().splitlines():
        if line.startswith("SIGNAL:"):
            raw = line.replace("SIGNAL:", "").strip().upper()
            signal = "BUY (LONG)" if "BUY" in raw else "SELL (SHORT)" if "SELL" in raw else "WAIT (SIDEWAYS)"
        elif line.startswith("BEGRÜNDUNG:"):
            reason = line.replace("BEGRÜNDUNG:", "").strip()
    return signal, f"[{source}]: {reason}"

def dual_ai_filter(preis, rsi, mathe_signal):
    fallback = "BUY (LONG)" if "BUY" in mathe_signal else "SELL (SHORT)" if "SELL" in mathe_signal else "WAIT (SIDEWAYS)"
    if not any(keys.values()):
        return fallback, "Kein API-Key – Mathe-Modus."
    prompt = AI_PROMPT.format(preis=preis, rsi=rsi, signal=mathe_signal)
    if keys["gemini"]:
        try:
            resp = genai.GenerativeModel("gemini-2.5-flash").generate_content(prompt)
            if resp.text and "SIGNAL:" in resp.text:
                return parse_ai_response(resp.text, "Gemini 2.5 Flash")
        except Exception: pass
    return fallback, "KI nicht verfügbar – Mathe-Modus."

# ==========================================
# UI RENDERING & SYSTEM STATS
# ==========================================
SIGNAL_CONFIG = {
    "BUY": {
        "color": "#00e676", "glow": "#00e676",
        "bg": "radial-gradient(circle at 50% 40%, #00e676 0%, #00c853 30%, #004d2e 70%, #001a10 100%)",
        "dir": "UPWARD", "win": "82%", "dots": 5,
        "svg": '<svg viewBox="0 0 24 24" style="width:74px;height:74px;fill:none;stroke:#fff;stroke-width:3;stroke-linecap:round;stroke-linejoin:round;"><path d="M23 6l-9.5 9.5-5-5L1 18M23 6h-6M23 6v6"/></svg>',
    },
    "SELL": {
        "color": "#ff1744", "glow": "#ff1744",
        "bg": "radial-gradient(circle at 50% 40%, #ff5252 0%, #ff1744 30%, #4d0010 70%, #1a0005 100%)",
        "dir": "DOWNWARD", "win": "89%", "dots": 4,
        "svg": '<svg viewBox="0 0 24 24" style="width:74px;height:74px;fill:none;stroke:#fff;stroke-width:3;stroke-linecap:round;stroke-linejoin:round;"><path d="M23 18l-9.5-9.5-5 5L1 6M23 18h-6M23 18v-6"/></svg>',
    },
    "WAIT": {
        "color": "#ffc400", "glow": "#ffc400",
        "bg": "radial-gradient(circle at 50% 40%, #ffd740 0%, #ffc400 30%, #4d3800 70%, #1a1200 100%)",
        "dir": "SIDEWAYS", "win": "—", "dots": 2,
        "svg": '<svg viewBox="0 0 24 24" style="width:74px;height:74px;fill:none;stroke:#fff;stroke-width:3;stroke-linecap:round;stroke-linejoin:round;"><path d="M5 12h14M13 5l7 7-7 7"/></svg>',
    },
}

def get_sig_key(s):
    if "BUY" in s: return "BUY"
    if "SELL" in s: return "SELL"
    return "WAIT"

def get_market_sessions():
    tz = pytz.timezone("Europe/Berlin")
    now = datetime.now(tz)
    weekday = now.weekday()
    h = now.hour + now.minute / 60.0
    sessions = [
        {"name": "Sydney", "flag": "🇦🇺", "open_h": 0.0, "close_h": 9.0, "days": [0,1,2,3,4]},
        {"name": "Tokio", "flag": "🇯🇵", "open_h": 1.0, "close_h": 10.0, "days": [0,1,2,3,4]},
        {"name": "London", "flag": "🇬🇧", "open_h": 9.0, "close_h": 18.0, "days": [0,1,2,3,4]},
        {"name": "New York", "flag": "🇺🇸", "open_h": 14.0, "close_h": 23.0, "days": [0,1,2,3,4]},
    ]
    result = []
    for s in sessions:
        is_open = weekday in s["days"] and s["open_h"] <= h < s["close_h"]
        status = f"Schließt in {int((s['close_h'] - h) * 60)}min" if is_open else "Geschlossen"
        result.append({
            "name": s["name"], "flag": s["flag"], "open": f"{int(s['open_h']):02d}:00", "close": f"{int(s['close_h']):02d}:00",
            "is_open": is_open, "status": status, "color": "#00e676" if is_open else "#ff1744", "dot": "🟢" if is_open else "🔴"
        })
    return result

# Execution Pipeline
market_state = check_market_state()
current_price = get_broker_market_data()
if not current_price:
    current_price = st.session_state.src_history[-1]

last_src = st.session_state.src_history[-1]
st.session_state.src_history.append(current_price)
if len(st.session_state.src_history) > 25: st.session_state.src_history.pop(0)

rsi = calculate_rsi(st.session_state.src_history)
atr = calculate_atr(st.session_state.src_history, ATR_PERIOD)
st.session_state.trail, st.session_state.pos = ut_bot_step(current_price, last_src, st.session_state.trail, st.session_state.pos, atr)
mathe_signal = "BUY" if st.session_state.pos == 1 else "SELL"

current_time = time.time()
if (current_time - st.session_state.last_ai_run >= 60.0) or st.session_state.force_ai:
    st.session_state.ki_signal, st.session_state.ki_reason = dual_ai_filter(current_price, rsi, mathe_signal)
    st.session_state.last_ai_run = current_time
    st.session_state.force_ai = False

seconds_until_next_run = max(0, int(60 - (current_time - st.session_state.last_ai_run)))
st.session_state.trade_timer = st.session_state.trade_timer - 1 if st.session_state.trade_timer > 1 else TRADE_TIMER_SEC

sessions = get_market_sessions()
open_count = sum(1 for s in sessions if s["is_open"])
sig_key = get_sig_key(st.session_state.ki_signal)
cfg = SIGNAL_CONFIG[sig_key]
dots_filled = "●" * cfg["dots"] + "○" * (5 - cfg["dots"])

# Render Status Message
if "🟢" in st.session_state.connection_status:
    st.success(st.session_state.connection_status)
else:
    st.error(st.session_state.connection_status)

# HTML UI Injection
st.html(f"""
<!DOCTYPE html>
<html>
<head>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800;900&display=swap');
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: #0a0f1a; font-family: 'Inter', sans-serif; }}
  .app {{ display: flex; justify-content: center; align-items: flex-start; min-height: 100vh; background: #0a0f1a; }}
  .phone {{ width: 100%; max-width: 480px; background: #0d1320; margin: 0 auto; overflow: hidden; }}
  .topbar {{ display: flex; justify-content: space-between; align-items: center; padding: 16px 20px; border-bottom: 1px solid #1a2540; }}
  .logo {{ font-size: 15px; font-weight: 900; color: #fff; }}
  .body {{ padding: 20px 18px; }}
  .signal-header {{ font-size: 16px; font-weight: 800; color: #fff; text-align: center; margin-bottom: 4px; }}
  .signal-tf {{ font-size: 13px; color: #4b6080; text-align: center; margin-bottom: 20px; }}
  .trading-prices {{ display: flex; justify-content: center; align-items: center; gap: 10px; margin-bottom: 20px; }}
  .price-button {{ flex: 1; background: rgba(10, 15, 26, 0.6); border-radius: 10px; padding: 10px; text-align: center; }}
  .price-button.sell {{ border: 1.5px solid #ff1744; color: #ff1744; }}
  .price-button.buy {{ border: 1.5px solid #2563eb; color: #2563eb; }}
  .circle-outer {{ display: flex; justify-content: center; margin-bottom: 18px; }}
  .circle-main {{ width: 180px; height: 180px; border-radius: 50%; display: flex; align-items: center; justify-content: center; background: {cfg['bg']}; box-shadow: 0 0 60px {cfg['glow']}88; }}
  .signal-text {{ text-align: center; font-size: 34px; font-weight: 900; color: {cfg['color']}; margin-bottom: 18px; }}
  .ai-bar {{ background: #0a0f1a; border: 1px solid #1a2540; border-radius: 12px; padding: 11px; text-align: center; color: #00e676; font-size: 12px; font-weight: 700; margin-bottom: 10px; }}
</style>
</head>
<body>
<div class="app">
  <div class="phone">
    <div class="topbar"><div class="logo">🪙 FISIGET BOT</div></div>
    <div class="body">
      <div class="signal-header">Gold Spot / U.S. Dollar</div>
      <div class="signal-tf">Mittelkurs: ${current_price:,.2f} · TF: 1 SEC</div>
      <div class="trading-prices">
        <div class="price-button sell"><h3>{st.session_state.broker_sell:,.2f}</h3><div>BID</div></div>
        <div class="price-button buy"><h3>{st.session_state.broker_buy:,.2f}</h3><div>ASK</div></div>
      </div>
      <div class="circle-outer"><div class="circle-main">{cfg['svg']}</div></div>
      <div class="signal-text">{st.session_state.ki_signal}</div>
      <div class="ai-bar">NEXT AI UPDATE IN {seconds_until_next_run}s</div>
      <div style="background:#0a0f1a; border:1px solid #1a2540; border-radius:12px; padding:12px; font-size:12px; color:#4b6080;">
        <span style="color:#fff; font-weight:700;">🤖 AI-Reasoning:</span> {st.session_state.ki_reason}
      </div>
    </div>
  </div>
</div>
</body>
</html>
""")

time.sleep(1)
st.rerun()
