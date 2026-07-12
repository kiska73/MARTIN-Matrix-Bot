import os
import time
import requests
from datetime import datetime
from pybit.unified_trading import HTTP

# ==============================================================================
# CONFIGURAZIONE TELEGRAM
# ==============================================================================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

def send_telegram_message(message):
    """Invia messaggio su Telegram"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        }
        requests.post(url, json=payload, timeout=10)
        print(f" 📨 Telegram inviato")
    except Exception as e:
        print(f" ⚠️ Errore invio Telegram: {e}")


# ==============================================================================
# CONFIGURAZIONE OPERATIVA
# ==============================================================================
SYMBOL = "UAIUSDT"

# Quantità per livello di rischio
QTY_LIVELLO_NORMALE = 100
QTY_LIVELLO_ALTO = 50
QTY_LIVELLO_ESTREMO = 20

# Soglie volatilità
SOGLIA_ALTA_VOLATILITA = 25.0
SOGLIA_ESTREMA_VOLATILITA = 50.0
RESET_DA_ALTO_A_NORMALE = 18.0
RESET_DA_ESTREMO_A_ALTO = 35.0

# Griglia
GRID_MULTIPLIERS = [1, 1, 1.1, 1.3, 1.5, 2.4, 2.7, 2.9]
GRID_SPACING = [0.0, 0.8, 1.0, 1.2, 1.5, 3.0, 4.0, 6.0]

TAKE_PROFIT_PERCENT = 1
STOP_LOSS_PERCENT = 21
COOLDOWN = 30

# Decimali
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

last_notification_6 = None
last_notification_18 = None

# ==============================================================================
# CONNESSIONE BYBIT
# ==============================================================================
session = HTTP(
    testnet=False,
    api_key=os.environ.get("BYBIT_API_KEY"),
    api_secret=os.environ.get("BYBIT_API_SECRET")
)

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
        
        highs = [float(candle[2]) for candle in kline_data]
        lows = [float(candle[3]) for candle in kline_data]
        open_24h_ago = float(kline_data[-1][1])
        
        volatility = ((max(highs) - min(lows)) / open_24h_ago) * 100
        return volatility
    except Exception as e:
        print(f" ⚠️ Errore volatilità: {e}")
        return 0.0

def get_wallet_balance():
    try:
        balance = session.get_wallet_balance(accountType="UNIFIED")["result"]["list"][0]
        for coin in balance["coin"]:
            if coin["coin"] == "USDT":
                return float(coin.get("walletBalance", 0))
        return 0.0
    except Exception as e:
        print(f" ⚠️ Errore wallet: {e}")
        return 0.0

def get_position_info():
    try:
        pos = session.get_positions(category="linear", symbol=SYMBOL)["result"]["list"][0]
        size = float(pos.get("size", 0))
        if size == 0:
            return None
        return {
            "size": size,
            "side": pos.get("side"),
            "avg_price": float(pos.get("avgPrice", 0)),
            "unrealized_pnl": float(pos.get("unrealisedPnl", 0))
        }
    except:
        return None

def cancel_all_orders():
    try:
        session.cancel_all_orders(category="linear", symbol=SYMBOL)
        time.sleep(0.5)
        return True
    except:
        return False

def close_position():
    try:
        pos = session.get_positions(category="linear", symbol=SYMBOL)["result"]["list"][0]
        size = float(pos.get("size", 0))
        if size == 0:
            return False
        side = "Sell" if pos.get("side") == "Buy" else "Buy"
        session.place_order(
            category="linear", symbol=SYMBOL, side=side, orderType="Market",
            qty=str(abs(size)), reduceOnly=True
        )
        print(f" 💥 Posizione chiusa a mercato")
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
print(" 🤖 BOT GRID UAIUSDT v8.9 - Completo con Telegram")
print(f" Strumento: {SYMBOL}")

# Report iniziale
initial_balance = get_wallet_balance()
pos_info = get_position_info()
current_price = get_current_price()

start_msg = f"""🚀 <b>BOT AVVIATO CORRETTAMENTE</b>

💰 <b>Saldo Wallet:</b> <code>{initial_balance:.2f} USDT</code>
"""

if pos_info:
    pnl_pct = (pos_info["unrealized_pnl"] / (pos_info["avg_price"] * pos_info["size"])) * 100 if pos_info["size"] > 0 else 0
    start_msg += f"""📍 <b>POSIZIONE APERTA</b>
   • Size: <code>{pos_info['size']} UAI</code>
   • Avg Price: <code>{pos_info['avg_price']:.5f}</code>
   • Prezzo Attuale: <code>{current_price:.5f if current_price else 'N/A'}</code>
   • Unrealized PnL: <code>{pos_info['unrealized_pnl']:.2f} USDT</code> ({pnl_pct:+.2f}%)
"""
else:
    start_msg += "📍 Nessuna posizione aperta al momento.\n"

start_msg += f"🕒 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n✅ Bot in monitoraggio."
send_telegram_message(start_msg)

print(f" 💰 Saldo iniziale: {initial_balance:.2f} USDT\n")

# ==============================================================================
# CICLO CONTINUO
# ==============================================================================
while True:
    try:
        now = time.time()
        current_dt = datetime.now()
        price = get_current_price()

        # ==================== REPORT TELEGRAM 06:00 e 18:00 ====================
        h = current_dt.hour
        m = current_dt.minute

        if h == 6 and m == 0:
            if last_notification_6 is None or last_notification_6.date() != current_dt.date():
                balance = get_wallet_balance()
                pos = get_position_info()
                msg = f"""🕕 <b>Report Mattutino - 06:00</b>

💰 <b>Wallet:</b> <code>{balance:.2f} USDT</code>
🔄 <b>Stato Rischio:</b> {stato_rischio_attuale}
"""

                if pos:
                    current_p = price if price else 0
                    pnl_pct = (pos["unrealized_pnl"] / (pos["avg_price"] * pos["size"])) * 100 if pos["size"] > 0 else 0
                    msg += f"""📍 <b>POSIZIONE APERTA</b>
   • Size: <code>{pos['size']} UAI</code>
   • Entry: <code>{pos['avg_price']:.5f}</code>
   • Prezzo: <code>{current_p:.5f}</code>
   • PnL: <code>{pos['unrealized_pnl']:.2f} USDT</code> (<code>{pnl_pct:+.2f}%</code>)
"""
                else:
                    msg += "📍 Nessuna posizione aperta\n"
                
                msg += f"🕒 {current_dt.strftime('%Y-%m-%d %H:%M:%S')}"
                send_telegram_message(msg)
                last_notification_6 = current_dt

        elif h == 18 and m == 0:
            if last_notification_18 is None or last_notification_18.date() != current_dt.date():
                balance = get_wallet_balance()
                pos = get_position_info()
                msg = f"""🕕 <b>Report Serale - 18:00</b>

💰 <b>Wallet:</b> <code>{balance:.2f} USDT</code>
🔄 <b>Stato Rischio:</b> {stato_rischio_attuale}
"""

                if pos:
                    current_p = price if price else 0
                    pnl_pct = (pos["unrealized_pnl"] / (pos["avg_price"] * pos["size"])) * 100 if pos["size"] > 0 else 0
                    msg += f"""📍 <b>POSIZIONE APERTA</b>
   • Size: <code>{pos['size']} UAI</code>
   • Entry: <code>{pos['avg_price']:.5f}</code>
   • Prezzo: <code>{current_p:.5f}</code>
   • PnL: <code>{pos['unrealized_pnl']:.2f} USDT</code> (<code>{pnl_pct:+.2f}%</code>)
"""
                else:
                    msg += "📍 Nessuna posizione aperta\n"
                
                msg += f"🕒 {current_dt.strftime('%Y-%m-%d %H:%M:%S')}"
                send_telegram_message(msg)
                last_notification_18 = current_dt

        # ==================== GESTIONE POSIZIONE ====================
        pos_data = session.get_positions(category="linear", symbol=SYMBOL)["result"]["list"][0]
        raw_size = float(pos_data.get("size", 0))
        pos_side = pos_data.get("side", "None")
        size = raw_size if (pos_side == "Buy" and raw_size > 0) else 0.0
        avg_price = float(pos_data.get("avgPrice", 0))

        active_orders = session.get_open_orders(category="linear", symbol=SYMBOL)["result"]["list"]

        if size == 0:
            last_tp_price = 0.0
            prezzo_inizio_griglia = 0.0

        # ==================== TARGET PROFIT ====================
        if size > 0:
            target_tp = round_price(avg_price * (1 + TAKE_PROFIT_PERCENT / 100))

            if price and price >= target_tp:
                print(f" 🎯 Target Profit raggiunto ({price} >= {target_tp}). Chiusura griglia.")
                cancel_all_orders()
                close_position()
                last_trade_time = now
                last_tp_price = 0.0
                prezzo_inizio_griglia = 0.0

            elif abs(target_tp - last_tp_price) > 0.00001 and (now - last_tp_update_time > 10):
                tp_orders = [o for o in active_orders if o.get("side") == "Sell" and o.get("orderType") == "Limit" and o.get("reduceOnly")]
                if tp_orders:
                    try:
                        session.cancel_order(category="linear", symbol=SYMBOL, orderId=tp_orders[0]["orderId"])
                    except:
                        pass

                try:
                    session.place_order(
                        category="linear", symbol=SYMBOL, side="Sell", orderType="Limit",
                        qty=str(size), price=str(target_tp), reduceOnly=True
                    )
                    last_tp_price = target_tp
                    last_tp_update_time = now
                    print(f" 📈 TP aggiornato a {target_tp}")
                except:
                    pass

        # ==================== APERTURA NUOVA GRIGLIA ====================
        elif size == 0 and (now - last_trade_time > COOLDOWN):
            daily_vol = get_daily_volatility()

            # Macchina a stati rischio
            if daily_vol > SOGLIA_ESTREMA_VOLATILITA:
                stato_rischio_attuale = "ESTREMO"
            elif daily_vol > SOGLIA_ALTA_VOLATILITA and stato_rischio_attuale != "ESTREMO":
                stato_rischio_attuale = "ALTO"
            elif stato_rischio_attuale == "ESTREMO" and daily_vol < RESET_DA_ESTREMO_A_ALTO:
                stato_rischio_attuale = "ALTO" if daily_vol >= RESET_DA_ALTO_A_NORMALE else "NORMALE"
            elif stato_rischio_attuale == "ALTO" and daily_vol < RESET_DA_ALTO_A_NORMALE:
                stato_rischio_attuale = "NORMALE"

            # Assegna quantità base
            if stato_rischio_attuale == "ESTREMO":
                BASE_QTY = QTY_LIVELLO_ESTREMO
            elif stato_rischio_attuale == "ALTO":
                BASE_QTY = QTY_LIVELLO_ALTO
            else:
                BASE_QTY = QTY_LIVELLO_NORMALE

            MAX_TOTAL_QTY = round_qty(sum([BASE_QTY * m for m in GRID_MULTIPLIERS]))
            safe_price = price if price is not None else 0.0

            print(f"\n 🛒 Avvio nuova griglia @ {safe_price:.4f} | Rischio: {stato_rischio_attuale} | Size base: {BASE_QTY}")

            cancel_all_orders()
            time.sleep(1.0)

            # Livello 1 - Market
            qty_l1 = round_qty(BASE_QTY * GRID_MULTIPLIERS[0])
            session.place_order(category="linear", symbol=SYMBOL, side="Buy", orderType="Market", qty=str(qty_l1))
            print(f" 🟢 [L1] Market eseguito: {qty_l1} UAI")

            time.sleep(2.0)
            new_pos = session.get_positions(category="linear", symbol=SYMBOL)["result"]["list"][0]
            avg = float(new_pos["avgPrice"])
            prezzo_inizio_griglia = avg
            prezzo_sl = round_price(avg * (1 - STOP_LOSS_PERCENT / 100))

            # Stop Loss Nativo
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
            print(" ✅ Griglia configurata con successo.\n")

        time.sleep(2)

    except Exception as e:
        print(f" [ALLERTA] Errore nel ciclo: {e}")
        time.sleep(5)
