import os
import time
from pybit.unified_trading import HTTP

# =====================================================================
# CONFIGURAZIONE
# =====================================================================
API_KEY = os.environ.get("BYBIT_API_KEY")
API_SECRET = os.environ.get("BYBIT_API_SECRET")
SYMBOL = "LABUSDT"
TP_LINK_ID = "TP_ORD_MASTER" 
SOGLIA_SL = -0.16 
SIZE_FISSA = 2     
NUMERO_LIVELLI_GRIGLIA = 13
RATIO_VOLATILITA = 0.73

session = HTTP(api_key=API_KEY, api_secret=API_SECRET)

# =====================================================================
# FUNZIONI DI SUPPORTO
# =====================================================================

def recupera_stato_posizione():
    try:
        response = session.get_positions(category="linear", symbol=SYMBOL)
        pos = response["result"]["list"][0]
        return float(pos["size"]), float(pos["avgPrice"])
    except: return 0.0, 0.0

def aggiorna_tp(size_posizione, quota_tp):
    # Pulisce vecchi ordini TP
    try:
        ordini = session.get_open_orders(category="linear", symbol=SYMBOL)["result"]["list"]
        for o in ordini:
            if o.get("orderLinkId") == TP_LINK_ID:
                session.cancel_order(category="linear", symbol=SYMBOL, orderId=o["orderId"])
                time.sleep(0.2)
    except: pass
    
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

ultima_size = -1.0
prezzo_ingresso_ufficiale = 0.0

print("🚀 BOT AVVIATO: Sincronizzazione in corso...")
# Sincronizzazione iniziale
s_init, p_init = recupera_stato_posizione()
if s_init > 0:
    prezzo_ingresso_ufficiale = p_init
    ultima_size = s_init
    print(f"✅ Sincronizzato! Posizione attiva: {s_init} LAB @ {p_init}")

while True:
    try:
        size, avg_price = recupera_stato_posizione()
        
        # --- LOGICA DI MONITORAGGIO ---
        if size > 0:
            if prezzo_ingresso_ufficiale == 0: prezzo_ingresso_ufficiale = avg_price
            
            ticker = session.get_tickers(category="linear", symbol=SYMBOL)
            prezzo_att = float(ticker["result"]["list"][0]["lastPrice"])
            pnl_perc = (prezzo_att / prezzo_ingresso_ufficiale) - 1
            
            # Controllo SL
            if pnl_perc <= SOGLIA_SL:
                print(f"🚨 SL RAGGIUNTO ({pnl_perc:.2%})! Chiusura Market.")
                session.place_order(category="linear", symbol=SYMBOL, side="Sell", 
                                    orderType="Market", qty=str(size), positionIdx=0, reduceOnly=True)
                prezzo_ingresso_ufficiale = 0
                ultima_size = -1.0
                time.sleep(10)
                continue

            # Aggiorna TP se la size cambia
            if size != ultima_size:
                aggiorna_tp(size, avg_price * (1 + RATIO_VOLATILITA/100))
                ultima_size = size
        
        # --- LOGICA DI RIPARTENZA ---
        elif size == 0:
            prezzo_ingresso_ufficiale = 0
            ultima_size = -1.0
            print("🧹 Reset ciclo: piazzamento griglia...")
            try: session.cancel_all_orders(category="linear", symbol=SYMBOL)
            except: pass
            
            session.place_order(category="linear", symbol=SYMBOL, side="Buy", 
                                orderType="Market", qty=str(SIZE_FISSA), positionIdx=0)
            time.sleep(3)
            
            # Recupera prezzo per piazzare la griglia
            _, p_ingresso = recupera_stato_posizione()
            if p_ingresso > 0:
                prezzo_ingresso_ufficiale = p_ingresso
                for i in range(1, NUMERO_LIVELLI_GRIGLIA):
                    prezzo_liv = p_ingresso * (1 - (RATIO_VOLATILITA * i) / 100)
                    session.place_order(category="linear", symbol=SYMBOL, side="Buy", 
                                        orderType="Limit", qty=str(SIZE_FISSA), price=str(round(prezzo_liv, 4)), positionIdx=0)
                aggiorna_tp(SIZE_FISSA, p_ingresso * (1 + RATIO_VOLATILITA/100))

        time.sleep(3)
    except Exception as e:
        print(f"⚠️ Errore: {e}")
        time.sleep(5)
