import os
import time
from pybit.unified_trading import HTTP

# ==========================================================
# CONFIG
# ==========================================================

API_KEY = os.environ.get("BYBIT_API_KEY")
API_SECRET = os.environ.get("BYBIT_API_SECRET")

SYMBOL = "LABUSDT"

session = HTTP(
    testnet=False,
    demo=False,
    api_key=API_KEY,
    api_secret=API_SECRET
)

GRID_SIZES = [2, 2, 2, 2, 5, 7, 9, 11, 15, 20, 25, 30, 50]

COOLDOWN = 10

# ==========================================================
# STATO
# ==========================================================

last_trade_time = 0
last_position_size = 0
entry_price = 0

# ==========================================================
# FUNZIONI
# ==========================================================

def get_position():
    try:
        r = session.get_positions(category="linear", symbol=SYMBOL)
        p = r["result"]["list"][0]
        return float(p["size"]), float(p["avgPrice"])
    except:
        return 0.0, 0.0


def get_price():
    t = session.get_tickers(category="linear", symbol=SYMBOL)
    return float(t["result"]["list"][0]["lastPrice"])


def cancel_orders():
    try:
        session.cancel_all_orders(category="linear", symbol=SYMBOL)
    except:
        pass


def place_grid(entry):
    for i in range(1, len(GRID_SIZES)):
        price = entry * (1 - (1.2 * i) / 100)

        session.place_order(
            category="linear",
            symbol=SYMBOL,
            side="Buy",
            orderType="Limit",
            qty=str(GRID_SIZES[i]),
            price=str(round(price, 4)),
            positionIdx=0
        )


def set_tp(size, avg):
    try:
        session.place_order(
            category="linear",
            symbol=SYMBOL,
            side="Sell",
            orderType="Limit",
            qty=str(size),
            price=str(round(avg * 1.009, 4)),
            positionIdx=0,
            reduceOnly=True
        )
    except:
        pass


# ==========================================================
# START
# ==========================================================

print("🚀 BOT AVVIATO")

# ==========================================================
# LOOP
# ==========================================================

while True:

    try:

        size, avg = get_position()
        price = get_price()

        # ======================================================
        # 1. POSIZIONE APERTA
        # ======================================================

        if size > 0:

            last_position_size = size
            entry_price = avg

            set_tp(size, avg)

        # ======================================================
        # 2. POSIZIONE CHIUSA
        # ======================================================

        elif size == 0 and last_position_size > 0:

            print("✅ Trade chiuso -> cooldown")

            last_trade_time = time.time()
            last_position_size = 0

        # ======================================================
        # 3. COOLDOWN
        # ======================================================

        elif size == 0 and last_position_size == 0:

            if time.time() - last_trade_time < COOLDOWN:

                print(
                    f"⏳ Cooldown {round(COOLDOWN - (time.time() - last_trade_time),1)}s"
                )

                time.sleep(1)
                continue

            # ==================================================
            # 4. NUOVA ENTRATA
            # ==================================================

            print("🧹 Nuovo ciclo")

            cancel_orders()

            session.place_order(
                category="linear",
                symbol=SYMBOL,
                side="Buy",
                orderType="Market",
                qty=str(GRID_SIZES[0]),
                positionIdx=0
            )

            time.sleep(2)

            size, avg = get_position()

            if size > 0:

                entry_price = avg
                last_position_size = size

                print(f"✅ Entry @ {avg}")

                place_grid(avg)

                set_tp(size, avg)

        # ======================================================
        # LOOP SLEEP
        # ======================================================

        time.sleep(3)

    except Exception as e:
        print("⚠️ Errore:", e)
        time.sleep(5)
