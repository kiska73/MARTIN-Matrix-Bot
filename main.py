import os
import time
import pandas as pd
from pybit.unified_trading import HTTP
from datetime import datetime, timezone

# ==========================================================
# CONFIGURAZIONE
# ==========================================================
API_KEY = os.environ.get("BYBIT_API_KEY")
API_SECRET = os.environ.get("BYBIT_API_SECRET")
SYMBOL = "LABUSDT"

session = HTTP(testnet=False, api_key=API_KEY, api_secret=API_SECRET)

current_mode = "AGGRESSIVE"
pause_until_next_candle = False

# Dimensioni dei lotti per ogni livello della griglia
GRID_SIZES = [2, 2, 2, 3, 4, 5, 6, 8, 10, 13, 16, 20, 25]

COOLDOWN = 20
last_candle_ts = 0
last_trade_time = 0

def get_current_price():
    try:
        ticker = session.get_tickers(category="linear", symbol=SYMBOL)
        return float(ticker['result']['list'][0]['lastPrice'])
    except:
        return None

def get_volatility_data(symbol):
    try:
        data = session.get_kline(category="linear", symbol=symbol, interval="240", limit=42)
        df = pd.DataFrame(data['result']['list'], columns=['ts', 'open', 'high', 'low', 'close', 'vol', 'turnover'])
        df['close'] = df['close'].astype(float)
        df['low'] = df['low'].astype(float)
        df['ts'] = df['ts'].astype(int)
        
        sma = df['close'].rolling(window=40).mean()
        std = df['close'].rolling(window=40).std()
        lower_band = sma - (std * 2)
        bb_width_percent = ((sma.iloc[-1] - lower_band.iloc[-1]) / sma.iloc[-1]) * 100
        
        return {
            'ts': df['ts'].iloc[-1],
            'bb_width': round(bb_width_percent, 2),
            'lower_band': round(lower_band.iloc[-1], 4),
        }
    except Exception as e:
        print(f"Errore Kline: {e}")
        return None

def get_spacing(mode):
    # Ritorna la distanza fissa in % tra un livello e l'altro
    return 1.5 if mode == "AGGRESSIVE" else 2.5

def should_check_candle():
    now_utc = datetime.now(timezone.utc)
    # Controllo ogni 4 ore (orari standard di chiusura candele 4H)
    if now_utc.hour % 4 == 0 and now_utc.minute == 0 and 0 <= now_utc.second <= 30:
        return True
    return False

print("🚀 BOT GRID MASTER - Attivo")

while True:
    try:
        now = time.time()
        price = get_current_price()
        
        # Recupero stato posizioni
        pos_data = session.get_positions(category="linear", symbol=SYMBOL)["result"]["list"]
        pos = pos_data[0] if pos_data else {"size": "0"}
        size = float(pos["size"])
        avg_price = float(pos.get("avgPrice", 0))

        active_orders = session.get_open_orders(category="linear", symbol=SYMBOL)["result"]["list"]
        tp_orders = [o for o in active_orders if o["side"] == "Sell" and o["orderType"] == "Limit"]

        # ==================== LOGICA 4H ====================
        if should_check_candle():
            vol_data = get_volatility_data(SYMBOL)
            if vol_data and vol_data['ts'] != last_candle_ts:
                new_mode = "CONSERVATIVE" if vol_data.get('bb_width', 0) > 40 else "AGGRESSIVE"
                current_mode = new_mode
                
                # Pausa se il prezzo è troppo vicino alla banda inferiore
                if price and vol_data.get('lower_band'):
                    distance = ((price - vol_data['lower_band']) / vol_data['lower_band']) * 100
                    pause_until_next_candle = (distance <= 3.0)
                
                last_candle_ts = vol_data['ts']

        # ==================== GESTIONE TAKE PROFIT ====================
        if size > 0:
            tp_percent = 1.20 if current_mode == "CONSERVATIVE" else 0.90
            target_tp = round(avg_price * (1 + tp_percent/100), 4)
            
            if not tp_orders or abs(float(tp_orders[0]["price"]) - target_tp) > 0.0002:
                session.cancel_all_orders(category="linear", symbol=SYMBOL, orderFilter="Order")
                session.place_order(category="linear", symbol=SYMBOL, side="Sell", orderType="Limit", 
                                  qty=str(size), price=str(target_tp), reduceOnly=True)

        # ==================== NUOVA ENTRATA ====================
        elif size == 0 and (now - last_trade_time > COOLDOWN):
            if not pause_until_next_candle:
                print(f"🧹 Nuova entrata in modalità {current_mode}")
                session.cancel_all_orders(category="linear", symbol=SYMBOL)
                time.sleep(1.0)

                # Entry Market iniziale
                session.place_order(category="linear", symbol=SYMBOL, side="Buy", orderType="Market", qty=str(GRID_SIZES[0]))
                time.sleep(2.0)
                
                # Ottieni prezzo medio reale
                new_pos = session.get_positions(category="linear", symbol=SYMBOL)["result"]["list"][0]
                avg = float(new_pos["avgPrice"])
                
                # Piazzamento Griglia Lineare
                accumulated_drop = 0
                spacing = get_spacing(current_mode)
                
                for i in range(1, 13):
                    accumulated_drop += spacing
                    entry_price = round(avg * (1 - accumulated_drop / 100), 4)
                    qty = GRID_SIZES[i] if i < len(GRID_SIZES) else 15
                    
                    session.place_order(category="linear", symbol=SYMBOL, side="Buy",
                                      orderType="Limit", qty=str(qty), price=str(entry_price))
                    
                last_trade_time = now

        time.sleep(5)

    except Exception as e:
        print(f"⚠️ Errore: {e}")
        time.sleep(10)
