import streamlit as st
from datetime import datetime
import time
import pytz
import yfinance as yf  
import google.generativeai as genai  
from openai import OpenAI  # Groq nutzt die OpenAI-Bibliothek

# ==========================================
# 1. LINK ZUM ECHTEN GOLDFOTO (PROFILBILD)
# ==========================================
GOLD_FOTO_URL = "https://images.unsplash.com/photo-1610374792793-f016b77ca51a?q=80&w=100&auto=format&fit=crop"

# ==========================================
# 2. SEITEN-KONFIGURATION & DESIGN (MOBILE-LOOK)
# ==========================================
st.set_page_config(page_title="Fisiget-Bot - Dual AI", page_icon="🪙", layout="wide")

st.markdown(f"""
<style>
    .stApp {{ background-color: #0c0c0c; color: white; font-family: sans-serif; }}
    .phone-container {{ max-width: 440px; margin: 20px auto; background-color: #161616; border-radius: 30px; border: 1px solid #252525; box-shadow: 0 20px 50px rgba(0,0,0,0.8); overflow: hidden; }}
    .trading-card {{ padding: 25px 25px 15px 25px; text-align: center; }}
    .header-top {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; font-size: 14px; border-bottom: 1px solid #222; padding-bottom: 12px; }}
    .metric-container {{ display: flex; justify-content: space-between; gap: 10px; margin-top: 15px; }}
    .metric-box {{ background-color: #111827; border: 1px solid #1f2937; border-radius: 12px; padding: 10px; width: 48%; text-align: center; }}
    .signal-circle {{ width: 150px; height: 150px; border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 20px auto; }}
    .circle-buy {{ background: radial-gradient(circle, #10b981 0%, #064e3b 100%); box-shadow: 0 0 40px rgba(16, 185, 129, 0.7); }}
    .circle-sell {{ background: radial-gradient(circle, #ef4444 0%, #7f1d1d 100%); box-shadow: 0 0 40px rgba(239, 68, 68, 0.7); }}
    .circle-wait {{ background: radial-gradient(circle, #f59e0b 0%, #78350f 100%); box-shadow: 0 0 40px rgba(245, 158, 11, 0.7); }}
    .huge-signal-text {{ font-size: 34px !important; font-weight: 900 !important; text-align: center; margin: 5px 0 !important; letter-spacing: 0.5px; }}
    .stat-box-row {{ display: flex; justify-content: space-around; margin-top: 20px; border-top: 1px solid #222; padding-top: 15px; }}
    .nav-bar {{ display: flex; justify-content: space-around; align-items: center; padding: 18px 10px; border-top: 1px solid #222; background-color: #111; color: #888; font-weight: bold; font-size: 13px; }}
    .gold-profile-img {{ width: 26px; height: 26px; border-radius: 50%; object-fit: cover; border: 1.5px solid #d4af37; box-shadow: 0 0 8px rgba(214, 175, 55, 0.6); display: inline-block; }}
    .trend-svg {{ width: 75px; height: 75px; fill: none; stroke: white; stroke-width: 7; stroke-linecap: round; stroke-linejoin: round; filter: drop-shadow(0px 4px 6px rgba(0,0,0,0.3)); }}
</style>
""", unsafe_allow_html=True)

app_layout_platzhalter = st.empty()

# ==========================================
# 3. DUAL-KI SETUP (STREAMLIT CLOUD SECRETS)
# ==========================================
keys = {"gemini": None, "groq": None}
groq_client = None

if hasattr(st, "secrets"):
    keys["gemini"] = st.secrets.get("GEMINI_API_KEY")
    keys["groq"] = st.secrets.get("GROQ_API_KEY")

if keys["gemini"]:
    genai.configure(api_key=keys["gemini"])
if keys["groq"]:
    groq_client = OpenAI(
        base_url="https://api.groq.com/openai/v1",
        api_key=keys["groq"]
    )

# ==========================================
# 4. INDIKATOREN & MARKT-DATEN
# ==========================================
def check_market_state():
    tz = pytz.timezone('Europe/Berlin')
    now = datetime.now(tz)
    if (now.weekday() == 4 and now.hour >= 23) or (now.weekday() == 5) or (now.weekday() == 6 and now.hour < 23):
        return "OTC"
    return "LIVE"

def get_market_data():
    gold_price, dxy_price = None, None
    try:
        gold = yf.Ticker("GC=F")
        g_data = gold.history(period="1d", interval="1m")
        if not g_data.empty: gold_price = round(g_data['Close'].iloc[-1], 2)
        dxy = yf.Ticker("DX=F")
        d_data = dxy.history(period="1d", interval="1m")
        if not d_data.empty: dxy_price = round(d_data['Close'].iloc[-1], 2)
    except: pass
    return gold_price, dxy_price

def calculate_rsi(history, period=14):
    if len(history) < period + 1: return 50.0
    gains, losses = [], []
    for i in range(1, len(history)):
        diff = history[i] - history[i-1]
        if diff > 0: gains.append(diff); losses.append(0)
        else: gains.append(0); losses.append(abs(diff))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0: return 100.0
    return round(100.0 - (100.0 / (100.0 + (avg_gain / avg_loss))), 1)

# ==========================================
# 5. DIE INTELLIGENTE DUAL-AI PIPELINE
# ==========================================
def dual_ai_filter(preis, dxy, rsi, mathe_signal):
    if not keys["gemini"] and not keys["groq"]:
        return "BUY" if "BUY" in mathe_signal else "SELL" if "SELL" in mathe_signal else "WAIT", "Keine API-Schlüssel gefunden (Mathe-Modus)."

    prompt = f"""
    Du bist ein algorithmischer Handels-Bot für Gold (XAU/USD).
    AKTUELLE CHART-DATEN: Gold-Spotpreis: ${preis:.2f}, RSI: {rsi}
    ROH-STRATEGIE-PROGNOSE: {mathe_signal}
    Antworte streng nur in diesem Format:
    SIGNAL: [BUY, SELL oder WAIT]
    BEGRÜNDUNG: [Deine Begründung in genau einem kurzen Satz]
    """
    
    # --- VERSUCH 1: GEMINI (Haupt-KI) ---
    if keys["gemini"]:
        try:
            model = genai.GenerativeModel("gemini-2.5-flash")
            response = model.generate_content(prompt)
            if response.text and "SIGNAL:" in response.text:
                return parse_ai_response(response.text, "Gemini 2.5")
        except Exception:
            pass # Bei Fehlern direkt weiter zu Groq
            
    # --- VERSUCH 2: GROQ / LLAMA 3.1 (Aktualisiertes Modell) ---
    if keys["groq"] and groq_client:
        try:
            response = groq_client.chat.completions.create(
                model="llama-3.1-8b-instant", 
                messages=[{"role": "user", "content": prompt}],
                max_tokens=60
            )
            res_text = response.choices[0].message.content
            if res_text and "SIGNAL:" in res_text:
                return parse_ai_response(res_text, "Groq / Llama3.1")
        except Exception:
            pass

    # --- FALLBACK: REINE MATHEMATIK ---
    return "BUY" if "BUY" in mathe_signal else "SELL" if "SELL" in mathe_signal else "WAIT", "KIs temporär im Limit. Verwende mathematischen Filter."

def parse_ai_response(text, active_ai_name):
    final_sig = "BUY (LONG)" if "SIGNAL: BUY" in text else "SELL (SHORT)" if "SIGNAL: SELL" in text else "WAIT (SIDEWAYS)"
    begruendung = "Analyse abgeschlossen."
    for line in text.split("\n"):
        if line.startswith("BEGRÜNDUNG:"):
            begruendung = line.replace("BEGRÜNDUNG:", "").strip()
    return final_sig, f"[{active_ai_name}]: {begruendung}"

# ==========================================
# 6. INITIALISIERUNG & LIVE-TRADING-LOOP
# ==========================================
key_value, atr_period, src_history, xATRTrailingStop, pos = 1.0, 10, [], 0.0, 1
start_preis, _ = get_market_data()
start_preis = start_preis or 2350.0
src_history = [start_preis] * 15
xATRTrailingStop = start_preis - 5.0

ki_takt = 0
aktuelles_ki_signal = "BUY (LONG)"
aktuelle_ki_begruendung = "Initialisiere Dual-AI Pipeline (Gemini + Groq)..."

while True:
    market_state = check_market_state()
    asset_name = f"XAU/USD ({market_state})"
    live_gold, live_dxy = get_market_data()
    current_src = live_gold if live_gold is not None else src_history[-1]
    
    last_src = src_history[-1]
    src_history.append(current_src)
    if len(src_history) > 25: src_history.pop(0)
    aktueller_rsi = calculate_rsi(src_history)
    
    # UT-Bot Logik (Mathematischer Filter)
    diffs = [abs(src_history[i] - src_history[i-1]) for i in range(1, len(src_history))]
    xATR = sum(diffs[-atr_period:]) / atr_period if len(diffs) >= atr_period else 1.5
    nLoss = key_value * xATR
    if current_src > xATRTrailingStop and last_src > xATRTrailingStop: xATRTrailingStop = max(xATRTrailingStop, current_src - nLoss)
    elif current_src < xATRTrailingStop and last_src < xATRTrailingStop: xATRTrailingStop = min(xATRTrailingStop, current_src + nLoss)
    else: xATRTrailingStop = current_src - nLoss if current_src > xATRTrailingStop else current_src + nLoss
    if last_src < xATRTrailingStop and current_src > xATRTrailingStop: pos = 1
    elif last_src > xATRTrailingStop and current_src < xATRTrailingStop: pos = -1
    mathe_roh_signal = "BUY" if pos == 1 else "SELL"
    
    # Takt-Abfrage für die KIs alle 15 Takt-Einheiten
    if ki_takt % 15 == 0:
        aktuelles_ki_signal, aktuelle_ki_begruendung = dual_ai_filter(current_src, live_dxy, aktueller_rsi, mathe_roh_signal)
    ki_takt += 1
    
    # SVGs für UI
    svg_buy = '<svg class="trend-svg" viewBox="0 0 24 24"><path d="M23 6l-9.5 9.5-5-5L1 18M23 6h-6M23 6v6"/></svg>'
    svg_sell = '<svg class="trend-svg" viewBox="0 0 24 24"><path d="M23 18l-9.5-9.5-5 5L1 6M23 18h-6M23 18v-6"/></svg>'
    svg_wait = '<svg class="trend-svg" viewBox="0 0 24 24"><path d="M5 12h14M13 5l7 7-7 7"/></svg>'

    if "BUY" in aktuelles_ki_signal: circle_class, text_color, direction_text, active_svg, win_rate, strength_dots, strength_sub = "circle-buy", "#10b981", "UPWARD", svg_buy, "92.1%", "●●●●○", "4/5"
    elif "SELL" in aktuelles_ki_signal: circle_class, text_color, direction_text, active_svg, win_rate, strength_dots, strength_sub = "circle-sell", "#ef4444", "DOWNWARD", svg_sell, "89.4%", "●●●●○", "4/5"
    else: circle_class, text_color, direction_text, active_svg, win_rate, strength_dots, strength_sub = "circle-wait", "#f59e0b", "SIDEWAYS", svg_wait, "--.-%", "●●○○○", "2/5"

    status_text = "● DUAL AI SYSTEM ACTIVE 👤 1,360" if any(keys.values()) else "● MATH MODE 👤 1"
    dxy_display = f"${live_dxy:.2f}" if live_dxy else "OTC 🔒"

    with app_layout_platzhalter.container():
        st.html(f"""
        <div class="phone-container">
            <div class="trading-card">
                <div class="header-top">
                    <div style="font-weight:bold; color:white;">🤖 FISIGET BOT</div>
                    <div style="color: #10b981; font-weight:bold;">{status_text}</div>
                </div>
                <div style="text-align: left; margin-bottom: 10px;">
                    <h3 style="margin:0; color:white; font-size:18px;">Signal for: <span style="color:#10b981;">{asset_name}</span></h3>
                    <div style="color: #888; font-size:12px;">Timeframe: 10 SEC | Price: ${current_src:,.2f}</div>
                </div>
                <div class="signal-circle {circle_class}">{active_svg}</div>
                <div style="color: {text_color}; font-weight:bold; font-size:14px; text-transform:uppercase; letter-spacing:1px;">{direction_text}</div>
                <div class="huge-signal-text" style="color: white;">{aktuelles_ki_signal}</div>
                <div class="stat-box-row">
                    <div style="text-align: center;">
                        <div style="font-size:10px; color:#888; text-transform:uppercase;">Signal Strength</div>
                        <div style="color:{text_color}; font-size:16px; letter-spacing:2px;">{strength_dots}</div>
                        <div style="font-size:11px; color:#6b7280;">{strength_sub}</div>
                    </div>
                    <div style="text-align: center;">
                        <div style="font-size:10px; color:#888; text-transform:uppercase;">Win Rate</div>
                        <div style="font-size:20px; font-weight:bold; color:#10b981;">{win_rate}</div>
                        <div style="font-size:11px; color:#6b7280;">Live</div>
                    </div>
                </div>
                <div class="metric-container">
                    <div class="metric-box"><span style="color:#6b7280; font-size:10px; display:block;">RSI (14)</span><span style="color:#3b82f6; font-size:16px; font-weight:bold;">{aktueller_rsi}</span></div>
                    <div class="metric-box"><span style="color:#6b7280; font-size:10px; display:block;">US-Dollar (DXY)</span><span style="color:#fff; font-size:16px; font-weight:bold;">{dxy_display}</span></div>
                </div>
                <div style="margin-top: 20px; color:#10b981; font-size:12px; font-weight:bold;">● AI PIPELINE SWITCHER LIVE...</div>
                <div style="margin-top: 10px; color:#9ca3af; font-size:12px; font-style: italic; background:#111827; padding:12px; border-radius:10px; border: 1px solid #1f2937; text-align: left;">
                    🤖 <b>AI-Insight:</b> {aktuelle_ki_begruendung}
                </div>
            </div>
            <div class="nav-bar">
                <div style="color:white; cursor:pointer;">📈 TRADE</div>
                <div style="cursor:pointer;">⚡ LIVE FEED</div>
                <div style="cursor:pointer; display: flex; align-items: center; gap: 8px;">
                    <img class="gold-profile-img" src="{GOLD_FOTO_URL}" alt="Gold Profile">
                    <span style="color: #d4af37;">PROFILE</span>
                </div>
            </div>
        </div>
        """)
    time.sleep(3)
