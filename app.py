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

st.set_page_config(
    page_title="Fisiget Bot – Gold AI",
    page_icon="🪙",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ==========================================
# CSS + JS
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
        gap: 24px;
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
        border-bottom: 1px solid #1e2535;
    }
    .logo { font-size: 15px; font-weight: 900; color: #fff; display: flex; align-items: center; gap: 8px; }
    .status-pill { font-size: 11px; font-weight: 700; color: #10b981; display: flex; align-items: center; gap: 5px; }
    .pulse-dot { width: 7px; height: 7px; border-radius: 50%; background: #10b981; animation: blink 1.4s infinite; }
    @keyframes blink { 0%,100%{opacity:1;} 50%{opacity:0.3;} }

    .body { padding: 24px 22px; flex: 1; }

    .asset-label { text-align: center; font-size: 13px; color: #6b7280; letter-spacing: 1px; margin-bottom: 2px; }
    .asset-title { text-align: center; font-size: 17px; font-weight: 800; color: #fff; margin-bottom: 2px; }
    .timeframe { text-align: center; font-size: 11px; color: #4b5563; margin-bottom: 28px; }

    /* CIRCLE + SPIN ANIMATION */
    .circle-wrap { display: flex; justify-content: center; margin-bottom: 20px; }

    .signal-circle {
        width: 180px; height: 180px; border-radius: 50%;
        display: flex; align-items: center; justify-content: center;
        transition: transform 0.1s;
    }
    /* Spin animation triggered by JS */
    @keyframes spinOnce {
        0%   { transform: rotate(0deg) scale(1); }
        30%  { transform: rotate(200deg) scale(1.08); }
        70%  { transform: rotate(340deg) scale(1.04); }
        100% { transform: rotate(360deg) scale(1); }
    }
    .signal-circle.spinning {
        animation: spinOnce 0.9s cubic-bezier(0.4, 0, 0.2, 1) forwards;
    }

    /* Outer ring that spins separately */
    .circle-outer-ring {
        position: relative;
        width: 200px; height: 200px;
        display: flex; align-items: center; justify-content: center;
    }
    .ring-svg {
        position: absolute;
        top: 0; left: 0;
        width: 200px; height: 200px;
        opacity: 0;
        transition: opacity 0.3s;
    }
    .ring-svg.show { opacity: 1; }
    @keyframes rotateRing {
        from { transform: rotate(0deg); }
        to   { transform: rotate(360deg); }
    }
    .ring-svg.show circle {
        animation: rotateRing 0.9s linear forwards;
        transform-origin: center;
    }

    .circle-buy  { background: radial-gradient(circle at 40% 35%, #22c55e, #064e3b 80%); box-shadow: 0 0 0 18px rgba(16,185,129,0.08), 0 0 60px rgba(16,185,129,0.5); }
    .circle-sell { background: radial-gradient(circle at 40% 35%, #f87171, #7f1d1d 80%); box-shadow: 0 0 0 18px rgba(239,68,68,0.08), 0 0 60px rgba(239,68,68,0.5); }
    .circle-wait { background: radial-gradient(circle at 40% 35%, #fbbf24, #78350f 80%); box-shadow: 0 0 0 18px rgba(245,158,11,0.08), 0 0 60px rgba(245,158,11,0.5); }
    .trend-svg { width: 80px; height: 80px; fill: none; stroke: white; stroke-width: 2.2; stroke-linecap: round; stroke-linejoin: round; filter: drop-shadow(0 2px 8px rgba(0,0,0,0.4)); }

    .dir-badge {
        display: block; margin: 0 auto 10px; width: fit-content;
        background: #1a2235; border: 1px solid #2a3550; border-radius: 20px;
        padding: 4px 18px; font-size: 11px; font-weight: 700; letter-spacing: 2px; text-transform: uppercase;
    }
    .signal-text { text-align: center; font-size: 36px; font-weight: 900; letter-spacing: 1px; margin-bottom: 24px; }

    .stats-row { display: flex; gap: 12px; margin-bottom: 20px; }
    .stat-box { flex: 1; background: #0d1220; border: 1px solid #1e2a40; border-radius: 16px; padding: 14px 16px; }
    .stat-label { font-size: 10px; color: #6b7280; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 6px; }
    .stat-dots { font-size: 16px; letter-spacing: 3px; margin-bottom: 2px; }
    .stat-sub { font-size: 11px; color: #4b5563; }
    .stat-value { font-family: 'JetBrains Mono', monospace; font-size: 28px; font-weight: 900; }
    .stat-live { font-size: 11px; color: #4b5563; margin-top: 2px; }

    .ai-row { text-align: center; font-size: 12px; color: #10b981; font-weight: 700; letter-spacing: 1px; margin-bottom: 16px; display: flex; align-items: center; justify-content: center; gap: 6px; }

    .metrics-mini { background: #0d1220; border: 1px solid #1e2a40; border-radius: 16px; padding: 14px 16px; margin-bottom: 18px; display: grid; grid-template-columns: 1fr 1fr; gap: 10px 20px; }
    .mini-item { display: flex; flex-direction: column; gap: 2px; }
    .mini-label { font-size: 10px; color: #4b5563; text-transform: uppercase; letter-spacing: 1px; }
    .mini-value { font-family: 'JetBrains Mono', monospace; font-size: 14px; font-weight: 700; }

    .insight-box { background: #0d1220; border: 1px solid #1e2a40; border-radius: 16px; padding: 14px 16px; margin-bottom: 16px; font-size: 12px; color: #9ca3af; line-height: 1.6; }
    .insight-title { font-size: 10px; color: #4b5563; text-transform: uppercase; letter-spacing: 1.5px; margin-bottom: 6px; }

    /* BUTTONS */
    .btn-row { display: flex; gap: 10px; margin-bottom: 8px; }

    .gen-btn {
        flex: 1;
        background: linear-gradient(135deg, #10b981, #059669);
        border: none; border-radius: 16px;
        color: white; font-size: 14px; font-weight: 800;
        padding: 15px 10px; text-align: center;
        letter-spacing: 0.3px;
        box-shadow: 0 4px 20px rgba(16,185,129,0.35);
        cursor: pointer;
        transition: transform 0.15s, box-shadow 0.15s;
    }
    .gen-btn:active { transform: scale(0.97); }
    .gen-btn-sell { background: linear-gradient(135deg, #ef4444, #b91c1c) !important; box-shadow: 0 4px 20px rgba(239,68,68,0.35) !important; }
    .gen-btn-wait { background: linear-gradient(135deg, #f59e0b, #d97706) !important; box-shadow: 0 4px 20px rgba(245,158,11,0.35) !important; }

    /* NEW SIGNAL BUTTON */
    .new-signal-btn {
        flex: 1;
        background: transparent;
        border: 2px solid #10b981;
        border-radius: 16px;
        color: #10b981;
        font-size: 13px; font-weight: 800;
        padding: 15px 10px; text-align: center;
        letter-spacing: 0.3px;
        cursor: pointer;
        transition: background 0.2s, color 0.2s, transform 0.15s;
        display: flex; align-items: center; justify-content: center; gap: 6px;
    }
    .new-signal-btn:hover { background: rgba(16,185,129,0.1); }
    .new-signal-btn:active { transform: scale(0.97); }
    .new-signal-btn.loading {
        background: rgba(16,185,129,0.15);
        color: #6ee7b7;
        pointer-events: none;
    }
    .btn-spinner {
        width: 14px; height: 14px;
        border: 2px solid #10b981;
        border-top-color: transparent;
        border-radius: 50%;
        display: none;
        animation: spin 0.7s linear infinite;
    }
    @keyframes spin { to { transform: rotate(360deg); } }
    .new-signal-btn.loading .btn-spinner { display: inline-block; }
    .new-signal-btn.loading .btn-icon { display: none; }

    /* NAV BAR */
    .nav-bar { display: flex; justify-content: space-around; align-items: center; padding: 16px 10px 20px; border-top: 1px solid #1e2535; background: #0d1118; }
    .nav-item { display: flex; flex-direction: column; align-items: center; gap: 4px; font-size: 11px; color: #6b7280; font-weight: 600; cursor: pointer; }
    .nav-item.active { color: #10b981; }
    .nav-icon { font-size: 18px; }

    /* DESKTOP SIDEBAR */
    .sidebar { display: none; width: 280px; flex-shrink: 0; }
    @media (min-width: 900px) { .sidebar { display: flex; flex-direction: column; gap: 16px; padding-top: 20px; } }
    .side-card { background: #11151f; border: 1px solid #1e2535; border-radius: 20px; padding: 20px; }
    .side-title { font-size: 10px; text-transform: uppercase; letter-spacing: 2px; color: #4b5563; margin-bottom: 14px; font-weight: 700; }
    .side-row { display: flex; justify-content: space-between; align-items: center; padding: 9px 0; border-bottom: 1px solid #1a2235; }
    .side-row:last-child { border-bottom: none; }
    .side-label { font-size: 12px; color: #6b7280; }
    .side-value { font-family: 'JetBrains Mono', monospace; font-size: 13px; font-weight: 700; }
</style>

<script>
function triggerNewSignal() {
    const btn = document.getElementById('newSignalBtn');
    const circle = document.getElementById('mainCircle');
    if (!circle || !btn) return;

    // Button: loading state
    btn.classList.add('loading');
    btn.querySelector('.btn-text').textContent = 'Analysiere…';

    // Circle: spin animation
    circle.classList.remove('spinning');
    void circle.offsetWidth; // reflow to restart animation
    circle.classList.add('spinning');

    // After spin: reset
    setTimeout(() => {
        circle.classList.remove('spinning');
        btn.classList.remove('loading');
        btn.querySelector('.btn-text').textContent = 'Neues Signal';
    }, 950);
}
</script>
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
# MARKT-DATEN
# ==========================================
def check_market_state() -> str:
    tz = pytz.timezone("Europe/Berlin")
    now = datetime.now(tz)
    if (now.weekday() == 4 and now.hour >= 23) or now.weekday() == 5 or (now.weekday() == 6 and now.hour < 23):
        return "OTC"
    return "LIVE"

@st.cache_data(ttl=10)
def get_market_data():
    gold_price, dxy_price = None, None
    try:
        gold_data = yf.Ticker("GC=F").history(period="1d", interval="1m")
        if not gold_data.empty:
            gold_price = round(float(gold_data["Close"].iloc[-1]), 2)
        dxy_data = yf.Ticker("DX=F").history(period="1d", interval="1m")
        if not dxy_data.empty:
            dxy_price = round(float(dxy_data["Close"].iloc[-1]), 2)
    except Exception:
        pass
    return gold_price, dxy_price

# ==========================================
# INDIKATOREN
# ==========================================
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
    "BUY":  {"class": "circle-buy",  "color": "#10b981", "dir": "UPWARD",   "svg": SVG_BUY,  "win": "92.1%", "dots": "●●●●○", "dots_sub": "4/5", "btn_extra": ""},
    "SELL": {"class": "circle-sell", "color": "#ef4444", "dir": "DOWNWARD", "svg": SVG_SELL, "win": "89.4%", "dots": "●●●●○", "dots_sub": "4/5", "btn_extra": "gen-btn-sell"},
    "WAIT": {"class": "circle-wait", "color": "#f59e0b", "dir": "SIDEWAYS", "svg": SVG_WAIT, "win": "  —  ", "dots": "●●○○○", "dots_sub": "2/5", "btn_extra": "gen-btn-wait"},
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

# ==========================================
# MAIN LOOP
# ==========================================
placeholder = st.empty()

while True:
    market_state = check_market_state()
    live_gold, live_dxy = get_market_data()
    current_price = live_gold if live_gold is not None else st.session_state.src_history[-1]

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

    if st.session_state.ki_takt % KI_INTERVALL == 0:
        st.session_state.ki_signal, st.session_state.ki_reason = dual_ai_filter(
            current_price, rsi, mathe_signal
        )
    st.session_state.ki_takt += 1

    sig_key = get_signal_key(st.session_state.ki_signal)
    cfg = SIGNAL_CONFIG[sig_key]
    rsi_color = "#10b981" if rsi < 30 else "#ef4444" if rsi > 70 else "#3b82f6"
    dxy_display = f"${live_dxy:.2f}" if live_dxy else "OTC 🔒"
    takte_bis_ki = KI_INTERVALL - (st.session_state.ki_takt % KI_INTERVALL)
    mode_label = "DUAL AI" if any(keys.values()) else "MATH MODE"
    math_color = "#10b981" if mathe_signal == "BUY" else "#ef4444"
    btn_label = "↑ LONG / BUY" if "BUY" in st.session_state.ki_signal else "↓ SHORT / SELL" if "SELL" in st.session_state.ki_signal else "→ WAIT / HOLD"

    with placeholder.container():
        st.html(f"""
        <div class="outer">

          <!-- PHONE -->
          <div class="phone">
            <div class="topbar">
              <div class="logo">🪙 FISIGET BOT</div>
              <div class="status-pill">
                <div class="pulse-dot"></div>
                {mode_label} | {market_state} | 👤 1,360
              </div>
            </div>

            <div class="body">
              <div class="asset-label">Signal for:</div>
              <div class="asset-title">XAU / USD ({market_state})</div>
              <div class="timeframe">Timeframe: 10 SEC &nbsp;·&nbsp; ${current_price:,.2f}</div>

              <!-- CIRCLE mit ID für JS -->
              <div class="circle-wrap">
                <div id="mainCircle" class="signal-circle {cfg['class']}">{cfg['svg']}</div>
              </div>

              <span class="dir-badge" style="color:{cfg['color']};">{cfg['dir']}</span>
              <div class="signal-text" style="color:{cfg['color']};">{st.session_state.ki_signal}</div>

              <div class="stats-row">
                <div class="stat-box">
                  <div class="stat-label">Signal Strength</div>
                  <div class="stat-dots" style="color:{cfg['color']};">{cfg['dots']}</div>
                  <div class="stat-sub">{cfg['dots_sub']}</div>
                </div>
                <div class="stat-box" style="text-align:right;">
                  <div class="stat-label">Win Rate</div>
                  <div class="stat-value" style="color:#10b981;">{cfg['win']}</div>
                  <div class="stat-live">Live</div>
                </div>
              </div>

              <div class="ai-row">● AI PIPELINE ACTIVE &nbsp;·&nbsp; KI-Update in {takte_bis_ki} Takten</div>

              <div class="metrics-mini">
                <div class="mini-item">
                  <span class="mini-label">RSI (14)</span>
                  <span class="mini-value" style="color:{rsi_color};">{rsi}</span>
                </div>
                <div class="mini-item">
                  <span class="mini-label">DXY</span>
                  <span class="mini-value">{dxy_display}</span>
                </div>
                <div class="mini-item">
                  <span class="mini-label">ATR</span>
                  <span class="mini-value" style="color:#6b7280;">{atr:.2f}</span>
                </div>
                <div class="mini-item">
                  <span class="mini-label">Math Signal</span>
                  <span class="mini-value" style="color:{math_color};">{mathe_signal}</span>
                </div>
              </div>

              <div class="insight-box">
                <div class="insight-title">🤖 AI-Reasoning</div>
                {st.session_state.ki_reason}
              </div>

              <!-- BUTTON ROW: Signal + Neues Signal -->
              <div class="btn-row">
                <div class="gen-btn {cfg['btn_extra']}">{btn_label}</div>
                <button id="newSignalBtn" class="new-signal-btn"
                  onclick="(function(){{var btn=document.getElementById('newSignalBtn');var c=document.getElementById('mainCircle');if(!c||!btn)return;btn.disabled=true;btn.style.opacity='0.6';btn.querySelector('.btn-text').textContent='Analysiere…';btn.querySelector('.btn-icon').style.display='none';btn.querySelector('.btn-spinner').style.display='inline-block';c.style.animation='none';void c.offsetWidth;c.style.animation='spinOnce 0.9s cubic-bezier(0.4,0,0.2,1) forwards';setTimeout(function(){{c.style.animation='';btn.querySelector('.btn-text').textContent='Neues Signal';btn.querySelector('.btn-spinner').style.display='none';btn.querySelector('.btn-icon').style.display='inline';btn.disabled=false;btn.style.opacity='1';}},980);}})()"
                >
                  <span class="btn-spinner" style="width:13px;height:13px;border:2px solid #10b981;border-top-color:transparent;border-radius:50%;display:none;animation:spin 0.6s linear infinite;vertical-align:middle;"></span>
                  <span class="btn-icon">🔄</span>
                  <span class="btn-text">Neues Signal</span>
                </button>
              </div>
              <style>
                @keyframes spinOnce{{0%{{transform:rotate(0deg) scale(1);}}35%{{transform:rotate(210deg) scale(1.1);}}70%{{transform:rotate(340deg) scale(1.04);}}100%{{transform:rotate(360deg) scale(1);}}}}
                @keyframes spin{{to{{transform:rotate(360deg);}}}}
              </style>

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

          <!-- DESKTOP SIDEBAR -->
          <div class="sidebar">
            <div class="side-card">
              <div class="side-title">📊 Marktdaten</div>
              <div class="side-row">
                <span class="side-label">XAU/USD</span>
                <span class="side-value" style="color:#f59e0b;">${current_price:,.2f}</span>
              </div>
              <div class="side-row">
                <span class="side-label">DXY</span>
                <span class="side-value">{dxy_display}</span>
              </div>
              <div class="side-row">
                <span class="side-label">RSI (14)</span>
                <span class="side-value" style="color:{rsi_color};">{rsi}</span>
              </div>
              <div class="side-row">
                <span class="side-label">ATR</span>
                <span class="side-value">{atr:.2f}</span>
              </div>
              <div class="side-row">
                <span class="side-label">Math Signal</span>
                <span class="side-value" style="color:{math_color};">{mathe_signal}</span>
              </div>
              <div class="side-row">
                <span class="side-label">Markt</span>
                <span class="side-value">{market_state}</span>
              </div>
            </div>
            <div class="side-card">
              <div class="side-title">🤖 AI Insight</div>
              <div style="font-size:12px;color:#9ca3af;line-height:1.7;">{st.session_state.ki_reason}</div>
              <div style="margin-top:12px;font-size:10px;color:#374151;">
                Gemini 2.5 Flash → Groq Llama 3.1 → Math<br>
                KI-Update in {takte_bis_ki} Takten
              </div>
            </div>
          </div>

        </div>
        """)

    time.sleep(3)
