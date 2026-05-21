import time
import math
import os  # <--- Fondamentale per leggere le variabili d'ambiente di Render
from pybit.unified_trading import HTTP

# =====================================================================
# CONFIGURAZIONE API CREDENTIALS (PROTETTE DA ENVIRONMENT VARIABLES)
# =====================================================================
# Il bot pescherà le chiavi in automatico dalla memoria sicura di Render
API_KEY = os.environ.get("BYBIT_API_KEY")
API_SECRET = os.environ.get("BYBIT_API_SECRET")
SYMBOL = "LABUSDT"          

# Griglia a 13 livelli espansa con ordini da 25, 30 e il Jolly da 50 LAB
GRID_SIZES = [2, 2, 2, 2, 5, 7, 9, 11, 15, 20, 25, 30, 50] 
TOTAL_EMERGENCY_SIZE = sum(GRID_SIZES) # Calcola automaticamente 180.0 LAB

# Connessione nativa ai server di Bybit
# NOTA: testnet=False è necessario per la nuova modalità "Demo Trading" del sito principale
session = HTTP(
    testnet=False,
    api_key=API_KEY,
    api_secret=API_SECRET
)

# Memoria di stato per la gestione dinamica del ciclo
bot_state = {
    "last_vol_check": 0,
    "current_regime_ratio": 1.0,
    "emergency_state_active": False,
    "half_size_liquidated": False,
    "max_price_reached_during_rebound": 0.0,
    "grid_placed": False
}

# =====================================================================
# FUNZIONI DI MERCATO API BYBIT V5
# =====================================================================

def get_volatility_ratio():
    """Analisi Volatilità Relativa: Confronta l'ultima ora con i 3 giorni passati"""
    try:
        # Benchmark 3 giorni (Candele Daily)
        kline_3gg = session.get_kline(category="linear", symbol=SYMBOL, interval="D", limit=3)['result']['list']
        ranges_3gg = [float(c[2]) - float(c[3]) for c in kline_3gg] # High - Low
        avg_range_3gg = sum(ranges_3gg) / len(ranges_3gg)
        
        # Flusso attuale 1 ora (60 candele da 1 minuto)
        kline_1h = session.get_kline(category="linear", symbol=SYMBOL, interval="1", limit=60)['result']['list']
        ranges_1h = [float(c[2]) - float(c[3]) for c in kline_1h]
        avg_range_1h = (sum(ranges_1h) / len(ranges_1h)) * 60 
        
        if avg_range_3gg > 0:
            ratio = avg_range_1h / avg_range_3gg
            return round(ratio, 2)
        return 1.0
    except Exception as e:
        print(f"⚠️ Nota: Impossibile calcolare volatilità (Uso Ratio Standard 1.0): {e}")
        return 1.0

def get_current_price():
    """Recupera l'ultimo prezzo battuto dal mercato ticker"""
    try:
        ticker = session.get_tickers(category="linear", symbol=SYMBOL)
        return float(ticker['result']['list'][0]['lastPrice'])
    except Exception as e:
        print(f"⚠️ Errore lettura prezzo di mercato: {e}")
        return 0.0

def get_active_position():
    """Verifica lo stato della posizione attiva (One-Way Mode)"""
    try:
        res = session.get_positions(category="linear", symbol=SYMBOL)
        positions = res.get('result', {}).get('list', [])
        
        for p in positions:
            size = float(p.get('size', 0))
            if size > 0:
                return size, float(p['avgPrice'])
        return 0.0, 0.0
    except Exception as e:
        print(f"⚠️ Errore lettura posizioni aperte: {e}")
        return 0.0, 0.0

def cancel_all_grid_orders():
    """Pulisce il book da tutti gli ordini Limit pendenti del bot"""
    try:
        session.cancel_all_orders(category="linear", symbol=SYMBOL)
        print("🧹 Tabula rasa sul book. Ordini pendenti cancellati.")
    except Exception as e:
        print(f"⚠️ Errore cancellazione ordini: {e}")

def place_dynamic_grid(current_price, vol_ratio):
    """Piazza la griglia a fisarmonica (13 livelli geometrici) allineata alla volatilità"""
    cancel_all_grid_orders()
    
    base_step_percent = 0.01 
    dynamic_step = base_step_percent * vol_ratio
    
    print(f"📐 Configurazione Griglia a Fisarmonica | Spaziatura Corrente: {dynamic_step * 100:.2f}%")
    
    for i, size in enumerate(GRID_SIZES):
        # Ogni livello si distanzia progressivamente seguendo la volatilità
        target_price = current_price * (1 - (dynamic_step * (i + 1)))
        target_price = round(target_price, 4) 
        
        try:
            session.place_order(
                category="linear",
                symbol=SYMBOL,
                side="Buy",
                orderType="Limit",
                qty=str(size),
                price=str(target_price),
                positionIdx=0
            )
        except Exception as e:
            print(f"❌ Impossibile piazzare livello {i+1} (Size: {size} LAB): {e}")

def market_close_position(qty_to_close):
    """Spara un ordine Market immediato per alleggerire la posizione"""
    try:
        session.place_order(
            category="linear",
            symbol=SYMBOL,
            side="Sell",
            orderType="Market",
            qty=str(qty_to_close),
            positionIdx=0
        )
    except Exception as e:
        print(f"❌ Errore esecuzione ordine Market: {e}")

# =====================================================================
# ARCHITETTURA CICLO CONTINUO (MONITORAGGIO LOGICO)
# =====================================================================

def run_bot():
    print("🚀 MASTER BOT PRONTO. Avvio del monitoraggio demo in corso su Bybit...")
    
    while True:
        try:
            position_size, avg_price = get_active_position()
            market_price = get_current_price()
            
            if market_price == 0.0:
                time.sleep(2)
                continue

            # CONTROLLO VOLATILITÀ PERIODICO (Ogni 5 minuti)
            if time.time() - bot_state["last_vol_check"] > 300:
                bot_state["current_regime_ratio"] = get_volatility_ratio()
                bot_state["last_vol_check"] = time.time()
                
                # Applica il Cancel & Replace se siamo flat sul mercato
                if position_size == 0:
                    print(f"🔄 Ricalcolo Volatilità Completato (Ratio Attuale: {bot_state['current_regime_ratio']})")
                    place_dynamic_grid(market_price, bot_state["current_regime_ratio"])
                    bot_state["grid_placed"] = True

            # CASO 1: NESSUNA POSIZIONE (Mercato in attesa o ciclo chiuso)
            if position_size == 0:
                if not bot_state["grid_placed"]:
                    place_dynamic_grid(market_price, bot_state["current_regime_ratio"])
                    bot_state["grid_placed"] = True
                
                # Reset totale della memoria difensiva
                bot_state["emergency_state_active"] = False
                bot_state["half_size_liquidated"] = False
                bot_state["max_price_reached_during_rebound"] = 0.0

            # CASO 2: STATO DI EMERGENZA (Caricato anche il 13° livello - Jolly da 50 LAB)
            elif position_size >= TOTAL_EMERGENCY_SIZE:
                if not bot_state["emergency_state_active"]:
                    print("🚨 EMERGENZA ATTIVATA: Raggiunto il fondo griglia con il Jolly da 50 LAB!")
                    cancel_all_grid_orders() # Blocca inserimenti spuri
                    bot_state["emergency_state_active"] = True

                # Target Break-Even calcolato per recuperare subito le commissioni (+0.2%)
                target_break_even = avg_price * 1.002
                
                # FASE A: Scarico immediato del 50% al tocco della media di carico
                if market_price >= target_break_even and not bot_state["half_size_liquidated"]:
                    size_to_liquidate = round(position_size / 2, 2)
                    print(f"⚡ Rimbalzo tecnico intercettato. Liquidazione immediata del 50% ({size_to_liquidate} LAB)")
                    market_close_position(size_to_liquidate)
                    
                    bot_state["half_size_liquidated"] = True
                    bot_state["max_price_reached_during_rebound"] = market_price
                    print("✅ Rischio monetario dimezzato. Attivazione Inseguitore Stop Loss sulla quota restante.")
                
                # FASE B: Trailing Stop Loss del -2% sulla metà protetta
                if bot_state["half_size_liquidated"]:
                    if market_price > bot_state["max_price_reached_during_rebound"]:
                        bot_state["max_price_reached_during_rebound"] = market_price
                    
                    trailing_sl_floor = bot_state["max_price_reached_during_rebound"] * 0.98
                    
                    if market_price <= trailing_sl_floor:
                        print(f"📉 Il rimbalzo si è arrestato. Scatta il Trailing SL di emergenza a {market_price}")
                        current_remany_size, _ = get_active_position()
                        if current_remany_size > 0:
                            market_close_position(current_remany_size)
                        bot_state["grid_placed"] = False 

            # CASO 3: GESTIONE PROFITTO DINAMICO (Griglia standard parziale: livelli da 1 a 12)
            elif position_size > 0 and position_size < TOTAL_EMERGENCY_SIZE:
                bot_state["grid_placed"] = False 
                
                # Assegnazione automatica del Take Profit in base alla volatilità calcolata
                if bot_state["current_regime_ratio"] < 0.7:
                    tp_percent = 0.006  # +0.6% (Bassa volatilità: prendi e scappa)
                    regime_name = "BASSA VOLATILITÀ"
                elif bot_state["current_regime_ratio"] > 1.5:
                    tp_percent = 0.012  # +1.2% (Alta volatilità: estendi l'uscita sul rimbalzo)
                    regime_name = "ALTA VOLATILITÀ"
                else:
                    tp_percent = 0.008  # +0.8% (Regime Standard)
                    regime_name = "VOLATILITÀ NORMALE"
                
                dynamic_tp_target = avg_price * (1 + tp_percent)
                
                # Stampa ottimizzata per i log persistenti del Cloud (senza end="\r")
                print(f"📊 [Posizione: {position_size} LAB] | [Media: {avg_price:.4f}] | [{regime_name}] | [Target TP: {dynamic_tp_target:.4f}]")
                
                if market_price >= dynamic_tp_target:
                    print(f"\n💰 Target {regime_name} (+{tp_percent*100}%) Preso! Liquidazione totale della griglia.")
                    market_close_position(position_size)
                    cancel_all_grid_orders()
                    bot_state["grid_placed"] = False

        except Exception as e:
            print(f"\n⚠️ Interruzione aggirata nel ciclo principale: {e}")
            
        time.sleep(2) # Pausa di 2 secondi per il rispetto dei limiti di frequenza (Rate Limit) Bybit

if __name__ == "__main__":
    run_bot()
