import os
import time
import pandas as pd
from pybit.unified_trading import HTTP
from datetime import datetime, timezone

# ==========================================================
# CONFIG
# ==========================================================
API_KEY = os.environ.get("BYBIT_API_KEY")
API_SECRET = os.environ.get("BYBIT_API_SECRET")
SYMBOL = "LABUSDT"

session = HTTP(testnet=False, api_key=API_KEY, api_secret=API_SECRET)

current_mode = "AGGRESSIVE"
pause_until_next_candle = False

GRID_SIZES = [2, 2, 2, 3, 4, 5, 6, 8, 10, 13, 16, 20, 25]

COOLDOWN = 20

def get_spacing(i, mode):
    """Fasce esatte come hai chiesto"""
    if mode == "AGGRESSIVE":
        if i <= 3:   return 1.0   # primi 3 ordini
        elif i <= 6: return 1.2
        elif i <= 9: return 1.5
        else:        return 1.8
    else:  # CONSERVATIVE
        if i <= 3:   return 2.0
        elif i <= 6: return 2.4
        elif i <= 9: return 2.8
        else:        return 3.2


def should_check_candle():
    now_utc = datetime.now(timezone.utc)
    hour = now_utc.hour
    minute = now_utc.minute
    second = now_utc.second
    if hour % 4 == 0 and minute == 0 and 5 <= second <= 15:
        return True
    return False


print("🚀 BOT MASTER - Griglia a Fasce Corretta")

while True:
    try:
        now = time.time()
        price = get_current_price()

        pos = session.get_positions(category="linear", symbol=SYMBOL)["result"]["list"][0]
        size = float(pos["size"])
        avg_price = float(pos.get("avgPrice", 0))

        active_orders = session.get_open_orders(category="linear", symbol=SYMBOL)["result"]["list"]
        tp_orders = [o for o in active_orders if o["side"] == "Sell" and o["orderType"] == "Limit"]
        sl_orders = [o for o in active_orders if o.get("triggerPrice")]

        # Controllo candela 4H
        if should_check_candle():
            vol_data = get_volatility_data(SYMBOL)
            if vol_data and vol_data['ts'] != last_candle_ts:
                print(f"📌 Candela 4H chiusa → {datetime.now().strftime('%H:%M:%S')}")

                new_mode = "CONSERVATIVE" if vol_data.get('bb_width', 0) > 40 else "AGGRESSIVE"
                if new_mode != current_mode:
                    print(f"🔄 CAMBIO MODALITÀ → {new_mode}")
                    current_mode = new_mode

                # Pausa
                if price and vol_data.get('lower_band'):
                    distance = ((price - vol_data['lower_band']) / vol_data['lower_band']) * 100
                    if distance <= 3.0:
                        pause_until_next_candle = True
                        print(f"⛔ PAUSA ATTIVATA ({distance:.1f}%)")
                    else:
                        pause_until_next_candle = False

                last_candle_ts = vol_data['ts']

        # Posizione aperta
        if size > 0:
            # TP Dinamico
            tp_percent = 1.20 if current_mode == "CONSERVATIVE" else 0.90
            target_tp = round(avg_price * (1 + tp_percent/100), 4)
            
            if tp_orders:
                if abs(float(tp_orders[0]["price"]) - target_tp) > 0.0002:
                    session.cancel_order(category="linear", symbol=SYMBOL, orderId=tp_orders[0]["orderId"])
                    session.place_order(category="linear", symbol=SYMBOL, side="Sell", orderType="Limit", qty=str(size), price=str(target_tp), reduceOnly=True)
            else:
                session.place_order(category="linear", symbol=SYMBOL, side="Sell", orderType="Limit", qty=str(size), price=str(target_tp), reduceOnly=True)

            # SL Sentinella
            if 'vol_data' in locals() and vol_data and vol_data['candle_low'] < vol_data['lower_band']:
                if price and price <= vol_data['candle_low'] * 0.997:
                    print(f"🚨 FLASH CRASH → Chiusura immediata")
                    session.place_order(category="linear", symbol=SYMBOL, side="Sell", orderType="Market", qty=str(size), reduceOnly=True)
                elif not sl_orders:
                    print(f"📉 SL Sentinella @ {vol_data['candle_low']}")
                    session.place_order(category="linear", symbol=SYMBOL, side="Sell", orderType="Market",
                                      qty=str(size), triggerPrice=str(vol_data['candle_low']),
                                      triggerDirection=2, triggerBy="LastPrice", reduceOnly=True)

        # Nuova entrata
        elif size == 0 and (now - last_trade_time > COOLDOWN):
            if pause_until_next_candle:
                print("⏳ In pausa...")
            else:
                print(f"🧹 Nuova entrata in modalità {current_mode}")
                session.cancel_all_orders(category="linear", symbol=SYMBOL)
                time.sleep(1.5)

                mode = current_mode

                session.place_order(category="linear", symbol=SYMBOL, side="Buy", orderType="Market", qty=str(GRID_SIZES[0]))
                time.sleep(2.5)

                new_pos = session.get_positions(category="linear", symbol=SYMBOL)["result"]["list"][0]
                if float(new_pos["size"]) > 0:
                    avg = float(new_pos["avgPrice"])
                    print(f"✅ Entrata @ {avg:.4f} | Modalità: {current_mode}")

                    for i in range(1, 13):
                        spacing = get_spacing(i, mode)
                        entry_price = round(avg * (1 - (spacing * i) / 100), 4)
                        qty = GRID_SIZES[i] if i < len(GRID_SIZES) else 15
                        session.place_order(category="linear", symbol=SYMBOL, side="Buy",
                                          orderType="Limit", qty=str(qty), price=str(entry_price))
                    
                    last_trade_time = now

        time.sleep(5)

    except Exception as e:
        print(f"⚠️ Errore: {e}")
        time.sleep(10)
