import os
import time
import requests
from datetime import datetime
from pybit.unified_trading import HTTP

# ==============================================================================
# CONFIG
# ==============================================================================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
SYMBOL = "UAIUSDT"

QTY_LIVELLO_NORMALE = 100
QTY_LIVELLO_ALTO = 50
QTY_LIVELLO_ESTREMO = 20

SOGLIA_ALTA_VOLATILITA = 25.0
SOGLIA_ESTREMA_VOLATILITA = 50.0
RESET_DA_ALTO_A_NORMALE = 18.0
RESET_DA_ESTREMO_A_ALTO = 35.0

GRID_MULTIPLIERS = [1, 1, 1.1, 1.3, 1.5, 2.4, 2.7, 2.9]
GRID_SPACING = [0.0, 0.8, 1.0, 1.2, 1.5, 3.0, 4.0, 6.0]

TAKE_PROFIT_PERCENT = 1
STOP_LOSS_PERCENT = 21
COOLDOWN = 30

# ==============================================================================
session = HTTP(
    testnet=False,
    api_key=os.environ.get("BYBIT_API_KEY"),
    api_secret=os.environ.get("BYBIT_API_SECRET")
)

# ==============================================================================
def send_telegram(message):
    if not TELEGRAM_BOT_TOKEN or not CHAT_ID:
        print("⚠️ Telegram non configurato")
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"}, timeout=10)
    except:
        pass

def get_wallet_balance():
    try:
        res = session.get_wallet_balance(accountType="UNIFIED")
        print("🔍 DEBUG Wallet Response:", res)   # ← IMPORTANTISSIMO
        
        account = res["result"]["list"][0]
        total = float(account.get("totalWalletBalance", 0))
        available = float(account.get("totalAvailableBalance", 0))
        
        print(f"💰 Total Wallet: {total:.2f} | Available: {available:.2f}")
        
        for coin in account.get("coin", []):
            if coin.get("coin") == "USDT":
                wb = float(coin.get("walletBalance", 0))
                print(f"💰 USDT walletBalance: {wb:.2f}")
                return wb
        return total if total > 0 else available
    except Exception as e:
        print(f"❌ Errore Wallet: {e}")
        return 0.0

def get_current_price():
    try:
        ticker = session.get_tickers(category="linear", symbol=SYMBOL)
        return float(ticker["result"]["list"][0]["lastPrice"])
    except:
        return None

def cancel_all_orders():
    try:
        session.cancel_all_orders(category="linear", symbol=SYMBOL)
        return True
    except:
        return False

# ==============================================================================
print("🤖 BOT UAIUSDT v9.1 - DEBUG MODE")
print(f"API Key presente: {'Sì' if os.environ.get('BYBIT_API_KEY') else 'NO'}")

balance = get_wallet_balance()
send_telegram(f"🚀 Bot avviato su Render\n💰 Saldo: {balance:.2f} USDT")

last_trade_time = 0
stato_rischio = "NORMALE"
BASE_QTY = QTY_LIVELLO_NORMALE

while True:
    try:
        price = get_current_price()
        now = time.time()
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Prezzo: {price} | Saldo: {get_wallet_balance():.2f} | Stato: {stato_rischio}")

        # ==================== APERTURA GRIGLIA ====================
        if price and (now - last_trade_time > COOLDOWN):
            pos = session.get_positions(category="linear", symbol=SYMBOL)["result"]["list"][0]
            size = float(pos.get("size", 0))
            
            if size == 0:
                daily_vol = 20.0  # placeholder per test
                
                if daily_vol > SOGLIA_ESTREMA_VOLATILITA:
                    stato_rischio = "ESTREMO"
                    BASE_QTY = QTY_LIVELLO_ESTREMO
                elif daily_vol > SOGLIA_ALTA_VOLATILITA:
                    stato_rischio = "ALTO"
                    BASE_QTY = QTY_LIVELLO_ALTO
                else:
                    stato_rischio = "NORMALE"
                    BASE_QTY = QTY_LIVELLO_NORMALE

                print(f"🛒 AVVIO GRIGLIA @ {price:.5f} | Rischio: {stato_rischio} | Qty base: {BASE_QTY}")
                
                cancel_all_orders()
                time.sleep(1)

                # Market Buy Livello 1
                qty = BASE_QTY
                session.place_order(
                    category="linear", symbol=SYMBOL, side="Buy",
                    orderType="Market", qty=str(qty)
                )
                print(f"✅ Market Buy eseguito: {qty} UAI")
                
                last_trade_time = now
                send_telegram(f"🟢 Griglia avviata @ {price:.5f}\nRischio: {stato_rischio}")

        time.sleep(5)

    except Exception as e:
        print(f"❌ Errore ciclo: {e}")
        time.sleep(10)
