import os
import time
from datetime import datetime
from pybit.unified_trading import HTTP

print("🚀 Bot avviato - Versione Debug 9.2")

# ====================== CONFIG ======================
SYMBOL = "UAIUSDT"
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

print(f"API Key presente: {'OK' if os.environ.get('BYBIT_API_KEY') else 'MISSING'}")
print(f"Telegram configurato: {'OK' if TELEGRAM_BOT_TOKEN and CHAT_ID else 'MISSING'}")

# ====================== CONNESSIONE ======================
try:
    session = HTTP(
        testnet=False,
        api_key=os.environ.get("BYBIT_API_KEY"),
        api_secret=os.environ.get("BYBIT_API_SECRET")
    )
    print("✅ Connessione Bybit OK")
except Exception as e:
    print(f"❌ Errore connessione Bybit: {e}")

# ====================== FUNZIONI ======================
def send_telegram(text):
    if not TELEGRAM_BOT_TOKEN or not CHAT_ID:
        print("⚠️ Telegram non configurato")
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}
        r = requests.post(url, json=payload, timeout=10)
        print(f"Telegram status: {r.status_code}")
    except Exception as e:
        print(f"Errore Telegram: {e}")

def get_wallet_balance():
    try:
        res = session.get_wallet_balance(accountType="UNIFIED")
        account = res["result"]["list"][0]
        total = float(account.get("totalWalletBalance", 0))
        print(f"💰 Wallet letto: {total:.2f} USDT")
        return total
    except Exception as e:
        print(f"❌ Errore Wallet: {e}")
        return 0.0

# ====================== AVVIO ======================
try:
    balance = get_wallet_balance()
    send_telegram(f"🤖 Bot Debug avviato su Render\n💰 Saldo: {balance:.2f} USDT\n🕒 {datetime.now()}")
    print("✅ Messaggio Telegram inviato (se configurato)")
except Exception as e:
    print(f"Errore avvio: {e}")

# ====================== CICLO PRINCIPALE ======================
print("Inizio ciclo principale...")
while True:
    try:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Bot vivo - Saldo: {get_wallet_balance():.2f}")
        time.sleep(10)
    except Exception as e:
        print(f"Errore ciclo: {e}")
        time.sleep(10)
