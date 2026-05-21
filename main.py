import os
import time
from pybit.unified_trading import HTTP

# =====================================================================
# CONFIGURAZIONE
# =====================================================================
API_KEY = os.environ.get("BYBIT_API_KEY")
API_SECRET = os.environ.get("BYBIT_API_SECRET")
SYMBOL = "LABUSDT"
TP_LINK_ID = "TP_ORDER_MASTER"
SOGLIA_SL = -0.16  # Stop Loss fisso a -16%
SIZE_FISSA = 2     # Size fissa per ogni livello della griglia

session = HTTP(
    testnet=False,
    demo=True,
    api_key=API_KEY,
    api_secret=API_SECRET
)

NUMERO_LIVELLI_GRIGLIA = 13
ratio_volatilità = 0.73

# =====================================================================
# FUNZIONI
# =====================================================================

def recupera_stato_posizione():
    try:
        response = session.get_positions(category="linear", symbol=SYMBOL)
        if response and "list" in response["result"] and len(response["result"]["list"]) > 0:
            pos = response["result"]["list"][0]
            # Ritorniamo size e prezzo medio
            return float(pos.get("size", 0)), float(pos.get("avgPrice", 0))
    except Exception as e:
        print(f"Errore recupero posizione: {e}")
    return 0.0, 0.0

def aggiorna_tp_limit_chirurgico(size_posizione, quota_tp):
    """Cancella solo il TP esistente e ne piazza uno nuovo."""
    try:
        ordini = session.get_open_orders(category="linear", symbol=SYMBOL)["result"]["list"]
        for o in ordini:
            if o.get("orderLinkId") == TP_LINK_ID:
                session.cancel_order(category="linear", symbol=SYMBOL, orderId=o["orderId"])
    except Exception as e:
        print(f"Errore cancellazione TP: {e}")
        
    if size_posizione > 0:
        session.place_order(
            category="linear", symbol=SYMBOL, side="Sell",
            orderType="Limit", qty=str(size_posizione),
            price=str(round(quota_tp, 4)),
            orderLinkId=TP_LINK_ID, positionIdx=0, reduceOnly=True
        )

# =====================================================================
# CICLO PRINCIPALE
# =====================================================================

ultima_size_tracciata = -1.0 
print("🚀 BOT ATTIVO: Size Fissa 2 LAB | Protezione SL -16% integrata.")

while True:
    try:
        size_attuale, prezzo_medio = recupera_stato_posizione()
        
        # --- LOGICA DI PROTEZIONE E GESTIONE POSIZIONE ---
        if size_attuale > 0:
            # 1. Controllo Stop Loss fisso
            ticker = session.get_tickers(category="linear", symbol=SYMBOL)
            prezzo_attuale = float(ticker["result"]["list"][0]["lastPrice"])
            pnl_perc = (prezzo_attuale / prezzo_medio) - 1
            
            if pnl_perc <= SOGLIA_SL:
                print(f"🚨 STOP LOSS RAGGIUNTO ({pnl_perc:.2%})! Chiusura Market.")
                session.place_order(category="linear", symbol=SYMBOL, side="Sell", 
                                    orderType="Market", qty=str(size_attuale), positionIdx=0, reduceOnly=True)
                time.sleep(10) # Pausa di sicurezza
                ultima_size_tracciata = -1.0
                continue

            # 2. Aggiornamento dinamico TP se la size cambia
            if size_attuale != ultima_size_tracciata:
                nuovo_tp = prezzo_medio * (1 + ratio_volatilità / 100)
                aggiorna_tp_limit_chirurgico(size_attuale, nuovo_tp)
                ultima_size_tracciata = size_attuale
            
        # --- LOGICA DI RESET E RIPARTENZA ---
        elif size_attuale == 0 and ultima_size_tracciata != 0:
            print("🧹 Reset ciclo: piazzamento griglia...")
            try: session.cancel_all_orders(category="linear", symbol=SYMBOL)
            except: pass
            
            # Apertura primo ordine
            session.place_order(category="linear", symbol=SYMBOL, side="Buy", 
                                orderType="Market", qty=str(SIZE_FISSA), positionIdx=0)
            time.sleep(3)
            
            # Lettura stato dopo apertura
            s_nuova, p_ingresso = recupera_stato_posizione()
            
            if s_nuova > 0:
                ultima_size_tracciata = s_nuova
                # Piazza griglia di acquisto
                for i in range(1, NUMERO_LIVELLI_GRIGLIA):
                    prezzo_livello = p_ingresso * (1 - (ratio_volatilità * i) / 100)
                    session.place_order(category="linear", symbol=SYMBOL, side="Buy", 
                                        orderType="Limit", qty=str(SIZE_FISSA), price=str(round(prezzo_livello, 4)), positionIdx=0)
                
                # Piazza TP iniziale
                aggiorna_tp_limit_chirurgico(s_nuova, p_ingresso * (1 + ratio_volatilità / 100))
                print(f"✅ Griglia ripartita con SL monitorato.")

        time.sleep(3)
    except Exception as e:
        print(f"⚠️ Errore nel ciclo: {e}")
        time.sleep(5)
