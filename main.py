import os
import time
from pybit.unified_trading import HTTP

# =====================================================================
# CONFIGURAZIONE
# =====================================================================
API_KEY = os.environ.get("BYBIT_API_KEY")
API_SECRET = os.environ.get("BYBIT_API_SECRET")
SYMBOL = "LABUSDT"

session = HTTP(testnet=False, demo=False, api_key=API_KEY, api_secret=API_SECRET)

GRID_SIZES_STANDARD = [2, 2, 2, 2, 5, 7, 9, 11, 15, 20, 25, 30, 50]

# =====================================================================
# LOGICA VOLATILITA E INDICATORI
# =====================================================================

def get_config_volatilita():
    """Confronta ultima candela 4H con le 20 precedenti."""
    try:
        klines = session.get_kline(category="linear", symbol=SYMBOL, interval="240", limit=21)
        data = klines["result"]["list"]
        
        # Volatilità ultima candela
        h_last, l_last = float(data[0][2]), float(data[0][3])
        vol_last = (h_last - l_last) / l_last
        
        # Volatilità media 20 precedenti
        ranges = [(float(k[2]) - float(k[3])) / float(k[3]) for k in data[1:]]
        vol_avg = sum(ranges) / len(ranges)
        
        # Se ultima candela è 1.5x più volatile della media -> Alta Vol
        return [2] * 13 if vol_last > (vol_avg * 1.5) else GRID_SIZES_STANDARD
    except: return GRID_SIZES_STANDARD

def get_bollinger_banda_inf_4h():
    """Calcola Banda Inferiore Bollinger 4H."""
    try:
        klines = session.get_kline(category="linear", symbol=SYMBOL, interval="240", limit=20)
        closes = [float(k[4]) for k in klines["result"]["list"]]
        media = sum(closes) / len(closes)
        std_dev = (sum([(x - media)**2 for x in closes]) / len(closes))**0.5
        return media - (2 * std_dev)
    except: return 0.0

def recupera_stato_posizione():
    try:
        response = session.get_positions(category="linear", symbol=SYMBOL)
        if response and "list" in response["result"] and len(response["result"]["list"]) > 0:
            pos = response["result"]["list"][0]
            return float(pos.get("size", 0)), float(pos.get("avgPrice", 0))
    except: pass
    return 0.0, 0.0

def aggiorna_tp_limit_chirurgico(size, tp):
    try:
        ordini = session.get_open_orders(category="linear", symbol=SYMBOL)["result"]["list"]
        for o in ordini:
            if o["side"] == "Sell": session.cancel_order(category="linear", symbol=SYMBOL, orderId=o["orderId"])
    except: pass
    if size > 0:
        session.place_order(category="linear", symbol=SYMBOL, side="Sell", orderType="Limit", 
                            qty=str(size), price=str(round(tp, 4)), positionIdx=0, reduceOnly=True)

# =====================================================================
# CICLO PRINCIPALE
# =====================================================================

ultima_size = -1.0
prezzo_ingresso = 0.0

print("🚀 BOT AVVIATO: Bollinger Breakout + Volatilità 4H + Paracadute 50%.")

while True:
    try:
        size, avg_price = recupera_stato_posizione()
        ticker = session.get_tickers(category="linear", symbol=SYMBOL)
        prezzo = float(ticker["result"]["list"][0]["lastPrice"])
        
        # 1. SL DINAMICO (Bollinger + Paracadute 50%)
        if size > 0 and prezzo_ingresso > 0:
            banda_inf = get_bollinger_banda_inf_4h()
            pnl = (prezzo / prezzo_ingresso) - 1
            if prezzo < banda_inf or pnl <= -0.50:
                print(f"🚨 SL DINAMICO INNESCATO (Prezzo: {prezzo} < Banda: {round(banda_inf, 4)} o PnL: {round(pnl, 2)})")
                session.place_order(category="linear", symbol=SYMBOL, side="Sell", orderType="Market", qty=str(size), positionIdx=0, reduceOnly=True)
                ultima_size = -1.0
                prezzo_ingresso = 0.0
                continue

        # 2. RESET E PIAZZAMENTO
        elif size == 0 and ultima_size != 0:
            print("🧹 Analisi 4H in corso...")
            lista_sizes = get_config_volatilita()
            
            try: session.cancel_all_orders(category="linear", symbol=SYMBOL)
            except: pass
            
            session.place_order(category="linear", symbol=SYMBOL, side="Buy", orderType="Market", qty=str(lista_sizes[0]), positionIdx=0)
            time.sleep(2)
            
            s_nuova, p_ing = recupera_stato_posizione()
            if s_nuova > 0:
                prezzo_ingresso = p_ing
                print(f"✅ Primo ordine @ {p_ing}. Griglia operativa.")
                for i in range(1, len(lista_sizes)):
                    prezzo_livello = p_ing * (1 - (1.0 * i) / 100)
                    session.place_order(category="linear", symbol=SYMBOL, side="Buy", orderType="Limit", qty=str(lista_sizes[i]), price=str(round(prezzo_livello, 4)), positionIdx=0)
                aggiorna_tp_limit_chirurgico(s_nuova, p_ing * 1.006)
                ultima_size = s_nuova

        # 3. Aggiorna TP
        if size > 0 and size != ultima_size:
            aggiorna_tp_limit_chirurgico(size, avg_price * 1.006)
            ultima_size = size

        time.sleep(3)
    except Exception as e:
        print(f"⚠️ Errore: {e}")
        time.sleep(10)
