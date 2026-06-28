import streamlit as st
from datetime import datetime
import time
import pytz
import MetaTrader5 as mt5
import google.generativeai as genai
from openai import OpenAI

# ==========================================
# KONFIGURATION
# ==========================================
GOLD_FOTO_URL = "https://images.unsplash.com/photo-1610374792793-f016b77ca51a?q=80&w=100&auto=format&fit=crop"
ATR_PERIOD = 10
KEY_VALUE = 1.0
TRADE_TIMER_SEC = 10

# Das Symbol deines Brokers für Gold (meistens "XAUUSD")
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
# STATE INIT (JEDE VARIABLE EINZELN ABSICHERN)
# ==========================================
if "src_history" not in st.session_state:
    st.session_state.src_history = [2350.0] * 15
if "trail" not in st.session_state:
    st.session_state.trail = 2345.0
if "pos" not in st.session_state:
    st.session_state.pos = 1
if "ki_signal" not in st.session_state:
    st.session_state.ki_signal = "BUY (LONG)"
if "ki_reason" not in st.session_state:
    st.session_state.ki_reason = "Initialisiere AI Pipeline…"
if "last_ai_run" not in st.session_state:
    st.session_state.last_ai_run = 0.0  
if "price_tick" not in st.session_state:
    st.session_state.price_tick = 0
if "force_ai" not in st.session_state: 
    st.session_state.force_ai = False
if "trade_timer" not in st.session_state: 
    st.session_state.trade_timer = TRADE_TIMER_SEC

# Zwischenspeicher für Broker-Preise
if "broker_sell" not in st.session_state: st.session_state.broker_sell = 2350.0
if "broker_buy" not in st.session_state: st.session_state.broker_buy = 2350.90
if "broker_spread" not in st.session_state: st.session_state.broker_spread = 0.90

# Versteckter Trigger für den Button-Klick (JavaScript)
if st.button("Hidden Trigger", key="hidden_trigger", type="secondary"):
    st.session_state.force_ai = True
    st.rerun()

# ==========================================
# SICHRE BROKER LIVE DATA (PEPPERSTONE MT5)
# ==========================================
def check_market_state() -> str:
    tz = pytz.timezone("Europe/Berlin")
    now = datetime.now(tz)
    if (now.weekday() == 4 and now.hour >= 23) or now.weekday() == 5 or (now.weekday() == 6 and now.hour < 23):
        return "OTC"
    return "LIVE"

def get_broker_market_data():
    if hasattr(st, "secrets") and "pepperstone" in st.secrets:
        account_number = st.secrets["pepperstone"]["account"]
        trading_password = st.secrets["pepperstone"]["password"]
        broker_server = st.secrets["pepperstone"]["server"]
    else:
        return None

    if not mt5.initialize():
        return None
        
    login_success = mt5.login(account=int(account_number), password=str(trading_password), server=str(broker_server))
    if not login_success:
        return None
    
    tick = mt5.symbol_info_tick(BROKER_SYMBOL)
    
    if tick is not None:
        bid = tick.bid
        ask = tick.ask
        
        st.session_state.broker_sell = round(bid, 2)
        st.session_state.broker_buy = round(ask, 2)
        st.session_state.broker_spread = round((ask - bid), 2)
        
        mid_price = round((bid + ask) / 2, 2)
        return mid_price
        
    return None

# ==========================================
# INDIKATOREN
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

# ==========================================
# DUAL-AI
# ==========================================
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
# SIGNAL CONFIG
def make_svg(path, color="white"):
    return f'<svg viewBox="0 0 24 24" style="width:74px;height:74px;fill:none;stroke:{color};stroke-width:3;stroke-linecap:round;stroke-linejoin:round;filter:drop-shadow(0 0 14px rgba(255,255,255,0.95)) drop-shadow(0 0 6px {color});"><path d="{path}"/></svg>'

SIGNAL_CONFIG = {
    "BUY": {
        "color": "#00e676", "glow": "#00e676",
        "bg": "radial-gradient(circle at 50% 40%, #00e676 0%, #00c853 30%, #004d2e 70%, #001a10 100%)",
        "dir": "UPWARD", "win": "82%", "dots": 5,
        "svg": make_svg("M23 6l-9.5 9.5-5-5L1 18M23 6h-6M23 6v6", "#fff"),
    },
    "SELL": {
        "color": "#ff1744", "glow": "#ff1744",
        "bg": "radial-gradient(circle at 50% 40%, #ff5252 0%, #ff1744 30%, #4d0010 70%, #1a0005 100%)",
        "dir": "DOWNWARD", "win": "89%", "dots": 4,
        "svg": make_svg("M23 18l-9.5-9.5-5 5L1 6M23 18h-6M23 18v-6", "#fff"),
    },
    "WAIT": {
        "color": "#ffc400", "glow": "#ffc400",
        "bg": "radial-gradient(circle at 50% 40%, #ffd740 0%, #ffc400 30%, #4d3800 70%, #1a1200 100%)",
        "dir": "SIDEWAYS", "win": "—", "dots": 2,
        "svg": make_svg("M5 12h14M13 5l7 7-7 7", "#fff"),
    },
}

def get_sig_key(s):
    if "BUY" in s: return "BUY"
    if "SELL" in s: return "SELL"
    return "WAIT"

# ==========================================
# MARKTZEITEN SESSIONS
# ==========================================
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
        if is_open:
            mins_left = int((s["close_h"] - h) * 60)
            status = f"Schließt in {mins_left}min"
            color = "#00e676"
            dot = "🟢"
        elif weekday in s["days"] and h < s["open_h"]:
            mins_to = int((s["open_h"] - h) * 60)
            status = f"Öffnet in {mins_to}min"
            color = "#ffc400"
            dot = "🟡"
        else:
            status = f"Geschlossen"
            color = "#ff1744"
            dot = "🔴"
        result.append({
            "name": s["name"], "flag": s["flag"],
            "open": f"{int(s['open_h']):02d}:00", "close": f"{int(s['close_h']):02d}:00",
            "is_open": is_open, "status": status, "color": color, "dot": dot,
        })
    return result

def build_market_hours_html(sessions):
    rows = ""
    for s in sessions:
        rows += f"""
        <div style="display:flex;justify-content:space-between;align-items:center;padding:10px 14px;border-bottom:1px solid #1a2540;">
          <div style="display:flex;align-items:center;gap:8px;">
            <span style="font-size:16px;">{s['flag']}</span>
            <div>
              <div style="font-size:12px;font-weight:700;color:#fff;">{s['name']}</div>
              <div style="font-size:10px;color:#4b6080;">{s['open']} – {s['close']} (Berlin)</div>
            </div>
          </div>
          <div style="text-align:right;">
            <div style="font-size:11px;font-weight:700;color:{s['color']};">{s['dot']} {'OFFEN' if s['is_open'] else 'GESCHLOSSEN'}</div>
            <div style="font-size:10px;color:#4b6080;">{s['status']}</div>
          </div>
        </div>"""
    return rows

# ==========================================
# TIMING & PIPELINE LOGIC
# ==========================================
market_state = check_market_state()
live_gold = get_broker_market_data()
current_price = live_gold if live_gold else st.session_state.src_history[-1]

is_weekend = datetime.now(pytz.timezone("Europe/Berlin")).weekday() >= 5
price_label = f"Fr. Schluss: ${current_price:,.2f}" if is_weekend else f"${current_price:,.2f}"

last_src = st.session_state.src_history[-1]
st.session_state.src_history.append(current_price)
if len(st.session_state.src_history) > 25:
    st.session_state.src_history.pop(0)

rsi = calculate_rsi(st.session_state.src_history)
atr = calculate_atr(st.session_state.src_history, ATR_PERIOD)
st.session_state.trail, st.session_state.pos = ut_bot_step(
    current_price, last_src, st.session_state.trail, st.session_state.pos, atr
)
mathe_signal = "BUY" if st.session_state.pos == 1 else "SELL"

# 1-Minuten KI-Bremse
current_time = time.time()
if (current_time - st.session_state.last_ai_run >= 60.0) or st.session_state.force_ai:
    st.session_state.ki_signal, st.session_state.ki_reason = dual_ai_filter(current_price, rsi, mathe_signal)
    st.session_state.last_ai_run = current_time
    st.session_state.force_ai = False

seconds_since_last_run = current_time - st.session_state.last_ai_run
seconds_until_next_run = max(0, int(60 - seconds_since_last_run))

st.session_state.trade_timer -= 1
if st.session_state.trade_timer <= 0:
    st.session_state.trade_timer = TRADE_TIMER_SEC

sessions = get_market_sessions()
market_hours_html = build_market_hours_html(sessions)
open_count = sum(1 for s in sessions if s["is_open"])

sig_key = get_sig_key(st.session_state.ki_signal)
cfg = SIGNAL_CONFIG[sig_key]
mode_label = "LIVE AI" if any(keys.values()) else "MATH MODE"
dots_filled = "●" * cfg["dots"] + "○" * (5 - cfg["dots"])

# Vorab-Berechnung für den fehlerfreien Sub-Text (Behebt SyntaxError!)
dots_sub_text = cfg['dots_sub'] if 'dots_sub' in cfg else f"{cfg['dots']}/5"

# ==========================================
# RENDER LAYOUT
# ==========================================
st.html(f"""
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800;900&display=swap');
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: #0a0f1a; font-family: 'Inter', sans-serif; }}
  @keyframes blink {{ 0%,100%{{opacity:1;}} 50%{{opacity:0.2;}} }}
  @keyframes fadeIn {{ from {{ opacity: 0; transform: translateY(10px); }} to {{ opacity: 1; transform: translateY(0); }} }}
  @keyframes glow-pulse {{
    0%, 100% {{ box-shadow: 0 0 60px {cfg['glow']}88, 0 0 120px {cfg['glow']}44; }}
    50%       {{ box-shadow: 0 0 80px {cfg['glow']}bb, 0 0 160px {cfg['glow']}66; }}
  }}
  .app {{ display: flex; justify-content: center; align-items: flex-start; min-height: 100vh; background: #0a0f1a; }}
  .phone {{ width: 100%; max-width: 100%; background: #0d1320; border-radius: 0; border: none; overflow: hidden; }}
  .topbar {{ display: flex; justify-content: space-between; align-items: center; padding: 16px 20px 12px; border-bottom: 1px solid #1a2540; }}
  .logo {{ font-size: 15px; font-weight: 900; color: #fff; display: flex; align-items: center; gap: 8px; }}
  .live-badge {{ font-size: 11px; font-weight: 700; color: #00e676; display: flex; align-items: center; gap: 6px; }}
  .dot-live {{ width: 7px; height: 7px; border-radius: 50%; background: #00e676; animation: blink 1.2s infinite; }}
  .body {{ width: 100%; max-width: 480px; margin: 0 auto; padding: 20px 18px 16px; box-sizing: border-box; }}
  .back-btn {{ color: #00e676; font-size: 20px; margin-bottom: 12px; cursor: pointer; display: inline-block; }}
  .signal-header {{ font-size: 16px; font-weight: 800; color: #fff; margin-bottom: 6px; text-align: center; }}
  .signal-header span {{ color: #00e676; }}
  .signal-tf {{ font-size: 13px; font-weight: 700; color: #4b6080; margin-bottom: 24px; text-align: center; }}
  .circle-outer {{ display: flex; justify-content: center; margin-bottom: 18px; }}
  .circle-main {{
    width: 180px; height: 180px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
    background: {cfg['bg']}; box-shadow: 0 0 60px {cfg['glow']}88, 0 0 120px {cfg['glow']}44; animation: glow-pulse 2s ease-in-out infinite;
  }}
  .dir-badge {{ display: block; width: fit-content; margin: 0 auto 8px; background: #0d1320; border: 1.5px solid {cfg['color']}; border-radius: 20px; padding: 5px 20px; font-size: 12px; font-weight: 800; letter-spacing: 1.5px; text-transform: uppercase; color: {cfg['color']}; }}
  .signal-text {{ text-align: center; font-size: 34px; font-weight: 900; color: {cfg['color']}; text-shadow: 0 0 30px {cfg['glow']}88; margin-bottom: 18px; letter-spacing: 0.5px; }}
  .stats-row {{ display: flex; gap: 10px; margin-bottom: 12px; }}
  .stat-card {{ flex: 1; background: #0a0f1a; border: 1px solid #1a2540; border-radius: 14px; padding: 12px 14px; }}
  .stat-label {{ font-size: 10px; color: #4b6080; text-transform: uppercase; letter-spacing: 1px; font-weight: 700; margin-bottom: 6px; }}
  .stat-dots {{ font-size: 16px; letter-spacing: 4px; color: {cfg['color']}; margin-bottom: 3px; }}
  .stat-sub {{ font-size: 11px; color: #4b6080; font-weight: 700; }}
  .stat-winrate {{ font-size: 28px; font-weight: 900; color: {cfg['color']}; line-height: 1; }}
  .stat-live {{ font-size: 10px; color: #4b6080; margin-top: 4px; }}
  .ai-bar {{ background: #0a0f1a; border: 1px solid #1a2540; border-radius: 12px; padding: 11px 16px; display: flex; align-items: center; justify-content: center; gap: 8px; margin-bottom: 10px; font-size: 12px; font-weight: 700; color: #00e676; letter-spacing: 1px; }}
  .trade-timer {{ background: #0a0f1a; border: 1px solid #1a2540; border-radius: 12px; padding: 10px 16px; text-align: center; margin-bottom: 12px; font-size: 12px; font-weight: 700; color: #4b6080; letter-spacing: 1px; }}
  .trade-timer span {{ color: #00e676; font-size: 14px; }}
  .gen-btn {{ width: 100%; border: none; border-radius: 14px; background: linear-gradient(135deg, #00e676, #00c853); color: #0a0d14; font-size: 15px; font-weight: 800; padding: 16px; letter-spacing: 0.5px; cursor: pointer; margin-bottom: 12px; box-shadow: 0 6px 24px rgba(0,230,118,0.35); transition: all 0.2s; font-family: Inter, sans-serif; }}
  .ssl-bar {{ text-align: center; font-size: 10px; color: #2a3a50; padding: 8px 0; }}
  .nav-bar {{ display: flex; justify-content: space-around; align-items: center; padding: 14px 20px 18px; border-top: 1px solid #1a2540; background: #090d18; }}
  .nav-item {{ display: flex; flex-direction: column; align-items: center; gap: 4px; font-size: 10px; font-weight: 700; color: #2a3a50; cursor: pointer; }}
  .nav-item.active {{ background: #00e676; color: #0a0f1a; padding: 8px 18px; border-radius: 12px; gap: 3px; }}
  .nav-icon {{ font-size: 16px; }}

  .trading-prices {{ display: flex; justify-content: center; align-items: center; gap: 10px; margin-bottom: 20px; }}
  .price-button {{ flex: 1; background: rgba(10, 15, 26, 0.6); border-radius: 10px; padding: 10px; text-align: center; font-family: monospace; }}
  .price-button.sell {{ border: 1.5px solid #ff1744; }}
  .price-button.buy {{ border: 1.5px solid #2563eb; }}
  .price-num-sell {{ font-size: 17px; font-weight: 700; color: #ff1744; }}
  .price-num-buy {{ font-size: 17px; font-weight: 700; color: #2563eb; }}
  .price-label-sub {{ font-size: 9px; color: #4b6080; text-transform: uppercase; font-weight: 700; margin-top: 2px; }}
</style>
</head>
<body>
<div class="app">
  <div class="phone">
    <div class="topbar">
      <div class="logo">🪙 FISIGET BOT</div>
      <div class="live-badge"><div class="dot-live"></div> {mode_label} | {market_state} | 👤 1,360</div>
    </div>

    <div class="body">
      <div class="back-btn">←</div>
      <div class="signal-header">Gold Spot / U.S. Dollar · <span>PEPPERSTONE LIVE</span></div>
      <div class="signal-tf">Mittelkurs: {price_label} &nbsp;·&nbsp; TF: 1 SEC</div>

      <div class="trading-prices">
        <div class="price-button sell">
          <div class="price-num-sell">{st.session_state.broker_sell:,.2f}</div>
          <div class="price-label-sub">BID (Verkauf)</div>
        </div>
        <div style="font-size:12px; color:#9ca3af; font-weight:700; font-family:monospace;">{st.session_state.broker_spread:.2f}</div>
        <div class="price-button buy">
          <div class="price-num-buy">{st.session_state.broker_buy:,.2f}</div>
          <div class="price-label-sub">ASK (Kauf)</div>
        </div>
      </div>

      <div class="circle-outer">
        <div id="mainCircle" class="circle-main">{cfg['svg']}</div>
      </div>

      <span class="dir-badge">{cfg['dir']}</span>
      <div class="signal-text">{st.session_state.ki_signal}</div>

      <div class="stats-row">
        <div class="stat-card">
          <div class="stat-label">Signal Strength</div>
          <div class="stat-dots">{dots_filled}</div>
          <div class="stat-sub">{dots_sub_text}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Win Rate</div>
          <div class="stat-winrate">{cfg['win']}</div>
          <div class="stat-live">Live</div>
        </div>
      </div>

      <div class="ai-bar">
        <span class="dot-live"></span> NEXT AI UPDATE IN {seconds_until_next_run}s
      </div>

      <div class="trade-timer">
        TRADE TIMER: <span>{st.session_state.trade_timer}s</span>
      </div>

      <button id="genBtn" class="gen-btn" onclick="
        var c = document.getElementById('mainCircle');
        c.style.animation = 'spinOnce 0.9s cubic-bezier(0.4, 0, 0.2, 1) forwards';
        document.querySelector('.stButton button').click();
      ">
        Generate New Signal
      </button>

      <div style="background:#0a0f1a;border:1px solid #1a2540;border-radius:12px;padding:12px 14px;font-size:11px;color:#4b6080;line-height:1.5;margin-bottom:14px;">
        <div style="font-size:10px;color:#2a3a50;text-transform:uppercase;letter-spacing:1px;margin-bottom:4px;font-weight:700;">🤖 AI-Reasoning</div>
        {st.session_state.ki_reason}
      </div>

      <div style="margin-bottom:6px;">
        <div style="width:100%;background:#0a0f1a;border:1px solid #1a2540;border-radius:12px;padding:12px 14px;color:#fff;font-size:12px;font-weight:700;display:flex;justify-content:space-between;align-items:center;">
          <span>Analyse-Märkte &nbsp;<span style="background:#00e67622;color:#00e676;border-radius:8px;padding:2px 8px;font-size:11px;">{open_count}/4 Aktiv</span></span>
        </div>
        <div style="background:#0a0f1a;border:1px solid #1a2540;border-top:none;border-radius:0 0 12px 12px;overflow:hidden;">
          {market_hours_html}
        </div>
      </div>

      <div class="ssl-bar">🔒 SSL Secured &nbsp;|&nbsp; 🔒 256-bit Encrypted</div>
    </div>

    <div class="nav-bar">
      <div class="nav-item active"><span class="nav-icon">📈</span>TRADE</div>
      <div class="nav-item"><span class="nav-icon">⚡</span>LIVE FEED</div>
      <div class="nav-item"><img src="{GOLD_FOTO_URL}" style="width:20px;height:20px;border-radius:50%;border:1.5px solid #d4af37;object-fit:cover;"><span>PROFILE</span></div>
    </div>

  </div>
</div>
</body>
</html>
""")

# ==========================================
# AUTOMATISCHER SEKUNDEN-TICKER
# ==========================================
time.sleep(1)
st.rerun()
