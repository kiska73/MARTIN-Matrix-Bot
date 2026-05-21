import os
import time
from pybit.unified_trading import HTTP

# =====================================================================
# CONFIGURAZIONE
# =====================================================================
API_KEY = os.environ.get("BYBIT_API_KEY")
API_SECRET = os.environ.get("BYBIT_API_SECRET")
SYMBOL = "LABUSDT"
TP_LINK_ID = "TP_ORDER_MASTER_BOT" # Etichetta univoca per il TP

session = HTTP(
    testnet=False,
    demo=True,
    api_key=API_KEY,
    api_secret=API_SECRET
)

GRID_SIZES = [2, 2, 2, 2, 5, 7, 9, 11, 15, 20, 25, 30, 50] 
SIZE_LIVELLO_1 = GRID_SIZES[0]
RESTANTI_LIVELLI = GRID_SIZES[1:]

# =====================================================================
# FUNZIONI
# =====================================================================

def recupera_stato_posizione():
    try:
        response = session.get_positions(category="linear", symbol=SYMBOL)
        if response and "list" in response["result"] and len(response["result"]["list"]) > 0:
            pos = response["result"]["list"][0]
            return float(pos.get("size", 0)), float(pos.get("avgPrice", 0))
    except Exception as e:
        print(f"⚠️ Errore lettura: {e}")
    return 0.0, 0.0

def aggiorna_tp_limit(size_posizione, quota_tp):
    """Cancella solo il TP tramite ID e ne piazza uno nuovo."""
    try:
        # Cancella SOLO il TP, non la griglia!
        session.cancel_order(category="linear", symbol=SYMBOL, orderLinkId=TP_LINK_ID)
    except:
        pass 
        
    if size_posizione > 0:
        session.place_order(
            category="linear", symbol=SYMBOL, side="Sell",
            orderType="Limit", qty=str(size_posizione),
            price=str(round(quota_tp, 4)),
            orderLinkId=TP_LINK_ID, # Etichetta fondamentale
            positionIdx=0, reduceOnly=True
        )
        print(f"🎯 [MAKER] TP Limit aggiornato a: {round(quota_tp, 4)}")

def piazza_restante_griglia_limit(prezzo_riferimento, spaziatura):
    for i, size in enumerate(RESTANTI_LIVELLI):
        prezzo_livello = prezzo_riferimento * (1 - (spaziatura * (i + 1)) / 100)
        session.place_order(
            category="linear", symbol=SYMBOL, side="Buy",
            orderType="Limit", qty=str(size),
            price=str(round(prezzo_livello, 4)),
            positionIdx=0
        )

# =====================================================================
# CICLO PRINCIPALE
# =====================================================================

ultima_size_tracciata = -1.0 
ratio_volatilità = 0.73

print("🚀 MASTER BOT PRONTO.")

while True:
    try:
        size_attuale, prezzo_medio = recupera_stato_posizione()
        
        if size_attuale != ultima_size_tracciata:
            if size_attuale > 0:
                # La posizione è attiva, aggiorniamo il TP (Maker)
                nuovo_tp = prezzo_medio * (1 + ratio_volatilità / 100)
                aggiorna_tp_limit(size_attuale, nuovo_tp)
                ultima_size_tracciata = size_attuale
                
            else:
                # Posizione zero: avvio ciclo o TP eseguito
                print("🧹 Reset ciclo...")
                try: session.cancel_all_orders(category="linear", symbol=SYMBOL)
                except: pass
                
                # Entrata a mercato
                session.place_order(category="linear", symbol=SYMBOL, side="Buy", 
                                    orderType="Market", qty=str(SIZE_LIVELLO_1), positionIdx=0)
                
                time.sleep(3) # Attesa allineamento
                s_nuova, p_ingresso = recupera_stato_posizione()
                
                if s_nuova > 0:
                    piazza_restante_griglia_limit(p_ingresso, ratio_volatilità)
                    ultima_size_tracciata = s_nuova
                    continue 

        time.sleep(3)
    except Exception as e:
        print(f"⚠️ Errore: {e}")
        time.sleep(5)
