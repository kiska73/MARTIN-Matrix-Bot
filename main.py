import os
import time
import pandas as pd
from pybit.unified_trading import HTTP

# ==========================================================
# CONFIG
# ==========================================================
API_KEY = os.environ.get("BYBIT_API_KEY")
API_SECRET = os.environ.get("BYBIT_API_SECRET")
SYMBOL = "LABUSDT"

session = HTTP(testnet=False, api_key=API_KEY, api_secret=API_SECRET)

GRID_SIZES = [2, 2, 2, 2, 5, 7, 9, 11, 15, 20, 25, 30, 50]
COOLDOWN = 18  # secondi

# Stato globale
last_trade_time = 0
last_candle_ts = 0
last_checked_ts = 0

def get_current_price():
    try:
        ticker = session.get_tickers(category="linear", symbol=SYMBOL)
        return float(ticker['result']['list'][0]['lastPrice'])
    except:
        return None

def get_bollinger_bands(symbol, period=40, std_dev=2):
    try:
        data = session.get_kline(
            category="linear", 
            symbol=symbol, 
            interval="240", 
            limit=period + 2
        )
        df = pd.DataFrame(data['result']['list'], 
                         columns=['ts', 'open', 'high', 'low', 'close', 'vol', 'turnover'])
        
        df['close'] = df['close'].astype(float)
        df['low'] = df['low'].astype(float)
        df['ts'] = df['ts'].astype(int)
        
        sma = df['close'].rolling(window=period).mean()
        std = df['close'].rolling(window=period).std()
        lower_band = sma - (std * std_dev)
        
        return {
            'ts': df['ts'].iloc[-1],           # timestamp della candela più recente
            'lower_band': lower_band.iloc[-1],
            'candle_low': df['low'].iloc[-1],
            'candle_close_time': df['ts'].iloc[-1] / 1000 + 14400  # tempo di chiusura candela
        }
    except Exception as e:
        print(f"Errore get_klines: {e}")
        return None


print("🚀 BOT AVVIATO - TP DINAMICO + SL SENTINELLA CON PROTEZIONE FLASH CRASH")

while True:
    try:
        now = time.time()
        
        # ==================== POSIZIONE APERTA ====================
        pos_list = session.get_positions(category="linear", symbol=SYMBOL)["result"]["list"]
        pos = pos_list[0]
        size = float(pos["size"])
        avg_price = float(pos["avgPrice"])
        
        active_orders = session.get_open_orders(category="linear", symbol=SYMBOL)["result"]["list"]
        tp_orders = [o for o in active_orders if o["side"] == "Sell" and o["orderType"] == "Limit"]
        sl_orders = [o for o in active_orders if o.get("triggerPrice") and o["side"] == "Sell"]

        if size > 0:
            # ===================== SL SENTINELLA =====================
            bb = get_bollinger_bands(SYMBOL)
            if bb and bb['ts'] != last_candle_ts:
                # Controlliamo solo dopo la chiusura della candela + ~6 secondi
                if now > bb['candle_close_time'] + 6:
                    current_price = get_current_price()
                    last_low = bb['candle_low']
                    lower_band = bb['lower_band']
                    
                    print(f"📊 Nuova candela 4H chiusa - Low: {last_low:.4f} | Lower Band: {lower_band:.4f} | Prezzo: {current_price:.4f}")
                    
                    if last_low < lower_band:
                        if current_price is not None and current_price <= last_low * 0.999:  # già sotto
                            print(f"🚨 FLASH CRASH DETECTED! Chiusura immediata a mercato @ {current_price}")
                            session.place_order(
                                category="linear", symbol=SYMBOL, side="Sell",
                                orderType="Market", qty=str(size), reduceOnly=True
                            )
                        elif not sl_orders:
                            print(f"📉 Imposto SL Sentinella a: {last_low:.4f}")
                            session.place_order(
                                category="linear", symbol=SYMBOL, side="Sell",
                                orderType="Market", qty=str(size),
                                triggerPrice=str(round(last_low, 4)),
                                triggerDirection=2,           # 2 = BelowPrice
                                triggerBy="LastPrice",
                                reduceOnly=True
                            )
                    
                    last_candle_ts = bb['ts']
            
            # ===================== TP DINAMICO =====================
            target_price = round(avg_price * 1.009, 4)
            
            if tp_orders:
                current_tp = float(tp_orders[0]["price"])
                if abs(current_tp - target_price) > 0.0001:
                    print(f"🔄 Aggiorno TP: {current_tp} → {target_price}")
                    session.cancel_order(category="linear", symbol=SYMBOL, orderId=tp_orders[0]["orderId"])
                    session.place_order(
                        category="linear", symbol=SYMBOL, side="Sell",
                        orderType="Limit", qty=str(size), price=str(target_price),
                        reduceOnly=True
                    )
            else:
                session.place_order(
                    category="linear", symbol=SYMBOL, side="Sell",
                    orderType="Limit", qty=str(size), price=str(target_price),
                    reduceOnly=True
                )

        # ==================== POSIZIONE CHIUSA → NUOVA ENTRATA ====================
        elif size == 0 and (now - last_trade_time > COOLDOWN):
            print("🧹 Nessuna posizione → Reset e nuova entrata")
            session.cancel_all_orders(category="linear", symbol=SYMBOL)
            
            # Entrata iniziale
            session.place_order(
                category="linear", symbol=SYMBOL, side="Buy",
                orderType="Market", qty=str(GRID_SIZES[0])
            )
            time.sleep(2)
            
            new_pos = session.get_positions(category="linear", symbol=SYMBOL)["result"]["list"][0]
            new_size = float(new_pos["size"])
            
            if new_size > 0:
                avg = float(new_pos["avgPrice"])
                print(f"✅ Entrata eseguita @ {avg}")
                
                # Grid di buy limit
                for i in range(1, len(GRID_SIZES)):
                    price = avg * (1 - (1.2 * i) / 100)
                    session.place_order(
                        category="linear", symbol=SYMBOL, side="Buy",
                        orderType="Limit", qty=str(GRID_SIZES[i]),
                        price=str(round(price, 4))
                    )
                
                last_trade_time = now

        time.sleep(5)

    except Exception as e:
        print(f"⚠️ Errore critico: {e}")
        time.sleep(10)
