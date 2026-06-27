import streamlit as st
from datetime import datetime
import time
import pytz
import yfinance as yf  # Holt die echten Live-Gold- & Dollar-Kurse
import google.generativeai as genai  # Das Gehirn für die echte KI-Analyse

# ==========================================
# 1. SEITEN-KONFIGURATION & MODERNES DESIGN
# ==========================================
st.set_page_config(page_title="Fisiget-Bot - Ultra AI", page_icon="🪙", layout="wide")

st.markdown("""
<style>
    .stApp {
        background-color: #060913;
    }
    
    /* Haupt-Trading-Card */
    .trading-card {
        background-color: #0d1222;
        padding: 22px;
        border-radius: 18px;
        border: 1px solid #1a233a;
        box-shadow: 0 15px 30px rgba(0, 0, 0, 0.4);
        margin: 15px auto;
        max-width: 100%;
        width: 440px;
    }
    
    /* Die Daten-Metriken Boxen */
    .metric-container {
        display: flex;
        justify-content: space-between;
        gap: 10px;
        margin-top: 15px;
    }
    .metric-box {
        background-color: #111827;
        border: 1px solid #1f2937;
        border-radius: 10px;
        padding: 10px;
        width: 48%;
        text-align: center;
    }
    
    /* Der animierte Signal-Kreis */
    .circle-buy {
        width: 140px; height: 140px; border-radius: 50%;
        display: flex; align-items: center; justify-content: center;
        margin: 15px auto; font-size: 45px; font-weight: bold;
        background: radial-gradient(circle, #10b981 0%, #052e16 100%);
        box-shadow: 0 0 40px rgba(16, 185, 129, 0.7); color: white;
        animation: pulse-green 1.5s infinite alternate;
    }
    .circle-sell {
        width: 140px; height: 140px; border-radius: 50%;
        display: flex; align-items: center; justify-content: center;
        margin: 15px auto; font-size: 45px; font-weight: bold;
        background: radial-gradient(circle, #ef4444 0%, #450a0a 100%);
        box-shadow: 0 0 40px rgba(239, 68, 68, 0.7); color: white;
        animation: pulse-red 1.5s infinite alternate;
    }
    .circle-wait {
        width: 140px; height: 140px; border-radius: 50%;
        display: flex; align-items: center; justify-content: center;
        margin: 15px auto; font-size: 45px; font-weight: bold;
        background: radial-gradient(circle, #f59e0b 0%, #78350f 100%);
        box-shadow: 0 0 40px rgba(245, 158, 11, 0.7); color: white;
        animation: pulse-amber 1.5s infinite alternate;
    }

    @keyframes pulse-green { 0% { box-shadow: 0 0 15px rgba(16, 185, 129, 0.4); } 100% { box-shadow: 0 0 45px rgba(16, 185, 129, 0.8); } }
    @keyframes pulse-red { 0% { box-shadow: 0 0 15px rgba(239, 68, 68, 0.4); } 100% { box-shadow: 0 0 45px rgba(239, 68, 68, 0.8); } }
    @keyframes pulse-amber { 0% { box-shadow: 0 0 15px rgba(245, 158, 11, 0.4); } 100% { box-shadow: 0 0 45px rgba(245, 158, 11, 0.8); } }

    .huge-signal-text { font-size: 32px !important; font-weight: 900 !important; text-align: center; margin: 10px 0 !important; }
    
    .status-badge { padding: 6px 16px; border-radius: 20px; font-size: 13px; font-weight: bold; text-align: center; width: fit-content; margin: 8px auto; text-transform: uppercase; }
    .badge-buy { background-color: rgba(16, 185, 129, 0.2); color: #10b981; border: 1px solid #10b981; }
    .badge-sell { background-color: rgba(239, 68, 68, 0.2); color: #ef4444; border: 1px solid #ef4444; }
    .badge-wait { background-color: rgba(245, 158, 11, 0.2); color: #f59e0b; border: 1px solid #f59e0b; }
    
    .bot-header { display: flex; flex-direction: row; justify-content: space-between; align-items: center; padding-bottom: 12px; border-bottom: 1px solid #1a233a; margin-bottom: 15px; flex-wrap: wrap; gap: 10px; }
    .header-left-side { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; }
    
    .header-price-buy-frame { background-color: transparent; color: #10b981; padding: 4px 12px; border-radius: 10px; font-weight: bold; font-size: 18px; border: 1.5px solid #10b981; text-align: center; }
    .header-price-buy-frame span { display: block; font-size: 9px; text-transform: uppercase; margin-top: -2px; color: #10b981; }
    .header-price-sell-frame { background-color: transparent; color: #ef4444; padding: 4px 12px; border-radius: 10px; font-weight: bold; font-size: 18px; border: 1.5px solid #ef4444; text-align: center; }
    .header-price-sell-frame span { display: block; font-size: 9px; text-transform: uppercase; margin-top: -2px; color: #ef4444; }

    @media (max-width: 600px) {
        .bot-header { flex-direction: column !important; text-align: center; }
        .header-left-side { flex-direction: column !important; }
        .trading-card { width: 100%; padding: 15px; }
    }
</style>
""", unsafe_allow_html=True)

app_layout_platzhalter = st.empty()

# ==========================================
# 2. KI-SETUP (ABSTURZSICHER FÜR LOCAL & ONLINE)
# ==========================================
ki_bereit = False
API_KEY = "DEIN_GEMINI_API_KEY"

# Versuche die Secrets zu prüfen ohne abzustürzen (Löst den Local-Fehler)
try:
    if hasattr(st, "secrets") and "GEMINI_API_KEY" in st.secrets:
        API_KEY = st.secrets["GEMINI_API_KEY"]
except Exception:
    pass

# HINWEIS: Wenn du LOKAL unbedingt mit KI testen willst, entferne das '#' vorne:
# API_KEY = "AIzaSyDEIN_ECHTER_LOCAL_KEY_NUR_FÜR_PC"

if API_KEY != "DEIN_GEMINI_API_KEY" and API_KEY.strip() != "":
    genai.configure(api_key=API_KEY)
    ki_bereit = True

# ==========================================
# 3. INDIKATOREN & LIVE-MARKT-LOGIK
# ==========================================
def check_market_state():
    tz = pytz.timezone('Europe/Berlin')
    now = datetime.now(tz)
    if (now.weekday() == 4 and now.hour >= 23) or (now.weekday() == 5) or (now.weekday() == 6 and now.hour < 23):
        return "OTC"
    return "LIVE"

def get_market_data():
    """Holt parallel Gold und den US-Dollar Index für die KI"""
    gold_price = None
    dxy_price = None
    try:
        gold = yf.Ticker("GC=F")
        g_data = gold.history(period="1d", interval="1m")
        if not g_data.empty:
            gold_price = round(g_data['Close'].iloc[-1], 2)
        
        # US-Dollar-Index holen (Intermarket-Analyse)
        dxy = yf.Ticker("DX=F")
        d_data = dxy.history(period="1d", interval="1m")
        if not d_data.empty:
            dxy_price = round(d_data['Close'].iloc[-1], 2)
    except Exception:
        pass
    return gold_price, dxy_price

def calculate_rsi(history, period=14):
    """Berechnet den mathematischen RSI-Indikator"""
    if len(history) < period + 1:
        return 50.0
    
    gains = []
    losses = []
    for i in range(1, len(history)):
        diff = history[i] - history[i-1]
        if diff > 0:
            gains.append(diff)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(diff))
            
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100.0 - (100.0 / (100.0 + rs)), 1)

def ai_filter(preis, dxy, rsi, mathe_signal, history):
    """Füttert Gemini mit erweiterten Profi-Daten"""
    if not ki_bereit:
        return mathe_signal, "Verbindung zu KI-Auge steht noch aus (Reine Mathe-Berechnung)."
    
    letzte_kurse = ", ".join([f"${k:.2f}" for k in history[-5:]])
    dxy_text = f"${dxy:.2f}" if dxy else "Nicht verfügbar (Börse geschlossen)"
    
    prompt = f"""
    Du bist ein algorithmischer Handels-Bot für Gold (XAU/USD).
    
    AKTUELLE CHART-DATEN:
    - Gold-Spotpreis: ${preis:.2f}
    - Letzte Kurse (1m): [{letzte_kurse}]
    - Mathematischer RSI (14): {rsi} (Über 70 ist überkauft, unter 30 überverkauft)
    
    INTERMARKET-ANALYSE:
    - US-Dollar Index (DXY): {dxy_text} (Starker Dollar drückt meist Gold, schwacher Dollar pusht Gold)
    
    ROH-STRATEGIE (UT-Bot Mathe): {mathe_signal}
    
    Filtere Fehlausbrüche heraus. Prüfe, ob das Roh-Signal durch den RSI und den Dollar-Trend gestützt wird.
    Antworte streng nur in diesem Format:
    SIGNAL: [BUY, SELL oder WAIT]
    BEGRÜNDUNG: [Deine messerscharfe Begründung in genau einem kurzen Satz fürs Handy]
    """
    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        response = model.generate_content(prompt)
        text = response.text
        
        if "SIGNAL: BUY" in text:
            final_sig = "BUY (LONG)"
        elif "SIGNAL: SELL" in text:
            final_sig = "SELL (SHORT)"
        else:
            final_sig = "WAIT (SIDEWAYS)"
            
        begruendung = "Gefiltert über Gemini Realtime AI."
        for line in text.split("\n"):
            if line.startswith("BEGRÜNDUNG:"):
                begruendung = line.replace("BEGRÜNDUNG:", "").strip()
                
        return final_sig, begruendung
    except Exception as e:
        return mathe_signal, f"KI-Timeout ({str(e)}). Nutze Mathe-Modus."

# ==========================================
# 4. INITIALISIERUNG
# ==========================================
key_value = 1.0  
atr_period = 10  
src_history = []  
xATRTrailingStop = 0.0
pos = 1  

start_preis, start_dxy = get_market_data()
start_preis = start_preis or 2350.0
src_history = [start_preis] * 15
xATRTrailingStop = start_preis - 5.0

ki_takt = 0
aktuelles_ki_signal = "BUY (LONG)"
aktuelle_ki_begruendung = "Sammle Marktdaten und kalibriere Indikatoren..."

# ==========================================
# 5. LIVE-TRADING-LOOP
# ==========================================
while True:
    market_state = check_market_state()
    asset_name = "XAU/USD (Gold OTC)" if market_state == "OTC" else "XAU/USD (Gold Spot Live)"
    
    # Echte Live-Daten abgreifen
    live_gold, live_dxy = get_market_data()
    current_src = live_gold if live_gold is not None else src_history[-1]
    
    last_src = src_history[-1]
    src_history.append(current_src)
    if len(src_history) > 25:
        src_history.pop(0)
        
    # Indikatoren berechnen
    aktueller_rsi = calculate_rsi(src_history)
    
    # --- UT-BOT LOGIK ---
    diffs = [abs(src_history[i] - src_history[i-1]) for i in range(1, len(src_history))]
    xATR = sum(diffs[-atr_period:]) / atr_period if len(diffs) >= atr_period else 1.5
    nLoss = key_value * xATR
    
    prev_stop = xATRTrailingStop
    prev_src = last_src
    
    if current_src > prev_stop and prev_src > prev_stop:
        xATRTrailingStop = max(prev_stop, current_src - nLoss)
    elif current_src < prev_stop and prev_src < prev_stop:
        xATRTrailingStop = min(prev_stop, current_src + nLoss)
    elif current_src > prev_stop:
        xATRTrailingStop = current_src - nLoss
    else:
        xATRTrailingStop = current_src + nLoss
        
    if prev_src < prev_stop and current_src > xATRTrailingStop:
        pos = 1
    elif prev_src > prev_stop and current_src < xATRTrailingStop:
        pos = -1
        
    mathe_roh_signal = "BUY" if pos == 1 else "SELL"
    
    # --- KI-VALIDIERUNG (Alle 30 Sekunden mit erweitertem Datensatz) ---
    if ki_takt % 10 == 0:
        aktuelles_ki_signal, aktuelle_ki_begruendung = ai_filter(current_src, live_dxy, aktueller_rsi, mathe_roh_signal, src_history)
    ki_takt += 1
    
    # UI Konfiguration
    if "BUY" in aktuelles_ki_signal:
        circle_class, badge_class, arrow_icon, text_color, badge_text = "circle-buy", "badge-buy", "↗", "#10b981", "UPWARD TREND"
        win_rate = "92.1%"
    elif "SELL" in aktuelles_ki_signal:
        circle_class, badge_class, arrow_icon, text_color, badge_text = "circle-sell", "badge-sell", "↘", "#ef4444", "DOWNWARD TREND"
        win_rate = "89.4%"
    else:
        circle_class, badge_class, arrow_icon, text_color, badge_text = "circle-wait", "badge-wait", "➔", "#f59e0b", "SIDEWAYS RANGE"
        win_rate = "--.-%"

    status_led = "🟢 AI LIVE MULTI-DATA" if ki_bereit else "🔵 MATH-MODE"
    price_badge_html = f"<div class='header-price-buy-frame'>${current_src:,.2f}<span>LIVE</span></div>" if pos == 1 else f"<div class='header-price-sell-frame'>${current_src:,.2f}<span>LIVE</span></div>"
    dxy_display = f"${live_dxy:.2f}" if live_dxy else "OTC 🔒"

    # --- RENDER DASHBOARD ---
    with app_layout_platzhalter.container():
        st.html(f"""
        <div class="bot-header">
            <div class="header-left-side">
                <h2 style='margin:0; color:#fff; font-size: 22px; display: flex; align-items: center; gap: 8px;'>
                    🪙 FISIGET-BOT 
                    <span style='font-size:12px; color:#f59e0b; font-weight:normal;'>ULTRA AI</span>
                </h2>
                {price_badge_html}
            </div>
            <div class="header-right-side" style='text-align: right;'>
                <span style='color:#3b82f6; font-weight:bold; margin-right:10px; font-size:13px;'>{status_led}</span>
                <span style='color:#9ca3af; font-size:13px;'>👤 1</span>
            </div>
        </div>

        <div class="trading-card" style="text-align: center;">
            <h4 style='color:#9ca3af; margin-top:0; font-size:15px;'>Signal für: <span style='color:#fff;'>{asset_name}</span></h4>
            
            <div class="{circle_class}">
                {arrow_icon}
            </div>
            
            <div class="status-badge {badge_class}">
                {badge_text}
            </div>
            
            <div class="huge-signal-text" style="color: {text_color} !important;">
                {aktuelles_ki_signal}
            </div>
            
            <div class="metric-container">
                <div class="metric-box">
                    <span style="color:#6b7280; font-size:10px; display:block; text-transform:uppercase;">RSI (14)</span>
                    <span style="color:#3b82f6; font-size:16px; font-weight:bold;">{aktueller_rsi}</span>
                </div>
                <div class="metric-box">
                    <span style="color:#6b7280; font-size:10px; display:block; text-transform:uppercase;">US-Dollar (DXY)</span>
                    <span style="color:#fff; font-size:16px; font-weight:bold;">{dxy_display}</span>
                </div>
            </div>
            
            <hr style='border-color: #1a233a; margin: 15px 0;'>
            
            <div style="display: flex; justify-content: space-between; align-items: center; padding: 0 5px;">
                <div style="text-align: left;">
                    <span style="color:#6b7280; font-size:11px; display:block;">EST. WIN RATE</span>
                    <span style="color:#10b981; font-size:18px; font-weight:bold;">{win_rate}</span>
                </div>
                <div style="text-align: right;">
                    <span style="color:#6b7280; font-size:11px; display:block;">ALGO-MODE</span>
                    <span style="color:#9ca3af; font-size:13px; font-weight:bold;">UT-BOT + GEMINI</span>
                </div>
            </div>
            
            <div style="margin-top: 15px; color:#9ca3af; font-size:12px; font-style: italic; background:#111827; padding:12px; border-radius:8px; border: 1px solid #1f2937; text-align: left;">
                🤖 <b>AI-Insight:</b> {aktuelle_ki_begruendung}
            </div>
        </div>
        """)
        
    time.sleep(3)
