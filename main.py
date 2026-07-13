import os
import time
import datetime
import asyncio
from pybit.unified_trading import HTTP
import telegram

# ==============================================================================
# CONFIGURAZIONE
# ==============================================================================
SYMBOL = "UAIUSDT"

QTY_LIVELLO_NORMALE = 100
QTY_LIVELLO_ALTO = 50
QTY_LIVELLO_ESTREMO = 20

SOGLIA_ALTA_VOLATILITA = 25.0
SOGLIA_ESTREMA_VOLATILITA = 50.0

RESET_DA_ALTO_A_NORMALE = 18.0
RESET_DA_ESTREMO_A_ALTO = 35.0

GRID_MULTIPLIERS = [1, 1, 1.1, 1.3, 1.5, 2.4, 2.7, 2.9]
GRID_SPACING = [0.0, 0.8, 1.0, 1.2, 1.5, 3.0, 4.0, 6.0]

TAKE_PROFIT_PERCENT = 1.0
STOP_LOSS_PERCENT = 21.0
COOLDOWN = 30

PRICE_DECIMALS = 5
QTY_DECIMALS = 0

# ==============================================================================
# VARIABILI DI STATO
# ==============================================================================
last_trade_time = 0.0
last_tp_price = 0.0
last_tp_update_time = 0.0
prezzo_inizio_griglia = 0.0

stato_rischio_attuale = "NORMALE"
BASE_QTY = QTY_LIVELLO_NORMALE

# ==============================================================================
# CONNESSIONI
# ==============================================================================
session = HTTP(
    testnet=False,
    api_key=os.environ.get("BYBIT_API_KEY"),
    api_secret=os.environ.get("BYBIT_API_SECRET")
)

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)

ultimo_report = ""


async def telegram_send(msg):
    try:
        await bot.send_message(chat_id=CHAT_ID, text=msg)
    except Exception as e:
        print(f"Errore Telegram: {e}")


def get_wallet_balance():
    try:
        w = session.get_wallet_balance(accountType="UNIFIED", coin="USDT")
        return float(w["result"]["list"][0]["coin"][0]["walletBalance"])
    except Exception as e:
        print(f"Errore saldo: {e}")
        return None


def check_daily_report():
    global ultimo_report
    nowdt = datetime.datetime.now()
    key = nowdt.strftime("%Y-%m-%d_%H:%M")
    
    if nowdt.strftime("%H:%M") in ("06:00", "18:00") and key != ultimo_report:
        bal = get_wallet_balance()
        if bal is not None:
            asyncio.run(telegram_send(
                f"📊 REPORT BOT\n\n"
                f"💰 Saldo USDT: {bal:.2f}\n"
                f"🪙 {SYMBOL}\n"
                f"🕒 {nowdt.strftime('%d/%m/%Y %H:%M')}"
            ))
            ultimo_report = key


# ==============================================================================
# FUNZIONI
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
            category="linear", symbol=SYMBOL, interval="60", limit=24
        )["result"]["list"]

        if not kline_data:
            return 0.0

        highs = [float(c[2]) for c in kline_data]
        lows = [float(c[3]) for c in kline_data]
        open_24h = float(kline_data[-1][1])

        volatility = ((max(highs) - min(lows)) / open_24h) * 100
        return volatility
    except Exception as e:
        print(f"Errore volatilità: {e}")
        return 0.0


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
            category="linear", symbol=SYMBOL, side=side,
            orderType="Market", qty=str(abs(size)), reduceOnly=True
        )
        print(f" POSIZIONE CHIUSA | Size: {size}")
        return True
    except Exception as e:
        print(f"Errore close position: {e}")
        return False


def get_current_price():
    try:
        ticker = session.get_tickers(category="linear", symbol=SYMBOL)
        return float(ticker['result']['list'][0]['lastPrice'])
    except:
        return None


# ==============================================================================
# CICLO PRINCIPALE
# ==============================================================================
print("🚀 BOT GRID LEVA 1 - AVVIATO")
print(f"Simbolo: {SYMBOL}\n")

while True:
    try:
        check_daily_report()
        now = time.time()
        price = get_current_price()

        pos_data = session.get_positions(category="linear", symbol=SYMBOL)["result"]["list"][0]
        size = float(pos_data.get("size", 0)) if pos_data.get("side") == "Buy" else 0.0
        avg_price = float(pos_data.get("avgPrice", 0))

        active_orders = session.get_open_orders(category="linear", symbol=SYMBOL)["result"]["list"]

        if size == 0:
            last_tp_price = 0.0
            prezzo_inizio_griglia = 0.0

        # === TAKE PROFIT ===
        if size > 0 and price:
            target_tp = round_price(avg_price * (1 + TAKE_PROFIT_PERCENT / 100))
            if price >= target_tp:
                print("🎯 Target Profit raggiunto - Chiusura griglia")
                cancel_all_orders()
                close_position()
                last_trade_time = now
            elif abs(target_tp - last_tp_price) > 1e-5 and (now - last_tp_update_time > 10):
                # Aggiorna TP
                for o in active_orders:
                    if o.get("side") == "Sell" and o.get("orderType") == "Limit":
                        session.cancel_order(category="linear", symbol=SYMBOL, orderId=o["orderId"])
                        break
                session.place_order(
                    category="linear", symbol=SYMBOL, side="Sell",
                    orderType="Limit", qty=str(size), price=str(target_tp), reduceOnly=True
                )
                last_tp_price = target_tp
                last_tp_update_time = now

        # === NUOVA GRIGLIA ===
        elif size == 0 and (now - last_trade_time > COOLDOWN):
            daily_vol = get_daily_volatility()

            # Gestione rischio
            if daily_vol > SOGLIA_ESTREMA_VOLATILITA:
                stato_rischio_attuale = "ESTREMO"
                BASE_QTY = QTY_LIVELLO_ESTREMO
            elif daily_vol > SOGLIA_ALTA_VOLATILITA:
                stato_rischio_attuale = "ALTO"
                BASE_QTY = QTY_LIVELLO_ALTO
            else:
                stato_rischio_attuale = "NORMALE"
                BASE_QTY = QTY_LIVELLO_NORMALE

            print(f"[{stato_rischio_attuale}] Volatilità 24h: {daily_vol:.2f}% | Size: {BASE_QTY}")

            MAX_TOTAL_QTY = round_qty(sum(BASE_QTY * m for m in GRID_MULTIPLIERS))
            cancel_all_orders()
            time.sleep(1)

            # L1 Market
            session.place_order(
                category="linear", symbol=SYMBOL, side="Buy",
                orderType="Market", qty=str(round_qty(BASE_QTY * GRID_MULTIPLIERS[0]))
            )
            time.sleep(2)

            new_pos = session.get_positions(category="linear", symbol=SYMBOL)["result"]["list"][0]
            prezzo_inizio_griglia = float(new_pos["avgPrice"])
            sl_price = round_price(prezzo_inizio_griglia * (1 - STOP_LOSS_PERCENT / 100))

            # Stop Loss
            session.place_order(
                category="linear", symbol=SYMBOL, side="Sell",
                orderType="Market", qty=str(MAX_TOTAL_QTY),
                triggerPrice=str(sl_price), triggerBy="LastPrice",
                triggerDirection=2, reduceOnly=True
            )

            # Livelli Limit
            acc_drop = 0.0
            for i in range(1, 8):
                acc_drop += GRID_SPACING[i]
                entry_p = round_price(prezzo_inizio_griglia * (1 - acc_drop / 100))
                qty = round_qty(BASE_QTY * GRID_MULTIPLIERS[i])
                session.place_order(
                    category="linear", symbol=SYMBOL, side="Buy",
                    orderType="Limit", qty=str(qty), price=str(entry_p)
                )
                print(f"[L{i+1}] @ {entry_p:.5f} | Qty: {qty}")

            last_trade_time = now
            print("✅ Griglia attivata\n")

        time.sleep(2)

    except Exception as e:
        print(f"[ERRORE] {e}")
        time.sleep(5)
