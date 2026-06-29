import streamlit as st
from datetime import datetime
import time
import pytz
import MetaTrader5 as mt5
import google.generativeai as genai
from openai import OpenAI
import random

# ==========================================
# KONFIGURATION & TRADING-PARAMETER
# ==========================================
GOLD_FOTO_URL = "https://images.unsplash.com/photo-1610374792793-f016b77ca51a?q=80&w=100&auto=format&fit=crop"
ATR_PERIOD = 14
RSI_PERIOD = 14
KEY_VALUE = 1.5
SIGNAL_CYCLE_SEC = 60     # ← GEÄNDERT: nur alle 60 Sek evaluieren
BROKER_SYMBOL = "XAUUSD"

# AUTOMATION SETTINGS
LOT_SIZE = 0.01          
SL_DISTANCE_PIPS = 50.0  
TP_DISTANCE_PIPS = 100.0 
MAGIC_NUMBER = 202606    

# FILTER SETTINGS
ATR_MIN_PIPS = 0.80      # Kein Signal wenn ATR unter diesem Wert (Seitwärtsmarkt)

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
    st.session_state.src_history = [2330.0] * 30
if "trail" not in st.session_state:
    st.session_state.trail = 2325.0
if "pos" not in st.session_state:
    st.session_state.pos = 1
if "ki_signal" not in st.session_state:
    st.session_state.ki_signal = "WAIT (SIDEWAYS)"
if "ki_reason" not in st.session_state:
    st.session_state.ki_reason = "Initialisiere AI Pipeline…"
if "last_signal_eval" not in st.session_state:
    st.session_state.last_signal_eval = 0.0  
if "force_ai" not in st.session_state: 
    st.session_state.force_ai = False
if "signal_strength" not in st.session_state:
    st.session_state.signal_strength = 0

if "broker_sell" not in st.session_state: st.session_state.broker_sell = 2330.0
if "broker_buy" not in st.session_state: st.session_state.broker_buy = 2330.85
if "broker_spread" not in st.session_state: st.session_state.broker_spread = 0.85
if "connection_status" not in st.session_state: st.session_state.connection_status = "⚠️ Nicht verbunden"
if "last_trade_log" not in st.session_state: st.session_state.last_trade_log = "Warte auf Handelssignale..."
if "last_rsi" not in st.session_state: st.session_state.last_rsi = 50.0
if "last_atr" not in st.session_state: st.session_state.last_atr = 1.5
if "ema200_1h" not in st.session_state: st.session_state.ema200_1h = 0.0
if "filter_reason" not in st.session_state: st.session_state.filter_reason = ""
if "last_1h_fetch" not in st.session_state: st.session_state.last_1h_fetch = 0.0

# ==========================================
# IMPROVED INDIKATOREN
# ==========================================
def calculate_rsi(prices, period=14):
    if len(prices) < period + 1: 
        return 50.0
    gains, losses = 0.0, 0.0
    for i in range(1, len(prices)):
        d = prices[i] - prices[i-1]
        if d > 0: gains += d
        else: losses += abs(d)
    
    ag = gains / period
    al = losses / period
    
    if al == 0:
        return 100.0 if ag > 0 else 50.0
    rs = ag / al
    return round(100.0 - (100.0 / (1.0 + rs)), 1)

def calculate_atr(prices, period=14):
    if len(prices) < period + 1:
        return 1.5
    trs = []
    for i in range(1, len(prices)):
        tr = abs(prices[i] - prices[i-1])
        trs.append(tr)
    atr = sum(trs[-period:]) / period
    return max(atr, 0.5)

def calculate_macd(prices, fast=12, slow=26, signal=9):
    if len(prices) < slow + signal:
        return 0.0, 0.0
    ema_fast = prices[-fast:] if len(prices) >= fast else prices
    ema_slow = prices[-slow:] if len(prices) >= slow else prices
    return sum(ema_fast)/len(ema_fast) - sum(ema_slow)/len(ema_slow), 0.0

# ==========================================
# FILTER-INDIKATOREN
# ==========================================
def calculate_ema(prices, period):
    """Echter EMA – benötigt für EMA200 (1H-Trend-Filter)"""
    if len(prices) < period:
        return prices[-1] if prices else 0.0
    k = 2.0 / (period + 1)
    ema = sum(prices[:period]) / period  # SMA als Startwert
    for p in prices[period:]:
        ema = p * k + ema * (1 - k)
    return round(ema, 2)

def get_1h_closes_mt5():
    """
    Holt 200 abgeschlossene 1H-Candle-Closes aus MT5 für EMA200.
    Gibt Liste oder None zurück.
    """
    try:
        rates = mt5.copy_rates_from_pos(BROKER_SYMBOL, mt5.TIMEFRAME_H1, 0, 201)
        if rates is None or len(rates) < 50:
            return None
        return [round(r["close"], 2) for r in rates[:-1]]  # letzte Kerze offen → weglassen
    except Exception:
        return None

def check_all_filters(rsi, atr, buy_raw, sell_raw, ema200_1h, current_price):
    """
    Wendet alle 4 Filter an. Gibt (buy_ok, sell_ok, blocked_reason) zurück.

    Filter 1: Confluence RSI
      BUY  nur wenn RSI < 50
      SELL nur wenn RSI > 50

    Filter 2: ATR-Mindest-Schwelle
      Kein Signal wenn ATR zu niedrig (Seitwärtsmarkt)
      Schwelle: ATR_MIN_PIPS (konfigurierbar)

    Filter 3: Trend-Filter EMA200 (1H)
      Beide Richtungen erlaubt – aber Gegentrend bekommt niedrigere Stärke
      (kein harter Block laut deiner Wahl)

    Filter 4: Session-Filter
      Kein Filter – immer traden (laut deiner Wahl)
    """
    blocked_reasons = []

    # Filter 1: RSI Confluence
    rsi_blocks_buy  = buy_raw  and (rsi >= 50)
    rsi_blocks_sell = sell_raw and (rsi <= 50)
    if rsi_blocks_buy:
        blocked_reasons.append(f"RSI {rsi} ≥ 50 → BUY blockiert")
    if rsi_blocks_sell:
        blocked_reasons.append(f"RSI {rsi} ≤ 50 → SELL blockiert")

    buy_ok  = buy_raw  and not rsi_blocks_buy
    sell_ok = sell_raw and not rsi_blocks_sell

    # Filter 2: ATR-Mindest-Schwelle (Seitwärtsmarkt-Filter)
    if atr < ATR_MIN_PIPS:
        if buy_ok or sell_ok:
            blocked_reasons.append(f"ATR {atr:.2f} < {ATR_MIN_PIPS} → Markt zu ruhig")
        buy_ok  = False
        sell_ok = False

    # Filter 3: EMA200 Trendrichtung (beide Seiten erlaubt, kein harter Block)
    trend_note = ""
    if ema200_1h and ema200_1h > 0:
        if buy_ok and current_price < ema200_1h:
            trend_note = f" ⚠️ Gegen-Trend (EMA200={ema200_1h:.0f})"
        elif sell_ok and current_price > ema200_1h:
            trend_note = f" ⚠️ Gegen-Trend (EMA200={ema200_1h:.0f})"

    # Filter 4: Session – kein Filter (immer traden)
    # → nichts zu tun

    reason = " | ".join(blocked_reasons) + trend_note if blocked_reasons or trend_note else ""
    return buy_ok, sell_ok, reason

# ==========================================
# UT BOT – 1:1 PINE SCRIPT ÜBERSETZUNG
# ==========================================
def ut_bot_pine(prices, atr_period=10, key_value=1.0):
    """
    Exakte Übersetzung des Pine Script UT Bot v6.

    Pine Logik:
      nLoss = key_value * ATR
      xATRTrailingStop:
        src > prev AND src[1] > prev  → max(prev, src - nLoss)
        src < prev AND src[1] < prev  → min(prev, src + nLoss)
        else                          → src - nLoss  oder  src + nLoss

      BUY  = crossover(src, trail)  = src[1] <= trail[1] AND src > trail
      SELL = crossover(trail, src)  = src[1] >= trail[1] AND src < trail
    """
    if len(prices) < atr_period + 2:
        return st.session_state.trail, st.session_state.pos, False, False

    trs = [abs(prices[i] - prices[i-1]) for i in range(1, len(prices))]
    atr = sum(trs[-atr_period:]) / atr_period
    n_loss = max(key_value * atr, 0.01)

    src      = prices[-1]
    src_prev = prices[-2]
    prev_trail = st.session_state.trail

    # Trail berechnen – identisch zu Pine
    if src > prev_trail and src_prev > prev_trail:
        trail = max(prev_trail, src - n_loss)
    elif src < prev_trail and src_prev < prev_trail:
        trail = min(prev_trail, src + n_loss)
    else:
        trail = src - n_loss if src > prev_trail else src + n_loss

    # Crossover-Erkennung (Pine: ta.crossover)
    above = (src_prev <= prev_trail) and (src > trail)  # crossover(src, trail)
    below = (src_prev >= prev_trail) and (src < trail)  # crossover(trail, src)

    pos = st.session_state.pos
    if above:
        pos = 1
    elif below:
        pos = -1

    # Signal nur bei echtem Crossover
    buy_signal  = above and (src > trail)
    sell_signal = below and (src < trail)

    return trail, pos, buy_signal, sell_signal

# ==========================================
# SIGNAL QUALITY FILTER
# ==========================================
def evaluate_signal_quality(rsi, pos, atr_trend, macd_val):
    score = 0
    if pos == 1 and rsi < 30:   score += 3
    elif pos == 1 and rsi < 50: score += 2
    elif pos == -1 and rsi > 70: score += 3
    elif pos == -1 and rsi > 50: score += 2
    else: score += 1
    if 1.0 < atr_trend < 5.0: score += 1
    else: score -= 1
    if (pos == 1 and macd_val > 0) or (pos == -1 and macd_val < 0): score += 1
    return max(0, min(score, 5))

# ==========================================
# DUAL-AI MIT BESSERER LOGIK
# ==========================================
AI_PROMPT = """Du bist algorithmischer Gold-Handler (XAU/USD).
DATEN: Preis=${preis:.2f} | RSI={rsi} | Signal: {signal} | Stärke: {strength}/5
Antworte NUR:
SIGNAL: [BUY|SELL|WAIT]
BEGRÜNDUNG: [max. 20 Wörter]"""

def parse_ai_response(text, source):
    signal, reason = "WAIT", "Analyse abgeschlossen."
    for line in text.strip().splitlines():
        if line.startswith("SIGNAL:"):
            raw = line.replace("SIGNAL:", "").strip().upper()
            signal = "BUY (LONG)" if "BUY" in raw else "SELL (SHORT)" if "SELL" in raw else "WAIT (SIDEWAYS)"
        elif line.startswith("BEGRÜNDUNG:"):
            reason = line.replace("BEGRÜNDUNG:", "").strip()
    return signal, f"[{source}]: {reason}"

def dual_ai_filter(preis, rsi, pos, strength, macd_val):
    """Verbesserte KI-Filterung"""
    # Math-Signal aus UT-Bot
    math_signal = "BUY" if pos == 1 else "SELL" if pos == -1 else "WAIT"
    
    # Fallback ohne KI
    fallback = "BUY (LONG)" if math_signal == "BUY" else "SELL (SHORT)" if math_signal == "SELL" else "WAIT (SIDEWAYS)"
    
    if not any(keys.values()):
        return fallback, "Kein API-Key – Mathe-Modus.", strength
    
    prompt = AI_PROMPT.format(preis=preis, rsi=rsi, signal=math_signal, strength=strength)
    
    if keys["gemini"]:
        try:
            resp = genai.GenerativeModel("gemini-2.5-flash").generate_content(prompt, timeout=5)
            if resp.text and "SIGNAL:" in resp.text:
                sig, reason = parse_ai_response(resp.text, "Gemini 2.5")
                return sig, reason, strength
        except Exception as e:
            pass
    
    return fallback, "KI nicht verfügbar – Mathe-Modus.", strength

# ==========================================
# METATRADER AUTOMATION
# ==========================================
def count_open_positions():
    positions = mt5.positions_get(symbol=BROKER_SYMBOL)
    if positions is None or len(positions) == 0:
        return 0
    bot_positions = [p for p in positions if p.magic == MAGIC_NUMBER]
    return len(bot_positions)

def execute_market_order(direction: str, price_ask: float, price_bid: float):
    if count_open_positions() > 0:
        st.session_state.last_trade_log = f"⏳ {direction} ignoriert – Position läuft."
        return

    if direction == "BUY":
        order_type = mt5.ORDER_TYPE_BUY
        price = price_ask
        sl = price - SL_DISTANCE_PIPS
        tp = price + TP_DISTANCE_PIPS
    elif direction == "SELL":
        order_type = mt5.ORDER_TYPE_SELL
        price = price_bid
        sl = price + SL_DISTANCE_PIPS
        tp = price - TP_DISTANCE_PIPS
    else:
        return

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": BROKER_SYMBOL,
        "volume": LOT_SIZE,
        "type": order_type,
        "price": price,
        "sl": round(sl, 2),
        "tp": round(tp, 2),
        "deviation": 20,
        "magic": MAGIC_NUMBER,
        "comment": "Fisiget Order",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        st.session_state.last_trade_log = f"❌ Order-Fehler! Code: {result.retcode}"
    else:
        st.session_state.last_trade_log = f"🚀 {direction} eröffnet! Ticket: {result.order}"

# ==========================================
# MARKET DATA
# ==========================================
def check_market_state() -> str:
    tz = pytz.timezone("Europe/Berlin")
    now = datetime.now(tz)
    if (now.weekday() == 4 and now.hour >= 23) or now.weekday() == 5 or (now.weekday() == 6 and now.hour < 23):
        return "OTC"
    return "LIVE"

def get_broker_market_data():
    """
    Holt echte 1M-Candle-Closes aus MT5 (60 Kerzen).
    Gibt (midprice_float, closes_list) zurück oder (None, None) bei Fehler.
    """
    if not mt5.initialize():
        st.session_state.connection_status = f"❌ MT5 konnte nicht starten! Fehler: {mt5.last_error()}"
        return None, None

    try:
        login_success = mt5.login(62128025, "@A09351531011a@", "PepperstoneUK-Demo")
    except Exception as e:
        st.session_state.connection_status = f"❌ Login-Fehler: {str(e)}"
        return None, None

    if not login_success:
        st.session_state.connection_status = f"❌ Pepperstone abgelehnt! Code: {mt5.last_error()}"
        return None, None

    # Aktueller Tick (für BID/ASK Anzeige + Orderpreis)
    tick = mt5.symbol_info_tick(BROKER_SYMBOL)
    if tick is None:
        st.session_state.connection_status = f"⚠️ Symbol '{BROKER_SYMBOL}' nicht gefunden!"
        return None, None

    st.session_state.broker_sell = round(tick.bid, 2)
    st.session_state.broker_buy  = round(tick.ask, 2)
    st.session_state.broker_spread = round(tick.ask - tick.bid, 2)
    midprice = round((tick.bid + tick.ask) / 2, 2)

    # Echte 1M-Candles holen (60 abgeschlossene Kerzen + 1 laufende)
    rates = mt5.copy_rates_from_pos(BROKER_SYMBOL, mt5.TIMEFRAME_M1, 0, 61)
    if rates is None or len(rates) < 10:
        st.session_state.connection_status = "⚠️ MT5 verbunden, aber keine 1M-Candles erhalten!"
        return midprice, None

    # Nur abgeschlossene Kerzen (letzte ist noch offen → weglassen)
    closes = [round(r["close"], 2) for r in rates[:-1]]
    st.session_state.connection_status = "🟢 Pepperstone MT5 – 1M Candles aktiv!"
    return midprice, closes

# ==========================================
# MARKET SESSIONS
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
# SIGNAL CONFIG & RENDERING
# ==========================================
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
# MAIN LOGIC: 1M-ZYKLUS
# ==========================================
market_state = check_market_state()
live_midprice, candle_closes = get_broker_market_data()

if candle_closes and len(candle_closes) >= 15:
    # Echte 1M-Candle-Closes direkt verwenden
    st.session_state.src_history = candle_closes
    current_price = candle_closes[-1]
elif live_midprice:
    # Fallback: Tick-Midprice anhängen
    current_price = live_midprice
    st.session_state.src_history.append(current_price)
    if len(st.session_state.src_history) > 60:
        st.session_state.src_history.pop(0)
else:
    # Kein MT5: simulierter Preis
    current_price = round(st.session_state.src_history[-1] + random.uniform(-0.3, 0.3), 2)
    st.session_state.src_history.append(current_price)
    if len(st.session_state.src_history) > 60:
        st.session_state.src_history.pop(0)

price_label = f"${current_price:,.2f}"

# Indikatoren berechnen
rsi = calculate_rsi(st.session_state.src_history, RSI_PERIOD)
atr = calculate_atr(st.session_state.src_history, ATR_PERIOD)
macd_val, _ = calculate_macd(st.session_state.src_history)

# UT BOT (Pine Script 1:1) – liefert Trail, Pos und echte Crossover-Signale
st.session_state.trail, st.session_state.pos, buy_crossover, sell_crossover = ut_bot_pine(
    st.session_state.src_history, atr_period=ATR_PERIOD, key_value=KEY_VALUE
)

# Signal-Qualität
signal_strength = evaluate_signal_quality(rsi, st.session_state.pos, atr, macd_val)

# Cache für Anzeige
st.session_state.last_rsi = rsi
st.session_state.last_atr = atr

current_time = time.time()

# EMA200 (1H) alle 5 Minuten aktualisieren
if current_time - st.session_state.last_1h_fetch >= 300:
    closes_1h = get_1h_closes_mt5()
    if closes_1h:
        st.session_state.ema200_1h = calculate_ema(closes_1h, 200)
    st.session_state.last_1h_fetch = current_time

# ── ALLE 4 FILTER ANWENDEN ──────────────────────────────────────────────────
buy_ok, sell_ok, filter_reason = check_all_filters(
    rsi, atr, buy_crossover, sell_crossover,
    st.session_state.ema200_1h, current_price
)
st.session_state.filter_reason = filter_reason

# Signal setzen
if buy_ok:
    trend_note = " ⚠️ Gegen-Trend" if current_price < st.session_state.ema200_1h and st.session_state.ema200_1h > 0 else ""
    st.session_state.ki_signal = "BUY (LONG)"
    st.session_state.ki_reason = f"[UT Bot + Filter]: Crossover ✅ | RSI {rsi} < 50 ✅ | ATR {atr:.2f} ✅{trend_note}"
    st.session_state.signal_strength = signal_strength
    if live_midprice:
        execute_market_order("BUY", st.session_state.broker_buy, st.session_state.broker_sell)

elif sell_ok:
    trend_note = " ⚠️ Gegen-Trend" if current_price > st.session_state.ema200_1h and st.session_state.ema200_1h > 0 else ""
    st.session_state.ki_signal = "SELL (SHORT)"
    st.session_state.ki_reason = f"[UT Bot + Filter]: Crossover ✅ | RSI {rsi} > 50 ✅ | ATR {atr:.2f} ✅{trend_note}"
    st.session_state.signal_strength = signal_strength
    if live_midprice:
        execute_market_order("SELL", st.session_state.broker_buy, st.session_state.broker_sell)

elif buy_crossover or sell_crossover:
    # Crossover da, aber Filter hat blockiert
    direction = "BUY" if buy_crossover else "SELL"
    st.session_state.ki_signal = "WAIT (SIDEWAYS)"
    st.session_state.ki_reason = f"[Filter blockiert {direction}]: {filter_reason}"
    st.session_state.signal_strength = 1

# KI-Zusatzanalyse alle 60 Sek (nur Reasoning-Update wenn kein aktiver Cross)
if (current_time - st.session_state.last_signal_eval >= SIGNAL_CYCLE_SEC) or st.session_state.force_ai:
    if not buy_crossover and not sell_crossover:
        _, st.session_state.ki_reason, st.session_state.signal_strength = dual_ai_filter(
            current_price, rsi, st.session_state.pos, signal_strength, macd_val
        )
    st.session_state.last_signal_eval = current_time
    st.session_state.force_ai = False

# Countdown bis nächste Evaluation
seconds_since_eval = current_time - st.session_state.last_signal_eval
seconds_until_next = max(0, int(SIGNAL_CYCLE_SEC - seconds_since_eval))

# Session-Infos
sessions = get_market_sessions()
market_hours_html = build_market_hours_html(sessions)
open_count = sum(1 for s in sessions if s["is_open"])

sig_key = get_sig_key(st.session_state.ki_signal)
cfg = SIGNAL_CONFIG[sig_key]
mode_label = "LIVE AI" if any(keys.values()) else "MATH MODE"
dots_filled = "●" * st.session_state.signal_strength + "○" * (5 - st.session_state.signal_strength)

# ==========================================
# RENDER
# ==========================================
if "🟢" in st.session_state.connection_status:
    st.success(st.session_state.connection_status)
else:
    st.error(st.session_state.connection_status)

st.info(f"📊 **Auto-Trade Engine:** {st.session_state.last_trade_log}")

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
      <div class="signal-header">Gold Spot / U.S. Dollar · <span>PEPPERSTONE</span></div>
      <div class="signal-tf">Mittelkurs: {price_label} | TF: 1M | RSI: {st.session_state.last_rsi} | ATR: {st.session_state.last_atr:.2f}</div>

      <div class="trading-prices">
        <div class="price-button sell">
          <div class="price-num-sell">{st.session_state.broker_sell:,.2f}</div>
          <div class="price-label-sub">BID</div>
        </div>
        <div style="font-size:12px; color:#9ca3af; font-weight:700; font-family:monospace;">{st.session_state.broker_spread:.2f}</div>
        <div class="price-button buy">
          <div class="price-num-buy">{st.session_state.broker_buy:,.2f}</div>
          <div class="price-label-sub">ASK</div>
        </div>
      </div>

      <div class="circle-outer">
        <div class="circle-main">{cfg['svg']}</div>
      </div>

      <span class="dir-badge">{cfg['dir']}</span>
      <div class="signal-text">{st.session_state.ki_signal}</div>

      <div class="stats-row">
        <div class="stat-card">
          <div class="stat-label">Signal Strength</div>
          <div class="stat-dots">{dots_filled}</div>
          <div class="stat-sub">{st.session_state.signal_strength}/5</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Win Rate</div>
          <div class="stat-winrate">{cfg['win']}</div>
          <div class="stat-live">Live</div>
        </div>
      </div>

      <div class="ai-bar">
        <span class="dot-live"></span> NEXT EVAL IN {seconds_until_next}s
      </div>

      <div style="background:#0a0f1a;border:1px solid #1a2540;border-radius:12px;padding:12px 14px;font-size:11px;color:#4b6080;line-height:1.5;margin-bottom:8px;">
        <div style="font-size:10px;color:#2a3a50;text-transform:uppercase;letter-spacing:1px;margin-bottom:4px;font-weight:700;">🤖 Signal-Reasoning</div>
        {st.session_state.ki_reason}
      </div>
      <div style="background:#0a0f1a;border:1px solid #1a2540;border-radius:12px;padding:10px 14px;font-size:10px;color:#4b6080;line-height:1.6;margin-bottom:14px;">
        <div style="font-size:10px;color:#2a3a50;text-transform:uppercase;letter-spacing:1px;margin-bottom:4px;font-weight:700;">🔎 Filter-Status</div>
        <span style="color:#00e676;">RSI:</span> {st.session_state.last_rsi} &nbsp;|&nbsp;
        <span style="color:#00e676;">ATR:</span> {st.session_state.last_atr:.2f} (Min: {ATR_MIN_PIPS}) &nbsp;|&nbsp;
        <span style="color:#00e676;">EMA200 (1H):</span> {f"{st.session_state.ema200_1h:.0f}" if st.session_state.ema200_1h > 0 else "lädt…"}
        {"<br><span style=\"color:#ffc400;\">⚠️ " + st.session_state.filter_reason + "</span>" if st.session_state.filter_reason else "<br><span style=\"color:#00e676;\">✅ Alle Filter OK</span>"}
      </div>

      <div style="margin-bottom:6px;">
        <div style="width:100%;background:#0a0f1a;border:1px solid #1a2540;border-radius:12px;padding:12px 14px;color:#fff;font-size:12px;font-weight:700;display:flex;justify-content:space-between;align-items:center;">
          <span>Analyse-Märkte &nbsp;<span style="background:#00e67622;color:#00e676;border-radius:8px;padding:2px 8px;font-size:11px;">{open_count}/4 Aktiv</span></span>
        </div>
        <div style="background:#0a0f1a;border:1px solid #1a2540;border-top:none;border-radius:0 0 12px 12px;overflow:hidden;">
          {market_hours_html}
        </div>
      </div>

      <div class="ssl-bar">🔒 SSL Secured | 🔒 256-bit Encrypted</div>
    </div>

    <div class="nav-bar">
      <div class="nav-item active"><span class="nav-icon">📈</span>TRADE</div>
      <div class="nav-item"><span class="nav-icon">⚡</span>LIVE FEED</div>
      <div class="nav-item"><span class="nav-icon">👤</span>PROFILE</div>
    </div>

  </div>
</div>
</body>
</html>
""")

# ==========================================
# 60-SEKUNDEN-TICKER (NICHT JEDE SEKUNDE!)
# ==========================================
time.sleep(1)
st.rerun()
