import threading
import time
import requests
import os

URL = os.getenv("KEEP_ALIVE_URL", "https://songaura.onrender.com")

def ping():
    while True:
        try:
            r = requests.get(URL)
            print(f"[KEEP-ALIVE] Ping {URL} → {r.status_code}")
        except Exception as e:
            print(f"[KEEP-ALIVE] Ошибка: {e}")
        time.sleep(300)  # каждые 5 минут

def keep_alive():
    t = threading.Thread(target=ping, daemon=True)
    t.start()
