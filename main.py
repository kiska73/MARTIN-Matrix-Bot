import os
import time
from pybit.unified_trading import HTTP

# CONFIGURAZIONE
API_KEY = os.environ.get("BYBIT_API_KEY")
API_SECRET = os.environ.get("BYBIT_API_SECRET")
SYMBOL = "LABUSDT"
TP_LINK_ID = "TP_ORD_MASTER" # Nome univoco
SOGLIA_SL = -0.16 
SIZE_FISSA = 2

session = HTTP(api_key=API_KEY, api_secret=API_SECRET)

def recupera_stato_posizione():
    try:
        response = session.get_positions(category="linear", symbol=SYMBOL)
        pos = response["result"]["list"][0]
        return float(pos["size"]), float(pos["avgPrice"])
    except: return 0.0, 0.0

def aggiorna_tp(size_posizione, quota_tp):
    # Cancella solo il TP precedente
    try:
        ordini = session.get_open_orders(category="linear", symbol=SYMBOL)["result"]["list"]
        for o in ordini:
            if o.get("orderLinkId") == TP_LINK_ID:
                session.cancel_order(category="linear", symbol=SYMBOL, orderId=o["orderId"])
    except: pass
    
    if size_posizione > 0:
        session.place_order(
            category="linear", symbol=SYMBOL, side="Sell",
            orderType="Limit", qty=str(size_posizione),
            price=str(round(quota_tp, 4)),
            orderLinkId=TP_LINK_ID, positionIdx=0, reduceOnly=True
        )

# CICLO
ultima_size = -1.0
prezzo_ingresso_ufficiale = 0.0 # <--- Memorizziamo qui il prezzo fisso

print("🚀 BOT ATTIVO CON SL -16% FORZATO")

while True:
    try:
        size, avg_price = recupera_stato_posizione()
        
        # Se siamo in posizione
        if size > 0:
            # Se è un nuovo ciclo, salva il prezzo di ingresso per lo SL
            if prezzo_ingresso_ufficiale == 0:
                prezzo_ingresso_ufficiale = avg_price
                print(f"✅ SL attivato. Prezzo di riferimento: {prezzo_ingresso_ufficiale}")

            # Controllo SL
            ticker = session.get_tickers(category="linear", symbol=SYMBOL)
            prezzo_att = float(ticker["result"]["list"][0]["lastPrice"])
            pnl_perc = (prezzo_att / prezzo_ingresso_ufficiale) - 1
            
            if pnl_perc <= SOGLIA_SL:
                print(f"🚨 SL RAGGIUNTO! Chiusura Market.")
                session.place_order(category="linear", symbol=SYMBOL, side="Sell", 
                                    orderType="Market", qty=str(size), positionIdx=0, reduceOnly=True)
                prezzo_ingresso_ufficiale = 0 # Reset SL
                time.sleep(10)
                continue

            # Aggiorna TP se la size cambia
            if size != ultima_size:
                aggiorna_tp(size, avg_price * 1.0073)
                ultima_size = size
        
        # Reset ciclo
        elif size == 0:
            prezzo_ingresso_ufficiale = 0 # Reset SL
            ultima_size = -1.0
            # ... (Logica di apertura primo ordine come prima) ...
            
        time.sleep(3)
    except Exception as e:
        print(f"Errore: {e}")
        time.sleep(5)
