import os
import time
from pybit.unified_trading import HTTP

# =====================================================================
# CONFIGURAZIONE
# =====================================================================

API_KEY = os.environ.get("BYBIT_API_KEY")
API_SECRET = os.environ.get("BYBIT_API_SECRET")

SYMBOL = "LABUSDT"

session = HTTP(
    testnet=False,
    demo=False,
    api_key=API_KEY,
    api_secret=API_SECRET
)

GRID_SIZES_STANDARD = [2, 2, 2, 2, 5, 7, 9, 11, 15, 20, 25, 30, 50]

COOLDOWN_TRADE = 10  # secondi

# =====================================================================
# FUNZIONI SUPPORTO
# =====================================================================

def get_config_volatilita():

    try:

        klines = session.get_kline(
            category="linear",
            symbol=SYMBOL,
            interval="240",
            limit=21
        )

        data = klines["result"]["list"]

        h_last = float(data[0][2])
        l_last = float(data[0][3])

        vol_last = (h_last - l_last) / l_last

        ranges = [
            (float(k[2]) - float(k[3])) / float(k[3])
            for k in data[1:]
        ]

        vol_avg = sum(ranges) / len(ranges)

        # modalità difensiva
        if vol_last > (vol_avg * 1.5):

            print("⚠️ Alta volatilità -> mini grid")

            return [2] * 13

        return GRID_SIZES_STANDARD

    except Exception as e:

        print(f"⚠️ Errore volatilità: {e}")

        return GRID_SIZES_STANDARD


def get_bollinger_banda_inf_4h():

    try:

        klines = session.get_kline(
            category="linear",
            symbol=SYMBOL,
            interval="240",
            limit=20
        )

        closes = [
            float(k[4])
            for k in klines["result"]["list"]
        ]

        media = sum(closes) / len(closes)

        std_dev = (
            sum((x - media) ** 2 for x in closes)
            / len(closes)
        ) ** 0.5

        return media - (2 * std_dev)

    except Exception as e:

        print(f"⚠️ Errore Bollinger: {e}")

        return 0.0


def recupera_stato_posizione():

    try:

        response = session.get_positions(
            category="linear",
            symbol=SYMBOL
        )

        positions = response["result"]["list"]

        if len(positions) > 0:

            pos = positions[0]

            size = float(pos.get("size", 0))
            avg_price = float(pos.get("avgPrice", 0))

            return size, avg_price

    except Exception as e:

        print(f"⚠️ Errore posizione: {e}")

    return 0.0, 0.0


def aggiorna_tp_limit_chirurgico(size, tp):

    # cancella vecchi TP
    try:

        ordini = session.get_open_orders(
            category="linear",
            symbol=SYMBOL
        )["result"]["list"]

        for o in ordini:

            if (
                o["side"] == "Sell"
                and o.get("reduceOnly") is True
            ):

                session.cancel_order(
                    category="linear",
                    symbol=SYMBOL,
                    orderId=o["orderId"]
                )

    except Exception as e:

        print(f"⚠️ Errore cancellazione TP: {e}")

    # crea nuovo TP
    try:

        if size > 0:

            session.place_order(
                category="linear",
                symbol=SYMBOL,
                side="Sell",
                orderType="Limit",
                qty=str(size),
                price=str(round(tp, 4)),
                positionIdx=0,
                reduceOnly=True
            )

            print(f"🎯 TP aggiornato -> {round(tp, 4)}")

    except Exception as e:

        print(f"⚠️ Errore nuovo TP: {e}")


# =====================================================================
# VARIABILI GLOBALI
# =====================================================================

ultima_size = -1.0
prezzo_ingresso = 0.0

ultimo_trade_time = 0

# =====================================================================
# AVVIO BOT
# =====================================================================

print("🚀 BOT LIVE AVVIATO")
print("📈 Strategia Grid + Mediazione")
print("🛡️ SL Bollinger 4H + Hard SL -60%")
print(f"⏳ Cooldown attivo: {COOLDOWN_TRADE}s")

# =====================================================================
# LOOP PRINCIPALE
# =====================================================================

while True:

    try:

        # ==============================================================
        # DATI LIVE
        # ==============================================================

        size, avg_price = recupera_stato_posizione()

        ticker = session.get_tickers(
            category="linear",
            symbol=SYMBOL
        )

        prezzo = float(
            ticker["result"]["list"][0]["lastPrice"]
        )

        # ==============================================================
        # STOP LOSS DINAMICO
        # ==============================================================

        if size > 0 and prezzo_ingresso > 0:

            klines = session.get_kline(
                category="linear",
                symbol=SYMBOL,
                interval="240",
                limit=2
            )

            candela_chiusa = klines["result"]["list"][0]

            close_candela = float(candela_chiusa[4])

            low_candela = float(candela_chiusa[3])

            banda_inf = get_bollinger_banda_inf_4h()

            pnl = (prezzo / prezzo_ingresso) - 1

            sl_bollinger = (
                close_candela < banda_inf
                and prezzo <= low_candela
            )

            hard_sl = pnl <= -0.60

            if sl_bollinger or hard_sl:

                print(
                    f"🚨 STOP LOSS -> prezzo {prezzo}"
                )

                session.place_order(
                    category="linear",
                    symbol=SYMBOL,
                    side="Sell",
                    orderType="Market",
                    qty=str(size),
                    positionIdx=0,
                    reduceOnly=True
                )

                ultimo_trade_time = time.time()

                ultima_size = 0
                prezzo_ingresso = 0.0

                time.sleep(2)

                continue

        # ==============================================================
        # POSIZIONE APPENA CHIUSA
        # ==============================================================

        elif size == 0 and ultima_size > 0:

            print("✅ Posizione chiusa")

            ultimo_trade_time = time.time()

            ultima_size = 0

            continue

        # ==============================================================
        # COOLDOWN
        # ==============================================================

        elif size == 0 and ultima_size == 0:

            tempo_passato = (
                time.time() - ultimo_trade_time
            )

            if tempo_passato < COOLDOWN_TRADE:

                attesa = round(
                    COOLDOWN_TRADE - tempo_passato,
                    1
                )

                print(
                    f"⏳ Cooldown attivo -> {attesa}s"
                )

                time.sleep(1)

                continue

            print("🧹 Avvio nuova griglia")

            lista_sizes = get_config_volatilita()

            # cancella ordini residui
            try:

                session.cancel_all_orders(
                    category="linear",
                    symbol=SYMBOL
                )

            except:
                pass

            # ==========================================================
            # ENTRY MARKET
            # ==========================================================

            session.place_order(
                category="linear",
                symbol=SYMBOL,
                side="Buy",
                orderType="Market",
                qty=str(lista_sizes[0]),
                positionIdx=0
            )

            print("🟢 Entry market inviata")

            time.sleep(2)

            s_nuova, p_ing = recupera_stato_posizione()

            if s_nuova > 0:

                prezzo_ingresso = p_ing

                print(
                    f"✅ Entry iniziale @ {p_ing}"
                )

                # ======================================================
                # CREA GRIGLIA
                # ======================================================

                for i in range(1, len(lista_sizes)):

                    prezzo_livello = (
                        p_ing * (1 - (1.2 * i) / 100)
                    )

                    session.place_order(
                        category="linear",
                        symbol=SYMBOL,
                        side="Buy",
                        orderType="Limit",
                        qty=str(lista_sizes[i]),
                        price=str(round(prezzo_livello, 4)),
                        positionIdx=0
                    )

                    print(
                        f"📌 Buy Limit "
                        f"{lista_sizes[i]} @ "
                        f"{round(prezzo_livello, 4)}"
                    )

                # primo TP
                aggiorna_tp_limit_chirurgico(
                    s_nuova,
                    p_ing * 1.007
                )

                ultima_size = s_nuova

        # ==============================================================
        # AGGIORNA TP SE CAMBIA SIZE
        # ==============================================================

        if size > 0 and size != ultima_size:

            nuovo_tp = avg_price * 1.007

            aggiorna_tp_limit_chirurgico(
                size,
                nuovo_tp
            )

            ultima_size = size

            print(
                f"🔄 Size aggiornata -> "
                f"{size} | Avg: {avg_price}"
            )

        # ==============================================================
        # LOOP DELAY
        # ==============================================================

        time.sleep(3)

    except Exception as e:

        print(f"⚠️ Errore generale: {e}")

        time.sleep(10)
