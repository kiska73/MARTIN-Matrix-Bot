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

# Griglia ottimizzata (più leggera per il margine)
GRID_SIZES_STANDARD = [1, 1, 1, 2, 3, 5, 7, 9, 11, 15, 20, 25, 30]

# =====================================================================
# FUNZIONI DI SUPPORTO
# =====================================================================

def get_config_volatilita():
    try:
        klines = session.get_kline(category="linear", symbol=SYMBOL, interval="240", limit=21)
        data = klines["result"]["list"]
        h_last, l_last = float(data[0][2]), float(data[0][3])
        vol_last = (h_last - l_last) / l_last
        ranges = [(float(k[2]) - float(k[3])) / float(k[3]) for k in data[1:]]
        vol_avg = sum(ranges) / len(ranges)
        return [2] * 13 if vol_last > (vol_avg * 1.5) else GRID_SIZES_STANDARD
    except: return GRID_SIZES_STANDARD

def get_bollinger_banda_inf_4h():
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

print("🚀 BOT LIVE AVVIATO: Bollinger SL su Minimo 4H + Volatilità + Paracadute 60% + Pausa 10s.")

while True:
    try:
        size, avg_price = recupera_stato_posizione()
        ticker = session.get_tickers(category="linear", symbol=SYMBOL)
        prezzo = float(ticker["result"]["list"][0]["lastPrice"])
        
        # 1. GESTIONE POSIZIONE APERTA
        if size > 0 and prezzo_ingresso > 0:
            # Analisi per SL su candela chiusa
            klines = session.get_kline(category="linear", symbol=SYMBOL, interval="240", limit=2)
            candela_chiusa = klines["result"]["list"][1]
            close_candela = float(candela_chiusa[4])
            low_candela = float(candela_chiusa[3])
            banda_inf = get_bollinger_banda_inf_4h()
            pnl = (prezzo / prezzo_ingresso) - 1
            
            # SL su minimo se chiude sotto banda O Paracadute estremo
            if (close_candela < banda_inf and prezzo <= low_candela) or pnl <= -0.60:
                print(f"🚨 SL INNESCATO (Prezzo {prezzo} rotto minimo {low_candela})")
                session.place_order(category="linear", symbol=SYMBOL, side="Sell", orderType="Market", qty=str(size), positionIdx=0, reduceOnly=True)
                
                print("⏳ Trade chiuso. Pausa tattica di 10 secondi...")
                time.sleep(10)
                
                ultima_size = -1.0
                prezzo_ingresso = 0.0
                continue

        # 2. RESET E PIAZZAMENTO GRIGLIA
        elif size == 0 and ultima_size != 0:
            # Se la size è diventata 0, significa che siamo appena usciti (TP o SL)
            # La pausa avviene solo se prima avevamo una posizione attiva
            if ultima_size > 0:
                print("🏁 Posizione chiusa. Pausa di 10 secondi...")
                time.sleep(10)
            
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
                    prezzo_livello = p_ing * (1 - (1.2 * i) / 100)
                    session.place_order(category="linear", symbol=SYMBOL, side="Buy", orderType="Limit", qty=str(lista_sizes[i]), price=str(round(prezzo_livello, 4)), positionIdx=0)
                aggiorna_tp_limit_chirurgico(s_nuova, p_ing * 1.007)
                ultima_size = s_nuova

        # 3. Aggiorna TP chirurgico
        if size > 0 and size != ultima_size:
            aggiorna_tp_limit_chirurgico(size, avg_price * 1.007)
            ultima_size = size

        time.sleep(3)
    except Exception as e:
        print(f"⚠️ Errore: {e}")
        time.sleep(10)
