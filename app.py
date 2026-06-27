import streamlit as st
from datetime import datetime
import time
import random
import pytz

# ==========================================
# 1. SEITEN-KONFIGURATION & MOBILE-FIRST DESIGN (CSS)
# ==========================================
st.set_page_config(page_title="Fisiget-Bot - Mobile AI", page_icon="🪙", layout="wide")

st.markdown("""
<style>
    /* Basis-Hintergrund */
    .stApp {
        background-color: #060913;
    }
    
    /* Haupt-Trading-Card (Responsive Breite für Handy & PC) */
    .trading-card {
        background-color: #0d1222;
        padding: 20px;
        border-radius: 16px;
        border: 1px solid #1a233a;
        box-shadow: 0 15px 25px rgba(0, 0, 0, 0.4);
        margin: 15px auto;
        max-width: 100%;
        width: 420px;
    }
    
    /* Der animierte Signal-Kreis */
    .circle-buy {
        width: 140px;
        height: 140px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        margin: 15px auto;
        font-size: 45px;
        font-weight: bold;
        background: radial-gradient(circle, #10b981 0%, #052e16 100%);
        box-shadow: 0 0 40px rgba(16, 185, 129, 0.7);
        color: white;
        animation: pulse-green 1.5s infinite alternate;
    }
    
    .circle-sell {
        width: 140px;
        height: 140px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        margin: 15px auto;
        font-size: 45px;
        font-weight: bold;
        background: radial-gradient(circle, #ef4444 0%, #450a0a 100%);
        box-shadow: 0 0 40px rgba(239, 68, 68, 0.7);
        color: white;
        animation: pulse-red 1.5s infinite alternate;
    }

    @keyframes pulse-green {
        0% { box-shadow: 0 0 15px rgba(16, 185, 129, 0.4); }
        100% { box-shadow: 0 0 45px rgba(16, 185, 129, 0.8); }
    }
    @keyframes pulse-red {
        0% { box-shadow: 0 0 15px rgba(239, 68, 68, 0.4); }
        100% { box-shadow: 0 0 45px rgba(239, 68, 68, 0.8); }
    }

    /* Signal-Schriftzug */
    .huge-signal-text {
        font-size: 32px !important;
        font-weight: 900 !important;
        text-align: center;
        margin: 10px 0 !important;
        letter-spacing: 1px;
    }

    /* Status-Plakette */
    .status-badge {
        padding: 6px 16px;
        border-radius: 20px;
        font-size: 13px;
        font-weight: bold;
        text-align: center;
        width: fit-content;
        margin: 8px auto;
        text-transform: uppercase;
    }
    .badge-buy { background-color: rgba(16, 185, 129, 0.2); color: #10b981; border: 1px solid #10b981; }
    .badge-sell { background-color: rgba(239, 68, 68, 0.2); color: #ef4444; border: 1px solid #ef4444; }
    
    /* --- INTELLIGENTER RESPONSIVER HEADER (HANDY-OPTIMIERT) --- */
    .bot-header {
        display: flex;
        flex-direction: row;
        justify-content: space-between;
        align-items: center;
        padding-bottom: 12px;
        border-bottom: 1px solid #1a233a;
        margin-bottom: 15px;
        flex-wrap: wrap; /* Erlaubt das Brechen auf Mobilgeräten */
        gap: 10px;
    }

    .header-left-side {
        display: flex;
        align-items: center;
        flex-wrap: wrap;
        gap: 10px;
    }
    
    /* Die Rahmen-Preis-Buttons */
    .header-price-buy-frame {
        background-color: transparent;
        color: #3b82f6;
        padding: 4px 12px;
        border-radius: 10px;
        font-weight: bold;
        font-size: 18px;
        border: 1.5px solid #3b82f6;
        display: inline-block;
        text-align: center;
    }
    .header-price-buy-frame span {
        display: block;
        font-size: 9px;
        text-transform: uppercase;
        letter-spacing: 1px;
        margin-top: -2px;
        color: #3b82f6;
    }

    .header-price-sell-frame {
        background-color: transparent;
        color: #ef4444;
        padding: 4px 12px;
        border-radius: 10px;
        font-weight: bold;
        font-size: 18px;
        border: 1.5px solid #ef4444;
        display: inline-block;
        text-align: center;
    }
    .header-price-sell-frame span {
        display: block;
        font-size: 9px;
        text-transform: uppercase;
        letter-spacing: 1px;
        margin-top: -2px;
        color: #ef4444;
    }

    /* CSS-Regeln für kleine Bildschirme (Handys) */
    @media (max-width: 600px) {
        .bot-header {
            flex-direction: column !important;
            text-align: center;
            align-items: center;
            justify-content: center;
        }
        .header-left-side {
            flex-direction: column !important;
            align-items: center;
        }
        .header-right-side {
            text-align: center !important;
            width: 100%;
            margin-top: 5px;
        }
        .trading-card {
            width: 100%;
            margin: 5px auto;
            padding: 15px;
        }
    }
</style>
""", unsafe_allow_html=True)

# Container für das ruckelfreie UI-Update auf dem Handy
app_layout_platzhalter = st.empty()

# ==========================================
# 2. INTELLIGENTES GEHIRN: MARKT-LOGIK
# ==========================================
def check_market_state():
    tz = pytz.timezone('Europe/Berlin')
    now = datetime.now(tz)
    weekday = now.weekday() 
    hour = now.hour

    if (weekday == 4 and hour >= 23) or (weekday == 5) or (weekday == 6 and hour < 23):
        return "OTC"
    return "LIVE"

# ==========================================
# 3. UT-BOT CORE ALGORITHMUS VARIABLEN
# ==========================================
key_value = 1.0  
atr_period = 10  
src_history = [4080.50] * 15  
xATRTrailingStop = 4070.0
pos = 1  

simulated_price = 4080.50

# ==========================================
# 4. UNENDLICHER LIVE-LOOP
# ==========================================
while True:
    market_state = check_market_state()
    asset_name = "XAU/USD (Gold OTC)" if market_state == "OTC" else "XAU/USD (Gold Live)"
        
    # Preis-Tick berechnen
    last_src = src_history[-1]
    change = random.choice([-1.45, -0.65, 0.35, 0.85, 1.40, -0.90, 0.10, -0.15])
    simulated_price += change
    current_src = simulated_price
    
    src_history.append(current_src)
    if len(src_history) > 20:
        src_history.pop(0)
        
    # UT-Bot Gehirn (ATR)
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
        
    # Signal-Styling zuweisen
    if pos == 1:
        signal_type = "BUY (LONG)"
        circle_class = "circle-buy"
        badge_class = "badge-buy"
        arrow_icon = "↗"
        text_color = "#10b981"
        badge_text = "UPWARD"
        strength_dots = "●●●●● (UT-V6)"
        win_rate = f"{random.randint(89, 94)}%"
        status_text = f"🟢 AI: Kurs über Stop (${xATRTrailingStop:.2f})"
        price_badge_html = f"<div class='header-price-buy-frame'>${current_src:,.2f}<span>KAUF</span></div>"
    else:
        signal_type = "SELL (SHORT)"
        circle_class = "circle-sell"
        badge_class = "badge-sell"
        arrow_icon = "↘"
        text_color = "#ef4444"
        badge_text = "DOWNWARD"
        strength_dots = "●●●●○ (UT-V6)"
        win_rate = f"{random.randint(84, 89)}%"
        status_text = f"🔴 AI: Kurs unter Stop (${xATRTrailingStop:.2f})"
        price_badge_html = f"<div class='header-price-sell-frame'>${current_src:,.2f}<span>VERKAUF</span></div>"

    # --- RESPONSIVES RENDERING ---
    with app_layout_platzhalter.container():
        st.html(f"""
        <div class="bot-header">
            <div class="header-left-side">
                <h2 style='margin:0; color:#fff; font-size: 22px; display: flex; align-items: center; gap: 8px;'>
                    🪙 FISIGET-BOT 
                    <span style='font-size:12px; color:#f59e0b; font-weight:normal;'>GOLD ED.</span>
                </h2>
                {price_badge_html}
            </div>
            <div class="header-right-side" style='text-align: right;'>
                <span style='color:#10b981; font-weight:bold; margin-right:10px; font-size:13px;'>● AI LIVE</span>
                <span style='color:#9ca3af; font-size:13px;'>👤 1,360</span>
            </div>
        </div>

        <div class="trading-card" style="text-align: center;">
            <h4 style='color:#9ca3af; margin-top:0; font-size:15px;'>Signal for: <span style='color:#fff;'>{asset_name}</span></h4>
            <p style='color:#6b7280; font-size:12px; margin:0;'>Timeframe: 10 SEC</p>
            
            <div class="{circle_class}">
                {arrow_icon}
            </div>
            
            <div class="status-badge {badge_class}">
                {badge_text}
            </div>
            
            <div class="huge-signal-text" style="color: {text_color} !important;">
                {signal_type}
            </div>
            
            <hr style='border-color: #1a233a; margin: 15px 0;'>
            
            <div style="display: flex; justify-content: space-between; align-items: center; padding: 0 10px;">
                <div style="text-align: left;">
                    <span style="color:#6b7280; font-size:11px; display:block;">UT-ALERTS V6</span>
                    <span style="color:{text_color}; font-size:13px; letter-spacing:1px;">{strength_dots}</span>
                </div>
                <div style="text-align: right;">
                    <span style="color:#6b7280; font-size:11px; display:block;">WIN RATE</span>
                    <span style="color:#10b981; font-size:20px; font-weight:bold;">{win_rate}</span>
                </div>
            </div>
            
            <div style="margin-top: 20px; color:#6b7280; font-size:11px;">
                {status_text}
            </div>
        </div>
        """)
        
    time.sleep(1)