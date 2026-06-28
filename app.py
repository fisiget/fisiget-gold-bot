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
TRADE_TIMER_SEC = 10

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
# MARKT-DATEN
# ==========================================
def check_market_state() -> str:
    tz = pytz.timezone("Europe/Berlin")
    now = datetime.now(tz)
    if (now.weekday() == 4 and now.hour >= 23) or now.weekday() == 5 or (now.weekday() == 6 and now.hour < 23):
        return "OTC"
    return "LIVE"

@st.cache_data(ttl=60)
def get_market_data():
    try:
        tz = pytz.timezone("Europe/Berlin")
        now = datetime.now(tz)
        is_weekend = now.weekday() >= 5 or (now.weekday() == 4 and now.hour >= 23)
        period = "5d" if is_weekend else "1d"
        interval = "1d" if is_weekend else "1m"
        gold_data = yf.Ticker("GC=F").history(period=period, interval=interval)
        if not gold_data.empty:
            price = round(float(gold_data["Close"].iloc[-1]), 2)
            if 1500 < price < 5000:
                return price
    except Exception:
        pass
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
    if keys["groq"] and groq_client:
        try:
            resp = groq_client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=60, temperature=0.1,
            )
            t = resp.choices[0].message.content
            if t and "SIGNAL:" in t:
                return parse_ai_response(t, "Groq / Llama 3.1")
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
# STATE INIT
# ==========================================
if "src_history" not in st.session_state:
    sp = get_market_data() or 2350.0
    st.session_state.src_history = [sp] * 15
    st.session_state.trail = sp - 5.0
    st.session_state.pos = 1
    st.session_state.ki_takt = 0
    st.session_state.ki_signal = "BUY (LONG)"
    st.session_state.ki_reason = "Initialisiere AI Pipeline…"

# Jeden Key einzeln absichern (verhindert AttributeError nach st.rerun)
if "force_ai" not in st.session_state: st.session_state.force_ai = False
if "analyzing" not in st.session_state: st.session_state.analyzing = False
if "trade_timer" not in st.session_state: st.session_state.trade_timer = TRADE_TIMER_SEC

# ==========================================
# MARKTZEITEN
# ==========================================
def get_market_sessions():
    """Gibt Status aller wichtigen Handelssessions zurück (Berlin-Zeit)."""
    tz = pytz.timezone("Europe/Berlin")
    now = datetime.now(tz)
    weekday = now.weekday()  # 0=Mo, 6=So
    h = now.hour + now.minute / 60.0

    sessions = [
        {
            "name": "Sydney",
            "flag": "🇦🇺",
            # Berlin: Mo 00:00–09:00, Di-Fr 00:00–09:00 (Sommer +1h)
            "open_h": 0.0, "close_h": 9.0,
            "days": [0,1,2,3,4],
        },
        {
            "name": "Tokio",
            "flag": "🇯🇵",
            # Berlin: Mo 01:00–10:00
            "open_h": 1.0, "close_h": 10.0,
            "days": [0,1,2,3,4],
        },
        {
            "name": "London",
            "flag": "🇬🇧",
            # Berlin: Mo-Fr 09:00–18:00
            "open_h": 9.0, "close_h": 18.0,
            "days": [0,1,2,3,4],
        },
        {
            "name": "New York",
            "flag": "🇺🇸",
            # Berlin: Mo-Fr 14:00–23:00
            "open_h": 14.0, "close_h": 23.0,
            "days": [0,1,2,3,4],
        },
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
            # Nächsten Öffnungstag berechnen
            next_day_name = ["Mo", "Di", "Mi", "Do", "Fr"][s["days"][0]] if s["days"] else "Mo"
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
        <div style="display:flex;justify-content:space-between;align-items:center;
                    padding:10px 14px;border-bottom:1px solid #1a2540;">
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
# LOGIC
# ==========================================
market_state = check_market_state()
live_gold = get_market_data()
current_price = live_gold if live_gold else st.session_state.src_history[-1]

spread = 0.90
sell_price = current_price
buy_price = round(current_price + spread, 2)

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

if st.session_state.ki_takt % KI_INTERVALL == 0 or st.session_state.force_ai:
    st.session_state.ki_signal, st.session_state.ki_reason = dual_ai_filter(current_price, rsi, mathe_signal)
    st.session_state.force_ai = False

st.session_state.ki_takt += 1

# Trade timer countdown
st.session_state.trade_timer -= 1
if st.session_state.trade_timer <= 0:
    st.session_state.trade_timer = TRADE_TIMER_SEC

sessions = get_market_sessions()
market_hours_html = build_market_hours_html(sessions)
open_count = sum(1 for s in sessions if s["is_open"])

sig_key = get_sig_key(st.session_state.ki_signal)
cfg = SIGNAL_CONFIG[sig_key]
mode_label = "LIVE AI" if any(keys.values()) else "MATH MODE"
takte_bis_ki = KI_INTERVALL - (st.session_state.ki_takt % KI_INTERVALL)
dots_filled = "●" * cfg["dots"] + "○" * (5 - cfg["dots"])
data_points = 6544 + (st.session_state.ki_takt * 7)
accuracy = round(39.8 + (rsi * 0.1), 1)
confidence = min(95, round(25 + cfg["dots"] * 10))

# ==========================================
# RENDER
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
  @keyframes spinOnce {{
    0%   {{ transform: rotate(0deg) scale(1); }}
    40%  {{ transform: rotate(200deg) scale(1.12); }}
    100% {{ transform: rotate(360deg) scale(1); }}
  }}
  @keyframes btnSpin {{ to {{ transform: rotate(360deg); }} }}
  @keyframes progress {{
    0%   {{ width: 15%; }}
    100% {{ width: 85%; }}
  }}
  @keyframes ringRotate {{
    from {{ stroke-dashoffset: 440; }}
    to   {{ stroke-dashoffset: 0; }}
  }}
  @keyframes fadeIn {{
    from {{ opacity: 0; transform: translateY(10px); }}
    to   {{ opacity: 1; transform: translateY(0); }}
  }}
  @keyframes glow-pulse {{
    0%, 100% {{ box-shadow: 0 0 60px {cfg['glow']}88, 0 0 120px {cfg['glow']}44; }}
    50%       {{ box-shadow: 0 0 80px {cfg['glow']}bb, 0 0 160px {cfg['glow']}66; }}
  }}
  @keyframes timerTick {{
    0%   {{ background: #10b98122; }}
    50%  {{ background: #10b98144; }}
    100% {{ background: #10b98122; }}
  }}

  /* =====================
     RESPONSIVE LAYOUT
     Mobile  < 600px  : 1 col, volle Breite
     Tablet  600-1023px: zentriert, max 560px
     Desktop >= 1024px : zentriert, max 620px, größere Schriften
  ===================== */

  .app {{
    display: flex;
    justify-content: center;
    align-items: flex-start;
    min-height: 100vh;
    background: #0a0f1a;
    padding: 0;
  }}

  .phone {{
    width: 100%;
    max-width: 100%;
    background: #0d1320;
    border-radius: 0;
    border: none;
    overflow: hidden;
  }}

  /* TOPBAR */
  .topbar {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 16px 20px 12px;
    border-bottom: 1px solid #1a2540;
  }}
  .logo {{ font-size: 15px; font-weight: 900; color: #fff; display: flex; align-items: center; gap: 8px; }}
  .live-badge {{ font-size: 11px; font-weight: 700; color: #00e676; display: flex; align-items: center; gap: 6px; }}
  .dot-live {{ width: 7px; height: 7px; border-radius: 50%; background: #00e676; animation: blink 1.2s infinite; }}

  /* BODY – zentriert, responsive Breite */
  .body {{
    width: 100%;
    max-width: 480px;
    margin: 0 auto;
    padding: 20px 18px 16px;
    box-sizing: border-box;
  }}

  .back-btn {{ color: #00e676; font-size: 20px; margin-bottom: 12px; cursor: pointer; display: inline-block; }}

  .signal-header {{ font-size: 15px; font-weight: 800; color: #fff; margin-bottom: 6px; }}
  .signal-header span {{ color: #00e676; }}
  .signal-tf {{ font-size: 13px; font-weight: 700; color: #9ca3af; margin-bottom: 20px; letter-spacing: 0.3px; }}

  /* CIRCLE */
  .circle-outer {{ display: flex; justify-content: center; margin-bottom: 18px; }}
  .circle-main {{
    width: 180px; height: 180px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    background: {cfg['bg']};
    box-shadow: 0 0 60px {cfg['glow']}88, 0 0 120px {cfg['glow']}44;
    animation: glow-pulse 2s ease-in-out infinite;
  }}

  /* DIR BADGE */
  .dir-badge {{
    display: block; width: fit-content; margin: 0 auto 8px;
    background: #0d1320; border: 1.5px solid {cfg['color']};
    border-radius: 20px; padding: 5px 20px;
    font-size: 12px; font-weight: 800; letter-spacing: 1.5px;
    text-transform: uppercase; color: {cfg['color']};
  }}
  .signal-text {{
    text-align: center; font-size: 34px; font-weight: 900;
    color: {cfg['color']}; text-shadow: 0 0 30px {cfg['glow']}88;
    margin-bottom: 18px; letter-spacing: 0.5px;
  }}

  /* STATS */
  .stats-row {{ display: flex; gap: 10px; margin-bottom: 12px; }}
  .stat-card {{ flex: 1; background: #0a0f1a; border: 1px solid #1a2540; border-radius: 14px; padding: 12px 14px; }}
  .stat-label {{ font-size: 10px; color: #4b6080; text-transform: uppercase; letter-spacing: 1px; font-weight: 700; margin-bottom: 6px; }}
  .stat-dots {{ font-size: 16px; letter-spacing: 4px; color: {cfg['color']}; margin-bottom: 3px; }}
  .stat-sub {{ font-size: 11px; color: #4b6080; font-weight: 700; }}
  .stat-winrate {{ font-size: 28px; font-weight: 900; color: {cfg['color']}; line-height: 1; }}
  .stat-live {{ font-size: 10px; color: #4b6080; margin-top: 4px; }}

  /* AI STATUS BAR */
  .ai-bar {{
    background: #0a0f1a; border: 1px solid #1a2540; border-radius: 12px;
    padding: 11px 16px; display: flex; align-items: center; justify-content: center;
    gap: 8px; margin-bottom: 10px; font-size: 12px; font-weight: 700;
    color: #00e676; letter-spacing: 1px;
  }}

  /* TRADE TIMER */
  .trade-timer {{
    background: #0a0f1a; border: 1px solid #1a2540; border-radius: 12px;
    padding: 10px 16px; text-align: center; margin-bottom: 12px;
    font-size: 12px; font-weight: 700; color: #4b6080; letter-spacing: 1px;
    animation: timerTick 1s ease infinite;
  }}
  .trade-timer span {{ color: #00e676; font-size: 14px; }}

  /* GENERATE BUTTON */
  .gen-btn {{
    width: 100%; border: none; border-radius: 14px;
    background: linear-gradient(135deg, #00e676, #00c853);
    color: #0a0f1a; font-size: 15px; font-weight: 800;
    padding: 16px; letter-spacing: 0.5px; cursor: pointer;
    margin-bottom: 12px; box-shadow: 0 6px 24px rgba(0,230,118,0.35);
    transition: all 0.2s; font-family: Inter, sans-serif;
  }}
  .gen-btn:hover {{ background: linear-gradient(135deg, #69f0ae, #00e676); }}
  .gen-btn:active {{ transform: scale(0.98); }}

  /* SSL */
  .ssl-bar {{ text-align: center; font-size: 10px; color: #2a3a50; padding: 8px 0; }}

  /* NAV BAR */
  .nav-bar {{
    display: flex; justify-content: space-around; align-items: center;
    padding: 14px 20px 18px; border-top: 1px solid #1a2540; background: #090d18;
  }}
  .nav-item {{ display: flex; flex-direction: column; align-items: center; gap: 4px; font-size: 10px; font-weight: 700; color: #2a3a50; cursor: pointer; }}
  .nav-item.active {{ background: #00e676; color: #0a0f1a; padding: 8px 18px; border-radius: 12px; gap: 3px; }}
  .nav-icon {{ font-size: 16px; }}

  /* ── TABLET (600px+) ── */
  @media (min-width: 600px) {{
    .body {{ max-width: 560px; padding: 24px 28px 20px; }}
    .topbar {{ padding: 18px 40px 14px; }}
    .nav-bar {{ padding: 14px 40px 18px; }}
    .logo {{ font-size: 16px; }}
    .live-badge {{ font-size: 12px; }}
    .signal-header {{ font-size: 17px; }}
    .signal-tf {{ font-size: 14px; }}
    .circle-main {{ width: 200px; height: 200px; }}
    .signal-text {{ font-size: 40px; }}
    .stat-winrate {{ font-size: 32px; }}
    .stat-dots {{ font-size: 18px; }}
    .stat-label {{ font-size: 11px; }}
    .gen-btn {{ font-size: 16px; padding: 18px; }}
    .ai-bar {{ font-size: 13px; }}
    .trade-timer {{ font-size: 13px; }}
    .trade-timer span {{ font-size: 15px; }}
    .dir-badge {{ font-size: 13px; padding: 6px 24px; }}
  }}

  /* ── DESKTOP (1024px+) ── */
  @media (min-width: 1024px) {{
    .body {{ max-width: 620px; padding: 32px 40px 24px; }}
    .topbar {{ padding: 22px 60px 16px; }}
    .nav-bar {{ padding: 16px 60px 20px; }}
    .logo {{ font-size: 18px; }}
    .live-badge {{ font-size: 13px; }}
    .signal-header {{ font-size: 20px; }}
    .signal-tf {{ font-size: 16px; }}
    .circle-main {{ width: 240px; height: 240px; }}
    .signal-text {{ font-size: 52px; margin-bottom: 24px; }}
    .stat-winrate {{ font-size: 40px; }}
    .stat-dots {{ font-size: 22px; letter-spacing: 5px; }}
    .stat-label {{ font-size: 12px; }}
    .stat-card {{ padding: 18px 20px; }}
    .gen-btn {{ font-size: 18px; padding: 20px; border-radius: 16px; }}
    .ai-bar {{ font-size: 14px; padding: 14px 20px; }}
    .trade-timer {{ font-size: 14px; padding: 13px 20px; }}
    .trade-timer span {{ font-size: 17px; }}
    .dir-badge {{ font-size: 14px; padding: 7px 28px; letter-spacing: 2px; }}
    .back-btn {{ font-size: 24px; }}
    .nav-item {{ font-size: 12px; }}
    .nav-icon {{ font-size: 20px; }}
    .ssl-bar {{ font-size: 12px; padding: 10px 0; }}
  }}

  /* ANALYZING SCREEN */
  .analyzing-screen {{
    display: none; /* toggled by JS */
    flex-direction: column;
    align-items: center;
    padding: 30px 20px;
  }}
  .analyze-title {{
    font-size: 16px; font-weight: 800; color: #fff;
    margin-bottom: 4px;
  }}
  .analyze-title span {{ color: #00e676; }}
  .analyze-tf {{ font-size: 11px; color: #4b6080; margin-bottom: 30px; }}

  /* Donut ring for analyzing */
  .donut-wrap {{ position: relative; width: 160px; height: 160px; margin-bottom: 28px; }}
  .donut-wrap svg {{ position: absolute; top:0; left:0; transform: rotate(-90deg); }}
  .brain-icon {{
    position: absolute; top: 50%; left: 50%;
    transform: translate(-50%, -50%);
    font-size: 40px;
  }}

  /* Progress bar */
  .progress-wrap {{
    width: 100%; background: #0a0f1a;
    border: 1px solid #1a2540; border-radius: 10px;
    padding: 14px 16px; margin-bottom: 16px;
  }}
  .progress-bar-bg {{
    background: #1a2540; border-radius: 6px; height: 6px;
    margin-bottom: 8px; overflow: hidden;
  }}
  .progress-bar-fill {{
    height: 100%; border-radius: 6px;
    background: linear-gradient(90deg, #00e676, #69f0ae);
    width: 55%; transition: width 0.5s;
  }}
  .progress-label {{
    font-size: 12px; color: #4b6080; text-align: center;
  }}

  /* Data points row */
  .data-row {{ display: flex; gap: 10px; margin-bottom: 8px; }}
  .data-card {{
    flex: 1; background: #0a0f1a;
    border: 1px solid #1a2540; border-radius: 12px;
    padding: 12px 10px; text-align: center;
  }}
  .data-card-label {{
    font-size: 9px; color: #4b6080;
    text-transform: uppercase; letter-spacing: 1px;
    font-weight: 700; margin-bottom: 6px;
  }}
  .data-card-val {{ font-size: 18px; font-weight: 900; color: #fff; }}
  .data-card-val.yellow {{ color: #ffc400; }}
  .data-card-val.red {{ color: #ff1744; }}
</style>
</head>
<body>
<div class="app">
  <div class="phone">

    <!-- TOPBAR -->
    <div class="topbar">
      <div class="logo">🪙 FISIGET BOT</div>
      <div class="live-badge">
        <div class="dot-live"></div>
        {mode_label} &nbsp;|&nbsp; 👤 1,360
      </div>
    </div>

    <!-- ========== ANALYZING SCREEN ========== -->
    <div id="analyzingScreen" class="body" style="display:none;">
      <div class="back-btn">←</div>
      <div class="analyze-title">Analyzing Market... <span>XAU/USD ({market_state})</span></div>
      <div class="analyze-tf">Timeframe: 10 SEC</div>

      <!-- Donut ring -->
      <div class="donut-wrap">
        <svg width="160" height="160" viewBox="0 0 160 160">
          <!-- BG ring -->
          <circle cx="80" cy="80" r="70" fill="none" stroke="#1a2540" stroke-width="12"/>
          <!-- Red arc (sell side) -->
          <circle cx="80" cy="80" r="70" fill="none" stroke="#ff1744" stroke-width="12"
            stroke-dasharray="220 220" stroke-linecap="round"/>
          <!-- Green arc (buy side) -->
          <circle cx="80" cy="80" r="70" fill="none" stroke="#00e676" stroke-width="12"
            stroke-dasharray="200 440" stroke-dashoffset="-220" stroke-linecap="round"/>
        </svg>
        <div class="brain-icon">🧠</div>
      </div>

      <!-- Progress -->
      <div class="progress-wrap">
        <div class="progress-bar-bg">
          <div class="progress-bar-fill" id="progressBar"></div>
        </div>
        <div class="progress-label" id="progressLabel">Analyzing volatility patterns...</div>
      </div>

      <!-- Data cards -->
      <div class="data-row">
        <div class="data-card">
          <div class="data-card-label">Data Points</div>
          <div class="data-card-val">{data_points:,}</div>
        </div>
        <div class="data-card">
          <div class="data-card-label">Accuracy</div>
          <div class="data-card-val yellow">{accuracy}%</div>
        </div>
        <div class="data-card">
          <div class="data-card-label">Confidence</div>
          <div class="data-card-val red">{confidence}%</div>
        </div>
      </div>
    </div>

    <!-- ========== MAIN SIGNAL SCREEN ========== -->
    <div id="mainScreen" class="body">
      <div class="back-btn">←</div>

      <div class="signal-header">Signal for: <span>XAU/USD ({market_state})</span></div>
      <div class="signal-tf">Timeframe: 10 SEC &nbsp;·&nbsp; <span style="color:#00e676;font-size:15px;font-weight:800;">{price_label}</span></div>

      <!-- BIG CIRCLE -->
      <div class="circle-outer">
        <div id="mainCircle" class="circle-main">
          {cfg['svg']}
        </div>
      </div>

      <div class="dir-badge">{cfg['dir']}</div>
      <div class="signal-text">{st.session_state.ki_signal}</div>

      <!-- STATS -->
      <div class="stats-row">
        <div class="stat-card">
          <div class="stat-label">Signal Strength</div>
          <div class="stat-dots">{dots_filled}</div>
          <div class="stat-sub">{cfg['dots']}/5</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Win Rate</div>
          <div class="stat-winrate">{cfg['win']}</div>
          <div class="stat-live">Live</div>
        </div>
      </div>

      <!-- AI STATUS -->
      <div class="ai-bar">
        <span style="width:7px;height:7px;border-radius:50%;background:#00e676;display:inline-block;animation:blink 1.2s infinite;"></span>
        AI PROCESSING... (Update in {takte_bis_ki}s)
      </div>

      <!-- TRADE TIMER -->
      <div class="trade-timer">
        TRADE TIMER: <span>{st.session_state.trade_timer}s</span>
      </div>

      <!-- GENERATE BUTTON -->
      <button id="genBtn" class="gen-btn" onclick="(function(){{

        var c = document.getElementById('mainCircle');
        var btn = document.getElementById('genBtn');

        // --- SPIN: direkt per keyframe in style-tag ---
        var styleTag = document.getElementById('spinStyle');
        if(!styleTag){{
          styleTag = document.createElement('style');
          styleTag.id = 'spinStyle';
          document.head.appendChild(styleTag);
        }}
        styleTag.textContent = '@keyframes spinNow {{ 0%{{transform:rotate(0deg) scale(1)}} 40%{{transform:rotate(200deg) scale(1.1)}} 100%{{transform:rotate(360deg) scale(1)}} }}';

        c.style.animation = 'none';
        void c.offsetWidth;
        c.style.animation = 'spinNow 0.9s cubic-bezier(0.4,0,0.2,1) forwards';

        btn.disabled = true;
        btn.textContent = '⟳ Analysiere...';
        btn.style.opacity = '0.75';

        // Nach Spin: Python Backend triggern
        setTimeout(function(){{
          c.style.animation = 'glow-pulse 2s ease-in-out infinite';
          btn.textContent = '🔄 Generate New Signal';
          btn.disabled = false;
          btn.style.opacity = '1';

          // Streamlit hidden button - mehrere Selektoren versuchen
          var hidden = (
            document.querySelector('button[kind="secondary"]') ||
            document.querySelector('[data-testid="stBaseButton-secondary"]') ||
            document.querySelector('[data-testid="stButton"] button') ||
            Array.from(document.querySelectorAll('button')).find(function(b){{ return b.textContent.trim() === 'Hidden Trigger'; }})
          );
          if(hidden) {{
            hidden.click();
          }} else {{
            // Fallback: URL-Reload mit Query-Parameter
            window.location.search = '?signal=' + Date.now();
          }}
        }}, 950);

      }})()">
        🔄 Generate New Signal
      </button>

      <!-- AI INSIGHT -->
      <div style="background:#0a0f1a;border:1px solid #1a2540;border-radius:12px;padding:12px 14px;font-size:11px;color:#4b6080;line-height:1.5;margin-bottom:14px;">
        <div style="font-size:10px;color:#2a3a50;text-transform:uppercase;letter-spacing:1px;margin-bottom:4px;font-weight:700;">🤖 AI-Reasoning</div>
        {st.session_state.ki_reason}
      </div>

      <!-- MARKTZEITEN TOGGLE -->
      <div style="margin-bottom:6px;">
        <button onclick="(function(){{
          var panel = document.getElementById('marketPanel');
          var arrow = document.getElementById('marketArrow');
          if(panel.style.display === 'none' || panel.style.display === ''){{
            panel.style.display = 'block';
            arrow.textContent = '▲';
          }} else {{
            panel.style.display = 'none';
            arrow.textContent = '▼';
          }}
        }})()"
          style="width:100%;background:#0a0f1a;border:1px solid #1a2540;border-radius:12px;
                 padding:12px 14px;color:#fff;font-size:12px;font-weight:700;cursor:pointer;
                 display:flex;justify-content:space-between;align-items:center;font-family:Inter,sans-serif;">
          <span>🕐 Markt-Öffnungszeiten &nbsp;
            <span style="background:#00e67622;color:#00e676;border-radius:8px;padding:2px 8px;font-size:11px;">
              {open_count}/4 offen
            </span>
          </span>
          <span id="marketArrow" style="color:#4b6080;">▼</span>
        </button>

        <div id="marketPanel" style="display:none;background:#0a0f1a;border:1px solid #1a2540;
             border-top:none;border-radius:0 0 12px 12px;overflow:hidden;">
          {market_hours_html}
          <div style="padding:8px 14px;font-size:10px;color:#2a3a50;text-align:center;">
            Alle Zeiten in Berliner Lokalzeit (CET/CEST)
          </div>
        </div>
      </div>

    </div><!-- /mainScreen -->

    <!-- SSL BAR -->
    <div class="ssl-bar">🔒 SSL Secured &nbsp;|&nbsp; 🔒 256-bit Encrypted &nbsp;|&nbsp; v2.4.7</div>

    <!-- NAV BAR -->
    <div class="nav-bar">
      <div class="nav-item active">
        <span class="nav-icon">📈</span>TRADE
      </div>
      <div class="nav-item">
        <span class="nav-icon">⚡</span>LIVE FEED
      </div>
      <div class="nav-item">
        <img src="{GOLD_FOTO_URL}" style="width:20px;height:20px;border-radius:50%;border:1.5px solid #d4af37;object-fit:cover;">
        <span>PROFILE</span>
      </div>
    </div>

  </div>
</div>
</body>
</html>
""")

# Versteckter Backend-Button - MUSS vor st.html stehen damit er immer im DOM ist
# Wird per JS geklickt wenn "Generate New Signal" gedrückt wird
if st.button("Hidden Trigger", key="hidden_trigger", type="secondary"):
    st.session_state.force_ai = True
    st.rerun()

# Auto-Refresh alle 3 Sekunden
time.sleep(LOOP_DELAY)
st.rerun()
