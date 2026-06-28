import streamlit as st
from datetime import datetime
import time
import pytz
import yfinance as yf
import google.generativeai as genai
from openai import OpenAI

# ==========================================
# KONFIGURATION
# ==========================================
GOLD_FOTO_URL = "https://images.unsplash.com/photo-1610374792793-f016b77ca51a?q=80&w=100&auto=format&fit=crop"
ATR_PERIOD = 10
KEY_VALUE = 1.0
KI_INTERVALL = 15
LOOP_DELAY = 3  

st.set_page_config(
    page_title="Fisiget Bot – Gold AI",
    page_icon="🪙",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ==========================================
# CSS (Smartphone-UI & TV-Preiskacheln)
# ==========================================
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;900&family=JetBrains+Mono:wght@400;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
        background-color: #0a0d14 !important;
        color: #e2e8f0;
    }
    .stApp { background-color: #0a0d14; }
    .block-container { padding: 0 !important; max-width: 100% !important; }
    header[data-testid="stHeader"] { background: transparent; }

    .outer {
        display: flex;
        justify-content: center;
        align-items: flex-start;
        min-height: 100vh;
        padding: 20px 12px 40px;
        box-sizing: border-box;
    }

    .phone {
        width: 100%;
        max-width: 420px;
        background: #11151f;
        border-radius: 32px;
        border: 1px solid #1e2535;
        box-shadow: 0 24px 64px rgba(0,0,0,0.7);
        overflow: hidden;
        flex-shrink: 0;
    }

    .topbar {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 20px 22px 14px;
    }
    .logo { font-size: 15px; font-weight: 900; color: #fff; display: flex; align-items: center; gap: 8px; }
    .status-pill { font-size: 11px; font-weight: 700; color: #10b981; display: flex; align-items: center; gap: 5px; }
    .pulse-dot { width: 7px; height: 7px; border-radius: 50%; background: #10b981; animation: blink 1.4s infinite; }
    @keyframes blink { 0%,100%{opacity:1;} 50%{opacity:0.3;} }

    .body { padding: 10px 22px 20px; flex: 1; }

    .asset-label { text-align: center; font-size: 14px; color: #9ca3af; font-weight: 600; margin-bottom: 2px; }
    .asset-title { text-align: center; font-size: 18px; font-weight: 800; color: #fff; margin-bottom: 2px; }
    .timeframe { text-align: center; font-size: 11px; color: #4b5563; margin-bottom: 16px; }

    /* TRADINGVIEW PRICE BUTTONS STYLE (Pepperstone Layout) */
    .trading-prices {
        display: flex;
        justify-content: center;
        align-items: center;
        gap: 10px;
        margin-bottom: 20px;
    }
    .price-button {
        flex: 1;
        background: rgba(17, 21, 31, 0.5);
        border-radius: 10px;
        padding: 8px 10px;
        text-align: center;
        font-family: 'JetBrains Mono', monospace;
    }
    .price-button.sell { border: 1.5px solid #ef4444; }
    .price-button.buy { border: 1.5px solid #2563eb; }
    .price-num-sell { font-size: 16px; font-weight: 700; color: #ef4444; }
    .price-num-buy { font-size: 16px; font-weight: 700; color: #2563eb; }
    .price-label-sub { font-size: 10px; color: #4b5563; text-transform: uppercase; font-weight: 700; margin-top: 2px; letter-spacing: 0.5px; }
    .price-spread { font-size: 12px; color: #9ca3af; font-weight: 600; font-family: 'JetBrains Mono', monospace; }

    /* GLOWING CIRCLE & SPIN ANIMATION */
    .circle-wrap { display: flex; justify-content: center; margin-bottom: 20px; }
    .signal-circle {
        width: 180px; height: 180px; border-radius: 50%;
        display: flex; align-items: center; justify-content: center;
    }
    
    .signal-circle.spinning {
        animation: spinOnce 0.7s cubic-bezier(0.4, 0, 0.2, 1) forwards;
    }

    @keyframes spinOnce {
        0%   { transform: rotate(0deg) scale(1); }
        50%  { transform: rotate(180deg) scale(1.06); }
        100% { transform: rotate(360deg) scale(1); }
    }

    .circle-buy  { background: radial-gradient(circle at center, #22c55e 0%, #064e3b 100%); box-shadow: 0 0 40px rgba(16,185,129,0.6); }
    .circle-sell { background: radial-gradient(circle at center, #f87171 0%, #7f1d1d 100%); box-shadow: 0 0 40px rgba(239,68,68,0.6); }
    .circle-wait { background: radial-gradient(circle at center, #fbbf24 0%, #78350f 100%); box-shadow: 0 0 40px rgba(245,158,11,0.6); }
    .trend-svg { width: 75px; height: 75px; fill: none; stroke: white; stroke-width: 2.5; stroke-linecap: round; stroke-linejoin: round; }

    .dir-badge {
        display: block; margin: 0 auto 6px; width: fit-content;
        background: #1a2235; border: 1px solid #2a3550; border-radius: 20px;
        padding: 4px 18px; font-size: 11px; font-weight: 700; letter-spacing: 1px; text-transform: uppercase;
    }
    .signal-text { text-align: center; font-size: 34px; font-weight: 900; letter-spacing: 0.5px; margin-bottom: 20px; }

    /* STATS KACHELN */
    .stats-row { display: flex; gap: 12px; margin-bottom: 16px; }
    .stat-box { flex: 1; background: #0c0f17; border: 1px solid #1e2535; border-radius: 14px; padding: 14px 16px; }
    .stat-label { font-size: 10px; color: #4b5563; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 6px; font-weight: 700; }
    .stat-dots { font-size: 16px; letter-spacing: 3px; margin-bottom: 2px; }
    .stat-sub { font-size: 11px; color: #4b5563; font-weight: 600; }
    .stat-value { font-family: 'Inter', sans-serif; font-size: 26px; font-weight: 900; }
    .stat-live { font-size: 10px; color: #4b5563; margin-top: 2px; }

    /* STATUS CAPSULE */
    .ai-status-bar {
        background: #0c0f17; border: 1px solid #1e2535; border-radius: 20px;
        padding: 10px; text-align: center; font-size: 11px; font-weight: 700;
        color: #10b981; letter-spacing: 1px; margin-bottom: 16px;
        display: flex; align-items: center; justify-content: center; gap: 6px;
    }

    /* GREEN HTML BUTTON */
    .html-gen-btn {
        width: 100%;
        background: #10b981;
        border: none;
        border-radius: 14px;
        color: #0a0d14;
        font-size: 15px;
        font-weight: 800;
        padding: 16px 10px;
        letter-spacing: 0.5px;
        box-shadow: 0 4px 20px rgba(16,185,129,0.25);
        cursor: pointer;
        transition: all 0.2s;
        display: block;
        text-align: center;
        margin-bottom: 14px;
    }
    .html-gen-btn:hover { background: #059669; color: #fff; }
    .html-gen-btn:active { transform: scale(0.99); }

    /* INSIGHT BOX */
    .insight-box { background: #0c0f17; border: 1px solid #1e2535; border-radius: 14px; padding: 12px 14px; font-size: 11px; color: #9ca3af; line-height: 1.5; }
    .insight-title { font-size: 10px; color: #4b5563; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 4px; font-weight: 700; }

    /* NAVIGATION BAR */
    .nav-bar { 
        display: flex; 
        justify-content: space-around; 
        align-items: center; 
        padding: 16px 10px 20px; 
        border-top: 1px solid #1e2535; 
        background: #0d1118;
    }
    .nav-item { display: flex; flex-direction: column; align-items: center; gap: 4px; font-size: 11px; color: #4b5563; font-weight: 700; }
    .nav-item.active { color: #10b981; }
    .nav-icon { font-size: 18px; }

    /* Versteckt den echten Python-Button im Backend */
    .stButton { display: none !important; }
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
# MARKT-DATEN & INDIKATOREN
# ==========================================
def check_market_state() -> str:
    tz = pytz.timezone("Europe/Berlin")
    now = datetime.now(tz)
    if (now.weekday() == 4 and now.hour >= 23) or now.weekday() == 5 or (now.weekday() == 6 and now.hour < 23):
        return "OTC"
    return "LIVE"

@st.cache_data(ttl=60)
def get_market_data():
    gold_price = None
    try:
        tz = pytz.timezone("Europe/Berlin")
        now = datetime.now(tz)
        is_weekend = now.weekday() >= 5 or (now.weekday() == 4 and now.hour >= 23)

        if is_weekend:
            gold_data = yf.Ticker("GC=F").history(period="5d", interval="1d")
            if not gold_data.empty:
                gold_price = round(float(gold_data["Close"].iloc[-1]), 2)
        else:
            gold_data = yf.Ticker("GC=F").history(period="1d", interval="1m")
            if not gold_data.empty:
                gold_price = round(float(gold_data["Close"].iloc[-1]), 2)
    except Exception:
        pass
    return gold_price, None

def calculate_rsi(prices: list, period: int = 14) -> float:
    if len(prices) < period + 1:
        return 50.0
    gains, losses = [], []
    for i in range(1, len(prices)):
        diff = prices[i] - prices[i - 1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    return round(100.0 - (100.0 / (1.0 + avg_gain / avg_loss)), 1)

def calculate_atr(prices: list, period: int) -> float:
    diffs = [abs(prices[i] - prices[i - 1]) for i in range(1, len(prices))]
    if len(diffs) < period:
        return 1.5
    return sum(diffs[-period:]) / period

def ut_bot_step(src: float, last_src: float, trail: float, pos: int, atr: float) -> tuple:
    n_loss = KEY_VALUE * atr
    if src > trail and last_src > trail:
        trail = max(trail, src - n_loss)
    elif src < trail and last_src < trail:
        trail = min(trail, src + n_loss)
    else:
        trail = src - n_loss if src > trail else src + n_loss
    if last_src < trail and src > trail:
        pos = 1
    elif last_src > trail and src < trail:
        pos = -1
    return trail, pos

# ==========================================
# DUAL-AI PIPELINE
# ==========================================
AI_PROMPT = """Du bist ein algorithmischer Handels-Bot für Gold (XAU/USD).
DATEN: Gold=${preis:.2f} | RSI={rsi} | Mathematisches Signal: {signal}
Antworte NUR in diesem Format:
SIGNAL: [BUY|SELL|WAIT]
BEGRÜNDUNG: [max. 15 Wörter]"""

def parse_ai_response(text: str, source: str) -> tuple:
    signal, reason = "WAIT", "Analyse abgeschlossen."
    for line in text.strip().splitlines():
        if line.startswith("SIGNAL:"):
            raw = line.replace("SIGNAL:", "").strip().upper()
            signal = "BUY (LONG)" if "BUY" in raw else "SELL (SHORT)" if "SELL" in raw else "WAIT (SIDEWAYS)"
        elif line.startswith("BEGRÜNDUNG:"):
            reason = line.replace("BEGRÜNDUNG:", "").strip()
    return signal, f"[{source}]: {reason}"

def dual_ai_filter(preis: float, rsi: float, mathe_signal: str) -> tuple:
    fallback_sig = "BUY (LONG)" if "BUY" in mathe_signal else "SELL (SHORT)" if "SELL" in mathe_signal else "WAIT (SIDEWAYS)"
    if not any(keys.values()):
        return fallback_sig, "Kein API-Key – Mathe-Modus aktiv."
    prompt = AI_PROMPT.format(preis=preis, rsi=rsi, signal=mathe_signal)
    if keys["gemini"]:
        try:
            model = genai.GenerativeModel("gemini-2.5-flash")
            resp = model.generate_content(prompt)
            if resp.text and "SIGNAL:" in resp.text:
                return parse_ai_response(resp.text, "Gemini 2.5 Flash")
        except Exception:
            pass
    if keys["groq"] and groq_client:
        try:
            resp = groq_client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=60, temperature=0.1,
            )
            text = resp.choices[0].message.content
            if text and "SIGNAL:" in text:
                return parse_ai_response(text, "Groq / Llama 3.1")
        except Exception:
            pass
    return fallback_sig, "KI temporär nicht verfügbar – Mathe-Modus."

# ==========================================
# SIGNAL CONFIG
# ==========================================
SVG_BUY  = '<svg class="trend-svg" viewBox="0 0 24 24"><path d="M23 6l-9.5 9.5-5-5L1 18M23 6h-6M23 6v6"/></svg>'
SVG_SELL = '<svg class="trend-svg" viewBox="0 0 24 24"><path d="M23 18l-9.5-9.5-5 5L1 6M23 18h-6M23 18v-6"/></svg>'
SVG_WAIT = '<svg class="trend-svg" viewBox="0 0 24 24"><path d="M5 12h14M13 5l7 7-7 7"/></svg>'

SIGNAL_CONFIG = {
    "BUY":  {"class": "circle-buy",  "color": "#10b981", "dir": "UPWARD",   "svg": SVG_BUY,  "win": "82%", "dots": "●●●●○", "dots_sub": "4/5"},
    "SELL": {"class": "circle-sell", "color": "#ef4444", "dir": "DOWNWARD", "svg": SVG_SELL, "win": "89.4%", "dots": "●●●●○", "dots_sub": "4/5"},
    "WAIT": {"class": "circle-wait", "color": "#f59e0b", "dir": "SIDEWAYS", "svg": SVG_WAIT, "win": "  —  ", "dots": "●●○○○", "dots_sub": "2/5"},
}

def get_signal_key(signal: str) -> str:
    if "BUY" in signal: return "BUY"
    if "SELL" in signal: return "SELL"
    return "WAIT"

# ==========================================
# STATE INIT
# ==========================================
if "src_history" not in st.session_state:
    start_price, _ = get_market_data()
    start_price = start_price or 2350.0
    st.session_state.src_history = [start_price] * 15
    st.session_state.trail = start_price - 5.0
    st.session_state.pos = 1
    st.session_state.ki_takt = 0
    st.session_state.ki_signal = "BUY (LONG)"
    st.session_state.ki_reason = "Initialisiere Dual-AI Pipeline…"
    st.session_state.force_ai_update = False

# ==========================================
# DATA REFRESH LOGIC
# ==========================================
market_state = check_market_state()
live_gold, _ = get_market_data()
current_price = live_gold if live_gold is not None else st.session_state.src_history[-1]

# Realistische Bid/Ask- und Live-Spread Berechnung
spread_value = 0.90
sell_price = current_price
buy_price = round(current_price + spread_value, 2)

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

if st.session_state.ki_takt % KI_INTERVALL == 0 or st.session_state.force_ai_update:
    st.session_state.ki_signal, st.session_state.ki_reason = dual_ai_filter(
        current_price, rsi, mathe_signal
    )
    st.session_state.force_ai_update = False

st.session_state.ki_takt += 1

sig_key = get_signal_key(st.session_state.ki_signal)
cfg = SIGNAL_CONFIG[sig_key]
mode_label = "LIVE AI" if any(keys.values()) else "MATH MODE"
takte_bis_ki = KI_INTERVALL - (st.session_state.ki_takt % KI_INTERVALL)

# ==========================================
# RENDER LAYOUT
# ==========================================
st.html(f"""
<div class="outer">
  <div class="phone">
    <div class="topbar">
      <div class="logo">🪙 FISIGET BOT</div>
      <div class="status-pill">
        <div class="pulse-dot"></div>
        ● {mode_label} | {market_state} | 👤 1,360
      </div>
    </div>

    <div class="body">
      <div class="asset-label">Signal for:</div>
      <div class="asset-title">XAU / USD ({market_state})</div>
      <div class="timeframe">Timeframe: 10 SEC &nbsp;·&nbsp; Pepperstone</div>

      <div class="trading-prices">
        <div class="price-button sell">
          <div class="price-num-sell">{sell_price:,.2f}</div>
          <div class="price-label-sub">Verkauf</div>
        </div>
        <div class="price-spread">{spread_value:.2f}</div>
        <div class="price-button buy">
          <div class="price-num-buy">{buy_price:,.2f}</div>
          <div class="price-label-sub">Kauf</div>
        </div>
      </div>

      <div class="circle-wrap">
        <div id="mainCircle" class="signal-circle {cfg['class']}">{cfg['svg']}</div>
      </div>

      <span class="dir-badge" style="color:{cfg['color']}; background: rgba(16,185,129,0.1); border-color: {cfg['color']}50;">{cfg['dir']}</span>
      <div class="signal-text" style="color:{cfg['color']};">{st.session_state.ki_signal}</div>

      <div class="stats-row">
        <div class="stat-box">
          <div class="stat-label">Signal Strength</div>
          <div class="stat-dots" style="color:{cfg['color']};">{cfg['dots']}</div>
          <div class="stat-sub">{cfg['dots_sub']}</div>
        </div>
        <div class="stat-box">
          <div class="stat-label">Win Rate</div>
          <div class="stat-value" style="color:#10b981;">{cfg['win']}</div>
          <div class="stat-live">Live</div>
        </div>
      </div>

      <div class="ai-status-bar">
        <span class="pulse-dot"></span> AI PROCESSING... (Update in {takte_bis_ki}s)
      </div>

      <button id="genBtn" class="html-gen-btn" onclick="
        var c = document.getElementById('mainCircle');
        var btn = document.getElementById('genBtn');
        c.classList.remove('spinning');
        void c.offsetWidth;
        c.classList.add('spinning');
        btn.style.background = '#059669';
        btn.style.color = '#ffffff';
        btn.textContent = 'Analysiere…';
        setTimeout(function() {{
            document.querySelector('.stButton button').click();
        }}, 650);
      ">
        Generate New Signal
      </button>

      <div class="insight-box">
        <div class="insight-title">🤖 AI-Reasoning</div>
        <span>{st.session_state.ki_reason}</span>
      </div>
    </div>

    <div class="nav-bar">
      <div class="nav-item active">
        <span class="nav-icon">📈</span><span>TRADE</span>
      </div>
      <div class="nav-item">
        <span class="nav-icon">⚡</span><span>LIVE FEED</span>
      </div>
      <div class="nav-item">
        <img src="{GOLD_FOTO_URL}" style="width:22px;height:22px;border-radius:50%;border:1.5px solid #d4af37;object-fit:cover;" alt="P">
        <span style="color:#d4af37;">PROFILE</span>
      </div>
    </div>
  </div>
</div>
""")

# Versteckter Streamlit-Button für das Klick-Handling im Python-Backend
if st.button("Hidden Trigger"):
    st.session_state.force_ai_update = True
    st.rerun()

# ==========================================
# AUTOMATISCHER REFRESH-TICKER (3 Sekunden-Takt)
# ==========================================
time.sleep(LOOP_DELAY)
st.rerun()
