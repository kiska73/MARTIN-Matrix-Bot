import os
import time
import requests
from datetime import datetime
from pybit.unified_trading import HTTP

# ==============================================================================
# CONFIGURAZIONE OPERATIVA
# ==============================================================================
SYMBOL = "UAIUSDT"

# ==================== TELEGRAM ====================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

# Le tue 3 Size personalizzabili
QTY_LIVELLO_NORMALE = 100
QTY_LIVELLO_ALTO = 50
QTY_LIVELLO_ESTREMO = 20

SOGLIA_ALTA_VOLATILITA = 25.0
SOGLIA_ESTREMA_VOLATILITA = 50.0

RESET_DA_ALTO_A_NORMALE = 18.0
RESET_DA_ESTREMO_A_ALTO = 35.0

GRID_MULTIPLIERS = [1, 1, 1.1, 1.3, 1.5, 2.4, 2.7, 2.9]
GRID_SPACING = [0.0, 0.8, 1.0, 1.2, 1.5, 3.0, 4.0, 6.0]

TAKE_PROFIT_PERCENT = 1
STOP_LOSS_PERCENT = 21
COOLDOWN = 30

# ==============================================================================
# DECIMALI STRUMENTO
# ==============================================================================
PRICE_DECIMALS = 5
QTY_DECIMALS = 0 

# ==============================================================================
# VARIABILI DI STATO
# ==============================================================================
last_trade_time = 0
last_tp_price = 0.0
last_tp_update_time = 0
prezzo_inizio_griglia = 0.0 

stato_rischio_attuale = "NORMALE"  
BASE_QTY = QTY_LIVELLO_NORMALE

last_morning_notification = None
last_evening_notification = None

# Connessione Bybit
session = HTTP(
    testnet=False, 
    api_key=os.environ.get("BYBIT_API_KEY"), 
    api_secret=os.environ.get("BYBIT_API_SECRET")
)

# ==============================================================================
# FUNZIONI TELEGRAM E SALDO
# ==============================================================================
def send_telegram_message(message):
    if not TELEGRAM_BOT_TOKEN or not CHAT_ID:
        print("⚠️ Telegram credentials non configurate")
        return False
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        }
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code != 200:
            print(f"❌ Telegram Error: {r.text}")
        return r.status_code == 200
    except Exception as e:
        print(f"❌ Errore invio Telegram: {e}")
        return False


def get_account_balance():
    try:
        resp = session.get_wallet_balance(accountType="UNIFIED")
        coins = resp["result"]["list"][0]["coin"]
        for coin in coins:
            if coin["coin"] == "USDT":
                return float(coin.get("walletBalance", 0))
        return 0.0
    except Exception as e:
        print(f"⚠️ Errore recupero saldo: {e}")
        return 0.0


def send_balance_notification(title):
    balance = get_account_balance()
    current_time = datetime.now()
    msg = f"<b>{title}</b>\n\n" \
          f"💰 Saldo USDT: <b>{balance:,.2f}</b>\n" \
          f"🕒 {current_time.strftime('%Y-%m-%d %H:%M:%S')}\n" \
          f"📊 Bot Grid UAIUSDT"
    send_telegram_message(msg)
    print(f"📨 {title} inviata su Telegram")


# ==============================================================================
# FUNZIONI UTILITARIE
# ==============================================================================
def round_price(price):
    return round(price, PRICE_DECIMALS)

def round_qty(qty):
    if QTY_DECIMALS == 0:
        return int(round(qty))
    return round(qty, QTY_DECIMALS)

def get_daily_volatility():
    try:
        kline_data = session.get_kline(
            category="linear",
            symbol=SYMBOL,
            interval="60",
            limit=24
        )["result"]["list"]
        
        if not kline_data:
            return 0.0
            
        highs = [float(candle[2]) for candle in kline_data]
        lows = [float(candle[3]) for candle in kline_data]
        open_24h_ago = float(kline_data[-1][1])
        
        volatility = ((max(highs) - min(lows)) / open_24h_ago) * 100
        return volatility
    except Exception as e:
        print(f" ⚠️ Errore volatilità: {e}")
        return 0.0

def cancel_all_orders():
    try:
        session.cancel_all_orders(category="linear", symbol=SYMBOL)
        time.sleep(0.5)
        print(" [SISTEMA] Tutti gli ordini cancellati")
        return True
    except Exception as e:
        print(f" Errore cancel all: {e}")
        return False

def close_position():
    try:
        pos = session.get_positions(category="linear", symbol=SYMBOL)["result"]["list"][0]
        size = float(pos.get("size", 0))
        if size == 0:
            return False
        
        side = "Sell" if pos.get("side") == "Buy" else "Buy"
        session.place_order(
            category="linear", symbol=SYMBOL, side=side, 
            orderType="Market", qty=str(abs(size)), reduceOnly=True
        )
        print(f" 💥 Posizione chiusa a mercato | Size: {size}")
        return True
    except Exception as e:
        print(f" Errore chiusura posizione: {e}")
        return False

def get_current_price():
    try:
        ticker = session.get_tickers(category="linear", symbol=SYMBOL)
        return float(ticker['result']['list'][0]['lastPrice'])
    except:
        return None

# ==============================================================================
# AVVIO BOT
# ==============================================================================
print(" 🤖 BOT GRID LEVA 1 (v8.8 - Telegram Startup + 06/18)")
print(f" Strumento: {SYMBOL}")

# Notifica di avvio
send_balance_notification("🚀 BOT AVVIATO")

print(f" Notifiche Telegram attive: Avvio + 06:00 + 18:00\n")

while True:
    try:
        now = time.time()
        price = get_current_price()
        
        pos_data = session.get_positions(category="linear", symbol=SYMBOL)["result"]["list"][0]
        pos_side = pos_data.get("side", "None")
        raw_size = float(pos_data.get("size", 0))
        size = raw_size if (pos_side == "Buy" and raw_size > 0) else 0.0
        avg_price = float(pos_data.get("avgPrice", 0))
        
        active_orders = session.get_open_orders(category="linear", symbol=SYMBOL)["result"]["list"]

        # ==================== NOTIFICHE TELEGRAM ORARIO ====================
        current_dt = datetime.now()
        ch = current_dt.hour
        cm = current_dt.minute

        if ch == 6 and cm == 0 and (last_morning_notification is None or last_morning_notification.date() != current_dt.date()):
            send_balance_notification("🌅 Saldo Account - 06:00")
            last_morning_notification = current_dt

        if ch == 18 and cm == 0 and (last_evening_notification is None or last_evening_notification.date() != current_dt.date()):
            send_balance_notification("🌆 Saldo Account - 18:00")
            last_evening_notification = current_dt

        # ==================== GESTIONE TARGET PROFIT ====================
        if size > 0:
            target_tp = round_price(avg_price * (1 + TAKE_PROFIT_PERCENT / 100))

            if price and price >= target_tp:
                print(f" 🎯 Target raggiunto! Chiusura griglia.")
                cancel_all_orders()
                close_position()
                last_trade_time = now
                last_tp_price = 0.0
                prezzo_inizio_griglia = 0.0
            
            elif (abs(target_tp - last_tp_price) > (10 ** -PRICE_DECIMALS)) and (now - last_tp_update_time > 10):
                tp_orders = [o for o in active_orders if o.get("side") == "Sell" and o.get("orderType") == "Limit" and o.get("reduceOnly") is True]
                
                update_needed = not tp_orders
                if tp_orders:
                    current_tp = float(tp_orders[0]["price"])
                    if abs(current_tp - target_tp) > (10 ** -PRICE_DECIMALS):
                        update_needed = True
                        try:
                            session.cancel_order(category="linear", symbol=SYMBOL, orderId=tp_orders[0]["orderId"])
                        except:
                            pass

                if update_needed:
                    try:
                        session.place_order(
                            category="linear", symbol=SYMBOL, side="Sell", orderType="Limit",
                            qty=str(size), price=str(target_tp), reduceOnly=True
                        )
                        last_tp_price = target_tp
                        last_tp_update_time = now
                        print(f" 📈 TP aggiornato → {target_tp}")
                    except:
                        pass

        # ==================== GENERAZIONE GRIGLIA ====================
        elif size == 0 and (now - last_trade_time > COOLDOWN):
            safe_price = price if price is not None else 0.0
            daily_vol = get_daily_volatility()

            # Gestione stato rischio
            if daily_vol > SOGLIA_ESTREMA_VOLATILITA:
                stato_rischio_attuale = "ESTREMO"
            elif daily_vol > SOGLIA_ALTA_VOLATILITA and stato_rischio_attuale != "ESTREMO":
                stato_rischio_attuale = "ALTO"
            elif stato_rischio_attuale == "ESTREMO" and daily_vol < RESET_DA_ESTREMO_A_ALTO:
                stato_rischio_attuale = "ALTO" if daily_vol >= RESET_DA_ALTO_A_NORMALE else "NORMALE"
            elif stato_rischio_attuale == "ALTO" and daily_vol < RESET_DA_ALTO_A_NORMALE:
                stato_rischio_attuale = "NORMALE"

            # Assegna BASE_QTY
            if stato_rischio_attuale == "ESTREMO":
                BASE_QTY = QTY_LIVELLO_ESTREMO
                print(f" 🔥 [ESTREMO] Vol {daily_vol:.2f}% → Size {BASE_QTY}")
            elif stato_rischio_attuale == "ALTO":
                BASE_QTY = QTY_LIVELLO_ALTO
                print(f" ⚠️ [ALTO] Vol {daily_vol:.2f}% → Size {BASE_QTY}")
            else:
                BASE_QTY = QTY_LIVELLO_NORMALE
                print(f" ✅ [NORMALE] Vol {daily_vol:.2f}% → Size {BASE_QTY}")

            MAX_TOTAL_QTY = round_qty(sum([BASE_QTY * m for m in GRID_MULTIPLIERS]))

            print(f"\n 🛒 Avvio nuova griglia @ {safe_price:.4f} (Max Qty: {MAX_TOTAL_QTY})")
            cancel_all_orders()
            time.sleep(1.0)

            # Livello 1 Market
            qty_l1 = round_qty(BASE_QTY * GRID_MULTIPLIERS[0])
            session.place_order(category="linear", symbol=SYMBOL, side="Buy", orderType="Market", qty=str(qty_l1))
            print(f" 🟢 [L1] Market eseguito: {qty_l1} UAI")

            time.sleep(2.0)
            new_pos = session.get_positions(category="linear", symbol=SYMBOL)["result"]["list"][0]
            prezzo_inizio_griglia = float(new_pos["avgPrice"])
            prezzo_sl = round_price(prezzo_inizio_griglia * (1 - STOP_LOSS_PERCENT / 100))

            # Stop Loss
            session.place_order(
                category="linear", symbol=SYMBOL, side="Sell", orderType="Market",
                qty=str(MAX_TOTAL_QTY), triggerPrice=str(prezzo_sl),
                triggerBy="LastPrice", triggerDirection=2, reduceOnly=True
            )
            print(f" 🛑 Stop Loss inserito a {prezzo_sl:.5f}")

            # Livelli Limit
            accumulated_drop = 0
            for i in range(1, len(GRID_MULTIPLIERS)):
                accumulated_drop += GRID_SPACING[i]
                entry_price = round_price(prezzo_inizio_griglia * (1 - accumulated_drop / 100))
                qty_livello = round_qty(BASE_QTY * GRID_MULTIPLIERS[i])
                
                session.place_order(
                    category="linear", symbol=SYMBOL, side="Buy",
                    orderType="Limit", qty=str(qty_livello), price=str(entry_price)
                )
                print(f" 📥 [L{i+1}] Limit @ {entry_price:.5f} | Qty: {qty_livello}")

            last_trade_time = now
            print(" ✅ Griglia configurata con successo!\n")

        time.sleep(2)

    except Exception as e:
        print(f" [ERRORE] Ciclo principale: {e}")
        time.sleep(5)
