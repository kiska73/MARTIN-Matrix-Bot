import os
import time
from pybit.unified_trading import HTTP

# =====================================================================
# CONFIGURAZIONE API CREDENTIALS & SCRIPT (ENVIRONMENT VARIABLES)
# =====================================================================
API_KEY = os.environ.get("BYBIT_API_KEY")
API_SECRET = os.environ.get("BYBIT_API_SECRET")
SYMBOL = "LABUSDT"  

# Connessione protetta ai server Demo di Bybit
session = HTTP(
    testnet=False,
    demo=True,  # Attiva il Demo Trading sul conto principale
    api_key=API_KEY,
    api_secret=API_SECRET
)

# Configurazione Griglia a 13 livelli (Espansa con Jolly finale)
GRID_SIZES = [2, 2, 2, 2, 5, 7, 9, 11, 15, 20, 25, 30, 50] 
TOTAL_EMERGENCY_SIZE = sum(GRID_SIZES) # 180.0 LAB

# =====================================================================
# FUNZIONI DI SUPPORTO PER GESTIONE ACCOUNT & ORDINI
# =====================================================================

def recupera_stato_posizione():
    """Recupera la size attuale e il prezzo medio di carico del Long."""
    try:
        response = session.get_positions(
            category="linear",
            symbol=SYMBOL
        )
        if response and "list" in response["result"] and len(response["result"]["list"]) > 0:
            pos = response["result"]["list"][0]
            size = float(pos.get("size", 0))
            avg_price = float(pos.get("avgPrice", 0))
            return size, avg_price
    except Exception as e:
        print(f"⚠️ Errore lettura posizioni: {e}")
    return 0.0, 0.0

def calcola_volatilta_ratio():
    """
    Simula o calcola il ratio di volatilità corrente.
    Sostituisci questo valore fisso con il tuo indicatore (es. ATR o Order Flow).
    """
    return 0.73

def aggiorna_tp_limit(size_posizione, quota_tp):
    """Cancella i vecchi ordini e piazza il nuovo TP sul book come LIMIT."""
    try:
        # 1. Pulizia preventiva: cancella SOLO gli ordini di vendita (TP) 
        # lasciando intatti gli ordini d'acquisto della griglia sottostante
        session.cancel_all_orders(
            category="linear",
            symbol=SYMBOL
        )
        print("🧹 Vecchio ordine di TP rimosso dal book.")
        
        # 2. Se abbiamo una posizione aperta, piazziamo il TP reale
        if size_posizione > 0:
            session.place_order(
                category="linear",
                symbol=SYMBOL,
                side="Sell",                  # Direzione contraria per chiudere il Long
                orderType="Limit",            # <--- MAKER FEE: Ordine Limit fermo sul book
                qty=str(size_posizione),      # Vende tutta la size accumulata
                price=str(round(quota_tp, 4)),# Prezzo di TP arrotondato
                positionIdx=0,
                reduceOnly=True               # <--- SICUREZZA: Esegue solo se riduce la posizione
            )
            print(f"🎯 [MAKER] Nuovo TP Limit piazzato sul book a quota: {round(quota_tp, 4)} per {size_posizione} LAB")
    except Exception as e:
        print(f"❌ Errore aggiornamento TP Limit: {e}")

def piazza_griglia_acquisto(prezzo_corrente, spaziatura):
    """Piazza i livelli d'acquisto Limit sotto il prezzo corrente (Fisarmonica)."""
    print(f"📐 Configurazione Griglia a Fisarmonica | Spaziatura Corrente: {spaziatura}%")
    prezzo_riferimento = prezzo_corrente
    
    for i, size in enumerate(GRID_SIZES):
        # Ogni livello si allontana in percentuale in base alla spaziatura calcolata
        prezzo_livello = prezzo_riferimento * (1 - (spaziatura * (i + 1)) / 100)
        try:
            session.place_order(
                category="linear",
                symbol=SYMBOL,
                side="Buy",
                orderType="Limit",
                qty=str(size),
                price=str(round(prezzo_livello, 4)),
                positionIdx=0
            )
            print(f"   ↳ Livello {i+1} piazzato: {size} LAB a {round(prezzo_livello, 4)}")
        except Exception as e:
            print(f"   ❌ Impossibile piazzare livello {i+1} (Size: {size}): {e}")

# =====================================================================
# CICLO PRINCIPALE DEL BOT (CORE LOGIC)
# =====================================================================

print("🚀 MASTER BOT PRONTO. Avvio del monitoraggio demo in corso su Bybit...")

# Stato iniziale di tracciamento
ultima_size_tracciata = -1.0 

while True:
    try:
        # 1. Monitoraggio costante della posizione reale
        size_attuale, prezzo_medio = recupera_stato_posizione()
        ratio_volatilità = calcola_volatilta_ratio()
        
        # 2. Rilevamento Cambio Stato (Inseguimento o Reset)
        if size_attuale != ultima_size_tracciata:
            print(f"\n🔄 Cambio size rilevato sul mercato: {ultima_size_tracciata} LAB ➔ {size_attuale} LAB")
            
            if size_attuale > 0:
                # LA GRIGLIA HA ACCUMULATO (o è partito il primo livello)
                # Calcola il TP adattandosi al nuovo prezzo medio di carico
                nuovo_target_tp = prezzo_medio * (1 + ratio_volatilità / 100)
                
                print(f"📊 [Posizione Attiva] Size: {size_attuale} LAB | Media Carico: {prezzo_medio}")
                print(f"🧮 Ricalcolo Target TP: {prezzo_medio} + {ratio_volatilità}% = {round(nuovo_target_tp, 4)}")
                
                # Aggiorna istantaneamente il book di Bybit con il TP Maker
                aggiorna_tp_limit(size_attuale, nuovo_target_tp)
                
            else:
                # LA POSIZIONE È STATA AZZERATA (Il TP Limit è stato preso!)
                if ultima_size_tracciata > 0:
                    print("🎉 TARGET PRESO! Il TP Limit è stato eseguito come Maker. Ciclo chiuso in profitto.")
                
                print("🧹 Tabula rasa sul book. Reset degli ordini rimasti...")
                try:
                    session.cancel_all_orders(category="linear", symbol=SYMBOL)
                except:
                    pass
                
                # Recupera l'ultimo prezzo per stampare la nuova griglia di partenza
                ticker = session.get_tickers(category="linear", symbol=SYMBOL)
                prezzo_spot = float(ticker["result"]["list"][0]["lastPrice"])
                
                # Rigenera la rete a fisarmonica
                piazza_griglia_acquisto(prezzo_spot, ratio_volatilità)
            
            # Memorizza lo stato corrente per il prossimo controllo
            ultima_size_tracciata = size_attuale
            
        else:
            # Nessun movimento di size, stampa un log di controllo statico ogni ciclo
            if size_attuale > 0:
                target_corrente = prezzo_medio * (1 + ratio_volatilità / 100)
                print(f"📊 [In ascolto...] Posizione: {size_attuale} LAB | Media: {prezzo_medio} | Target TP: {round(target_corrente, 4)} | Volatilità Ratio: {ratio_volatilità}", end="\r")
            else:
                print("💤 In attesa che venga agganciato il primo livello della griglia...", end="\r")

    except Exception as e:
        print(f"\n⚠️ Errore nel ciclo principale: {e}")
        
    # Ritardo di sicurezza per evitare il superamento dei limiti di chiamata (Rate Limit)
    time.sleep(3)
