
import os
import time
import datetime
import pytz
import requests
import pandas as pd
from pybit.unified_trading import HTTP

# ==============================================================================
# CONFIGURAZIONE TELEGRAM (da Environment Variables)
# ==============================================================================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "6916198243:AAFTF66LYSeqviL5YnfGtbUkSjTwPah6s")
CHAT_ID = os.environ.get("CHAT_ID", "820279313")

# ==============================================================================
# CONFIGURAZIONE OPERATIVA - QUANTITÀ FISSE (UAI)
# ==============================================================================
SYMBOL = "UAIUSDT"

# Le tue 3 Size personalizzabili (Modificabili a mano in al prezzo)
QTY_LIVELLO_NORMALE = 100  # Size standard con mercato tranquillo
QTY_LIVELLO_ALTO = 50     # Size ridotta con mercato nervoso
QTY_LIVELLO_ESTREMO = 20   # Size minima di emergenza con mercato impazzito

# SOGLIE DI ATTIVAZIONE (In salita - Calcolate sulle 24 ore mobili)
SOGLIA_ALTA_VOLATILITA = 25.0    # Sopra il 20%, passa a size 50
SOGLIA_ESTREMA_VOLATILITA = 50.0  # Sopra il 40%, passa a size 20

# SOGLIE DI RIPRISTINO / RIENTRO (In discesa per evitare l'effetto altalena)
RESET_DA_ALTO_A_NORMALE = 18.0   # Torna a 100 solo se scende sotto il 15%
RESET_DA_ESTREMO_A_ALTO = 35.0   # Torna a 50 solo se scende sotto il 30%

# 8 Livelli: il bot moltiplicherà la tua BASE_QTY attuale per questi coefficienti
GRID_MULTIPLIERS = [1, 1, 1.1, 1.3, 1.5, 2.4, 2.7, 2.9]

# Calibri degli spaziatori per arrivare precisi al 16% di calo cumulativo
GRID_SPAC = [0.0, 0.8, 1.0, 1.2, 1.5, 3.0, 4.0, 6.0]

# Target profit fisso della griglia (1% sul prezzo medio ponderato)
TAKE_PROFIT_PERCENT = 1

# Distanza percentuale dello Stop Loss Fisso dal prezzo di partenza dell'L1
STOP_LOSS_PERCENT = 21

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

# Livello di rischio corrente: "NORMALE", "ALTO", "ESTREMO"
stato_rischio_attuale = "NORMALE"  
BASE_QTY = QTY_LIVELLO_NORMALE   # Inizializzazione iniziale

# Variabili per invio Telegram saltuario (una volta al giorno)
ultimo_invio_6 = None  # Data dell'ultimo invio alle 06:00
ultimo_invio_18 = None # Data dell'ultimo invio alle 18:00

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

def get_daily_volatility():
    """
    Scarica le ultime 24 candele orarie (1H) per calcolare la volatilità 
    reale delle ultime 24 ore mobili, evitando il reset di mezzanotte.
    """
    try:
        kline_data = session.get_kline(
            category="linear",
            symbol=SYMBOL,
            interval="60", # 60 minuti = 1 ora
            limit=24       # Prende le ultime 24 ore
        )["result"]["list"]
        
        if not kline_data:
            return 0.0
            
        # Estraiamo i prezzi di High e Low da tutte le 24 candele
        highs = [float(candle[2]) for candle in kline_data]
        lows = [float(candle[3]) for candle in kline_data]
        
        # Il prezzo di apertura di 24 ore fa (l'ultima candela nella lista ritornata da Bybit)
        open_24h_ago = float(kline_data[-1][1]) 
        
        max_high = max(highs)
        min_low = min(lows)
        
        # Formula della volatilità mobile sulle 24 ore
        volatility = ((max_high - min_low) / open_24h_ago) * 100
        return volatility
    except Exception as e:
        print(f" ⚠️ Errore nel recupero della volatilità Rolling 24h: {e}")
        return 0.0

def cancel_all_orders():
    try:
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
        print(f" 💥 POSIZIONE CHIUSA A MERCATO | Size: {size}AI")
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

def get_wallet_balance_usdt():
    """Recupera il saldo del wallet spot o derivati in USDT (es. unified account)"""
    try:
        # Per conti Unificati di Bybit si usa get_wallet_balance
        wallet = session.get_wallet_balance(accountType="UNIFIED", coin="USDT")
        coins = wallet['result']['list'][0]['coin']
        for coin in coins:
            if coin['coin'] == 'USDT':
                return float(coin['walletBalance'])
        return 0.0
    except Exception as e:
        print(f" Errore recupero wallet: {e}")
        return 0.0

def send_telegram_message(message):
    """Invia un messaggio Telegram usando il bot token e chat ID configurati"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            'chat_id': CHAT_ID,
            'text': message,
            'parse_mode': 'HTML'
        }
        r = requests.post(url, data=payload, timeout=10)
        if r.status_code == 200:
            print(f" 📨 Messaggio Telegram inviato con successo.")
        else:
            print(f" ⚠️ Errore invio Telegram: {r.status_code} - {r.text}")
    except Exception as e:
        print(f" ⚠️ Eccezione nell'invio Telegram: {e}")

def get_italian_time():
    """Restituisce l'ora corrente in Italia (Europe/Rome) con timezone aware"""
    tz = pytz.timezone('Europe/Rome')
    return datetime.datetime.now(tz)

# ==============================================================================
# AVVIO BOT E CICLO CONTINUO
# ==============================================================================
print(" 🤖 BOT GRID LEVA 1 (v8.7 - Rolling 24h Volatility & 3 Scaglioni)")
print(f" Strumento: {SYMBOL}")
print(f"  -> MODALITÀ NORMALE: Size {QTY_LIVELLO_NORMALE}")
print(f"  -> MODALITÀ ALTA VOLATILITÀ (> {SOGLIA_ALTA_VOLATILITA}%): Size {QTY_LIVELLO_ALTO} (Rientro < {RESET_DA_ALTO_A_NORMALE}%)")
print(f"  -> MODALITÀ ESTREMA VOLATILITÀ (> {SOGLIA_ESTREMA_VOLATILITA}%): Size {QTY_LIVELLO_ESTREMO} (Rientro < {RESET_DA_ESTREMO_A_ALTO}%)")
print(f" Stop Loss Fisso (Nativo): -{STOP_LOSS_PERCENT}%\n")

while True:
    try:
        now = time.time()
        price = get_current_price()
        
        pos_data = session.get_positions(category="linear", symbol=SYMBOL)["result"]["list"][0]
        pos_side = pos_data.get("side",None")
        raw_size = float(pos_data["size"])

        size = raw_size if (pos_side == "Buy" and raw_size > 0) else 0.0
        avg_price = float(pos_data.get("avgPrice", 0))
        
        active_orders = session.get_open_orders(category="linear", symbol=SYMBOL)["result"]["list"]

        if size == 0:
            last_tp_price = 0.0
            prezzo_inizio_griglia = 0.0

        # ==================== GESTIONE TARGET PROFIT (TP) ====================
        if size > 0:
            target_tp = round_price(avg_price * (1 + TAKE_PROFIT_PERCENT / 100))

            if price and price >= target_tp:
                print(f" 🎯 Target raggiunto a mercato! Prezzo ({price}) >= TP ({target_tp}). Chiusura griglia.")
                cancel_all_orders()
                close_position()
                last_trade_time = now  
                last_tp_price = 0.0
                prezzo_inizio_griglia = 0.0
            
            elif (abs(target_tp - last_tp_price) > (10 ** -PRICE_DECIMALS)) and (now - last_tp_update_time > 10):
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
            
            # --- MACCHINA A STATI DELLA
