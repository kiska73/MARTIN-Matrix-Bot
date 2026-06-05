import os
import time
import pandas as pd
from pybit.unified_trading import HTTP

# ==============================================================================
# CONFIGURAZIONE OPERATIVA - QUANTITÀ FISSE (UAI)
# ==============================================================================
SYMBOL = "UAIUSDT"
BASE_QTY = 70  # <<--- LA QUANTITÀ LA DECIDI TU QUI (Pezzi del 1° livello)

# 8 Livelli: il bot moltiplicherà la tua BASE_QTY per questi coefficienti
GRID_MULTIPLIERS = [1, 1, 1, 1.5, 2, 2, 3, 4.5] 

# Calibri degli spaziatori per arrivare precisi al 12% di calo cumulativo
GRID_SPACING = [0.0, 1.0, 1.0, 1.2, 1.5, 2.0, 2.5, 2.8]

# Target profit fisso della griglia (es. 0.90% sul prezzo medio ponderato)
TAKE_PROFIT_PERCENT = 0.90 

# Distanza percentuale dello Stop Loss Fisso dal prezzo di partenza dell'L1
STOP_LOSS_PERCENT = 15.5

COOLDOWN = 30  # Secondi di pausa dopo la chiusura di una griglia

# ==============================================================================
# DECIMALI STRUMENTO
# ==============================================================================
PRICE_DECIMALS = 5
QTY_DECIMALS = 0 

# ==============================================================================
# VARIABILI DI STATO (TRACKING AUTOMATICO)
# ==============================================================================
last_trade_time = 0
last_tp_price = 0.0
last_tp_update_time = 0
prezzo_inizio_griglia = 0.0 

# Connessione alle API di Bybit
session = HTTP(
    testnet=False, 
    api_key=os.environ.get("BYBIT_API_KEY"), 
    api_secret=os.environ.get("BYBIT_API_SECRET")
)

# ==============================================================================
# FUNZIONI UTILITARIE
# ==============================================================================
def round_price(price):
    return round(price, PRICE_DECIMALS)

def round_qty(qty):
    if QTY_DECIMALS == 0:
        return int(round(qty))
    return round(qty, QTY_DECIMALS)

def cancel_all_orders():
    try:
        # Cancella sia gli ordini LIMIT (Griglia e TP) sia i condizionali (SL)
        session.cancel_all_orders(category="linear", symbol=SYMBOL)
        time.sleep(0.5)
        print(" [SISTEMA] Tutti gli ordini (Limit e SL condizionali) cancellati")
        return True
    except Exception as e:
        print(f" Errore cancel all: {e}")
        return False

def close_position():
    try:
        pos = session.get_positions(category="linear", symbol=SYMBOL)["result"]["list"][0]
        size = float(pos.get("size", 0))
        if size == 0:
            return False
        
        pos_side = pos.get("side", "Buy")
        side = "Sell" if pos_side == "Buy" else "Buy"
        
        session.place_order(
            category="linear", symbol=SYMBOL, side=side, orderType="Market", 
            qty=str(abs(size)), reduceOnly=True
        )
        print(f" 💥 POSIZIONE CHIUSA A MERCATO | Size: {size} UAI")
        time.sleep(1.0)
        return True
    except Exception as e:
        print(f" Errore chiusura posizione: {e}")
        return False

def get_current_price():
    try:
        ticker = session.get_tickers(category="linear", symbol=SYMBOL)
        return float(ticker['result']['list'][0]['lastPrice'])
    except:
        return None

# ==============================================================================
# AVVIO BOT E CICLO CONTINUO
# ==============================================================================
print(" 🤖 BOT GRID LEVA 1 (v8.3 - Fix Trigger Direction & Qty)")
print(f" Strumento: {SYMBOL} | Quantità Base (L1): {BASE_QTY} UAI | Livelli: 8")
print(f" Copertura griglia: -12.0% | Stop Loss Fisso (Nativo): -{STOP_LOSS_PERCENT}%\n")

# Calcolo preventivo esatto della dimensione massima teorica della griglia
MAX_TOTAL_QTY = round_qty(sum([BASE_QTY * m for m in GRID_MULTIPLIERS]))

while True:
    try:
        now = time.time()
        price = get_current_price()
        
        # Lettura dello stato reale della posizione su Bybit
        pos_data = session.get_positions(category="linear", symbol=SYMBOL)["result"]["list"][0]
        pos_side = pos_data.get("side", "None")
        raw_size = float(pos_data["size"])

        # Riconosce solo se siamo effettivamente in LONG
        size = raw_size if (pos_side == "Buy" and raw_size > 0) else 0.0
        avg_price = float(pos_data.get("avgPrice", 0))
        
        active_orders = session.get_open_orders(category="linear", symbol=SYMBOL)["result"]["list"]

        # Se non abbiamo posizioni aperte, puliamo le variabili di riferimento
        if size == 0:
            last_tp_price = 0.0
            prezzo_inizio_griglia = 0.0

        # ==================== GESTIONE TARGET PROFIT (TP) ====================
        if size > 0:
            target_tp = round_price(avg_price * (1 + TAKE_PROFIT_PERCENT / 100))

            # Chiusura immediata a mercato se il prezzo supera direttamente il TP target
            if price and price >= target_tp:
                print(f" 🎯 Target raggiunto a mercato! Prezzo ({price}) >= TP ({target_tp}). Chiusura griglia.")
                cancel_all_orders()
                close_position()
                last_trade_time = now  
                last_tp_price = 0.0
                prezzo_inizio_griglia = 0.0
            
            # Aggiornamento ordine limite di TP (Non tocca lo Stop Loss)
            elif (abs(target_tp - last_tp_price) > (10 ** -PRICE_DECIMALS)) and (now - last_tp_update_time > 10):
                # Filtra solo l'ordine di TP (Limit, Sell, ReduceOnly) senza toccare i Condizionali
                tp_orders = [o for o in active_orders if o.get("side") == "Sell" and o.get("orderType") == "Limit" and o.get("reduceOnly") is True]

                update_needed = False
                if not tp_orders:
                    update_needed = True
                else:
                    current_tp = float(tp_orders[0]["price"])
                    if abs(current_tp - target_tp) > (10 ** -PRICE_DECIMALS):
                        update_needed = True
                        try:
                            session.cancel_order(category="linear", symbol=SYMBOL, orderId=tp_orders[0]["orderId"])
                        except:
                            pass

                if update_needed:
                    try:
                        session.place_order(
                            category="linear", symbol=SYMBOL, side="Sell", orderType="Limit",
                            qty=str(size), price=str(target_tp), reduceOnly=True
                        )
                        last_tp_price = target_tp
                        last_tp_update_time = now
                        print(f" 📈 Aggiornato Limit Take Profit → {target_tp} | PnL atteso: +{TAKE_PROFIT_PERCENT}%")
                    except:
                        pass

        # ==================== GENERAZIONE STRUTTURA GRIGLIA ====================
        elif size == 0 and (now - last_trade_time > COOLDOWN):
            safe_price = price if price is not None else 0.0
            print(f"\n 🛒 Avvio ciclo griglia 8 livelli @ {safe_price:.4f}")
            cancel_all_orders()
            time.sleep(1.0)

            # Livello 1: Ordine a mercato immediato basato sulla tua BASE_QTY
            qty_livello_1 = round_qty(BASE_QTY * GRID_MULTIPLIERS[0])
            
            try:
                session.place_order(category="linear", symbol=SYMBOL, side="Buy", orderType="Market", qty=str(qty_livello_1))
                print(f" 🟢 [L1] Eseguito Market: {qty_livello_1} UAI")
            except Exception as e:
                print(f" [ERRORE CRITICO] Impossibile aprire ordine iniziale: {e}")
                time.sleep(10)
                continue

            time.sleep(2.0) # Sincronizzazione server
            new_pos = session.get_positions(category="linear", symbol=SYMBOL)["result"]["list"][0]
            avg = float(new_pos["avgPrice"])
            
            # Fissiamo il prezzo di partenza reale
            prezzo_inizio_griglia = avg 
            
            # Calcolo del prezzo di Stop Loss statico
            prezzo_sl = round_price(prezzo_inizio_griglia * (1 - STOP_LOSS_PERCENT / 100))
            print(f" 📌 Prezzo base impostato a: {prezzo_inizio_griglia:.5f}")
            
            # ------------------------------------------------------------------
            # PIAZZAMENTO DELLO STOP LOSS REALE (CONDIZIONALE) SU BYBIT (FIXED)
            # ------------------------------------------------------------------
            try:
                session.place_order(
                    category="linear",
                    symbol=SYMBOL,
                    side="Sell",
                    orderType="Market",       # Eseguito a mercato al tocco del trigger
                    qty=str(MAX_TOTAL_QTY),   # Esattamente la somma totale (es. 972)
                    triggerPrice=str(prezzo_sl),
                    triggerBy="LastPrice",
                    triggerDirection=2,        # FIXED: 2 indica che il prezzo scende verso lo SL
                    reduceOnly=True           # Chiude la griglia senza aprire short
                )
                print(f" 🛑 [STOP LOSS NATIVO] Inserito su Bybit a {prezzo_sl:.5f} per {MAX_TOTAL_QTY} UAI (Visibile sul grafico)")
            except Exception as sl_err:
                print(f" ⚠️ Errore critico nell'inserimento dello Stop Loss nativo: {sl_err}")

            # Generazione automatica dei restanti 7 livelli LIMIT
            accumulated_drop = 0
            for i in range(1, len(GRID_MULTIPLIERS)):
                accumulated_drop += GRID_SPACING[i]
                entry_price = round_price(prezzo_inizio_griglia * (1 - accumulated_drop / 100))
                qty_livello = round_qty(BASE_QTY * GRID_MULTIPLIERS[i])
                
                try:
                    session.place_order(
                        category="linear", symbol=SYMBOL, side="Buy",
                        orderType="Limit", qty=str(qty_livello), price=str(entry_price)
                    )
                    print(f" 📥 [L{i+1}] Inserito Limit @ {entry_price:.5f} | Qty: {qty_livello} UAI | Drop: -{accumulated_drop:.1f}%")
                except Exception as grid_err:
                    print(f" ❌ Errore inserimento livello {i+1}: {grid_err}")
            
            last_trade_time = now
            print(" ✅ Griglia configurata e attiva. Monitoraggio ordinario...")

        time.sleep(2)

    except Exception as e:
        print(f" [ALLERTA SISTEMA] Errore nel ciclo continuo: {e}")
        time.sleep(5)
