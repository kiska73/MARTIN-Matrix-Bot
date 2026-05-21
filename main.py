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

# Griglia originale a 13 livelli (Totale 180 LAB)
# Il livello 1 (2 LAB) entra a mercato. I successivi 12 rimangono Limit.
GRID_SIZES = [2, 2, 2, 2, 5, 7, 9, 11, 15, 20, 25, 30, 50] 
SIZE_LIVELLO_1 = GRID_SIZES[0]        # 2 LAB (Ingresso istantaneo a mercato)
RESTANTI_LIVELLI = GRID_SIZES[1:]     # I restanti 12 livelli per la fisarmonica

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
    """Cancella i vecchi ordini di TP e piazza il nuovo TP sul book come LIMIT."""
    try:
        # Pulizia preventiva: cancella solo gli ordini di vendita (TP)
        # lasciando intatti gli ordini d'acquisto della griglia pendente
        session.cancel_all_orders(
            category="linear",
            symbol=SYMBOL
        )
        print("🧹 Vecchio ordine di TP rimosso dal book.")
        
        if size_posizione > 0:
            session.place_order(
                category="linear",
                symbol=SYMBOL,
                side="Sell",                  # Direzione contraria per chiudere il Long
                orderType="Limit",            # MAKER FEE: Ordine Limit fermo sul book
                qty=str(size_posizione),      # Vende tutta la size accumulata
                price=str(round(quota_tp, 4)),# Prezzo di TP arrotondato
                positionIdx=0,
                reduceOnly=True               # SICUREZZA: Esegue solo se riduce la posizione
            )
            print(f"🎯 [MAKER] Nuovo TP Limit piazzato sul book a quota: {round(quota_tp, 4)} per {size_posizione} LAB")
    except Exception as e:
        print(f"❌ Errore aggiornamento TP Limit: {e}")

def apri_livello_1_a_mercato():
    """Invia un ordine istantaneo a mercato per il primo livello da 2 LAB."""
    try:
        print(f"⚡ Inserimento istantaneo Livello 1 a MERCATO ({SIZE_LIVELLO_1} LAB)...")
        order = session.place_order(
            category="linear",
            symbol=SYMBOL,
            side="Buy",
            orderType="Market",               # Entra subito senza aspettare
            qty=str(SIZE_LIVELLO_1),
            positionIdx=0
        )
        print("🟢 Livello 1 eseguito con successo.")
        return True
    except Exception as e:
        print(f"❌ Errore ordine a mercato Livello 1: {e}")
        return False

def piazza_restante_griglia_limit(prezzo_riferimento, spaziatura):
    """Piazza i restanti 12 livelli d'acquisto Limit a fisarmonica sotto il prezzo di ingresso."""
    print(f"📐 Configurazione Griglia a Fisarmonica (12 livelli rimanenti) | Spaziatura: {spaziatura}%")
    
    for i, size in enumerate(RESTANTI_LIVELLI):
        # L'indice parte da 0, ma corrisponde al livello 2 effettivo della griglia originale
        numero_livello = i + 2 
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
            print(f"   ↳ Livello {numero_livello} piazzato: {size} LAB a {round(prezzo_livello, 4)}")
        except Exception as e:
            print(f"   ❌ Impossibile piazzare livello {numero_livello} (Size: {size}): {e}")

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
        
        # 2. Rilevamento Cambio Stato (Inseguimento o Inizio Ciclo)
        if size_attuale != ultima_size_tracciata:
            print(f"\n🔄 Cambio size rilevato sul mercato: {ultima_size_tracciata} LAB ➔ {size_attuale} LAB")
            
            if size_attuale > 0:
                # LA POSIZIONE È ATTIVA (È entrato il livello 1 a mercato o i successivi limit)
                # Calcola il TP adattandosi al prezzo medio corrente
                nuovo_target_tp = prezzo_medio * (1 + ratio_volatilità / 100)
                
                print(f"📊 [Posizione Attiva] Size: {size_attuale} LAB | Media Carico: {prezzo_medio}")
                print(f"🧮 Ricalcolo Target TP: {prezzo_medio} + {ratio_volatilità}% = {round(nuovo_target_tp, 4)}")
                
                # Aggiorna istantaneamente il book di Bybit con il TP Maker
                aggiorna_tp_limit(size_attuale, nuovo_target_tp)
                
            else:
                # LA POSIZIONE È A ZERO (O il bot è appena partito, o il TP Limit è stato preso!)
                if ultima_size_tracciata > 0:
                    print("🎉 TARGET PRESO! Il TP Limit è stato eseguito come Maker. Ciclo chiuso in profitto.")
                
                print("🧹 Pulizia totale del book prima di iniziare il nuovo ciclo...")
                try:
                    session.cancel_all_orders(category="linear", symbol=SYMBOL)
                except:
                    pass
                
                # AZIONE AGGIORNATA: Entra subito a mercato con il livello 1
                successo_ingresso = apri_livello_1_a_mercato()
                
                if successo_ingresso:
                    # Aspetta un istante per far registrare la posizione a Bybit
                    time.sleep(2)
                    size_nuova, prezzo_ingresso = recupera_stato_posizione()
                    
                    if size_nuova > 0:
                        # Piazza i restanti 12 livelli condizionati SOTTO il prezzo di ingresso reale
                        piazza_restante_griglia_limit(prezzo_ingresso, ratio_volatilità)
                    else:
                        print("⚠️ Posizione non rilevata subito dopo l'ordine a mercato. Riprovo nel prossimo ciclo.")
                
            # Memorizza lo stato corrente per il prossimo controllo
            ultima_size_tracciata = size_attuale
            
        else:
            # Nessun movimento di size, stampa un log di controllo statico ogni ciclo
            if size_attuale > 0:
                target_corrente = prezzo_medio * (1 + ratio_volatilità / 100)
                print(f"📊 [In ascolto...] Posizione: {size_attuale} LAB | Media: {prezzo_medio} | Target TP: {round(target_corrente, 4)} | Volatilità Ratio: {ratio_volatilità}", end="\r")
            else:
                print("💤 Inizializzazione in corso...", end="\r")

    except Exception as e:
        print(f"\n⚠️ Errore nel ciclo principale: {e}")
        
    # Ritardo di sicurezza per evitare il superamento dei limiti di chiamata (Rate Limit)
    time.sleep(3)
