import hashlib, hmac, json, os, random, time
from datetime import datetime
from zoneinfo import ZoneInfo
import requests

HOST = "https://api-e.ecoflow.com"
AK = os.environ["ECOFLOW_ACCESS_KEY"]
SK = os.environ["ECOFLOW_SECRET_KEY"]
SN = os.environ["ECOFLOW_SN"]
TG_TOKEN = os.environ["TELEGRAM_TOKEN"]
TG_CHAT = os.environ["TELEGRAM_CHAT_ID"]

STATE_FILE = "state.json"
NEEDED = {"offline": 2, "online": 1}   # сколько проверок подряд нужно для подтверждения
TZ = ZoneInfo("Europe/Kyiv")


def api_get(path):
    nonce = str(random.randint(100000, 999999))
    ts = str(int(time.time() * 1000))
    to_sign = f"accessKey={AK}&nonce={nonce}&timestamp={ts}"
    sign = hmac.new(SK.encode(), to_sign.encode(), hashlib.sha256).hexdigest()
    headers = {"accessKey": AK, "nonce": nonce, "timestamp": ts, "sign": sign}
    r = requests.get(HOST + path, headers=headers, timeout=20)
    r.raise_for_status()
    return r.json()


def is_online():
    data = api_get("/iot-open/sign/device/list")
    if data.get("code") != "0":
        raise RuntimeError("EcoFlow API error")
    for d in data.get("data", []):
        if d.get("sn") == SN:
            return d.get("online") == 1
    raise RuntimeError("Station not found in device list")


def send(text):
    r = requests.post(
        f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
        data={"chat_id": TG_CHAT, "text": text, "parse_mode": "HTML"},
        timeout=20,
    )
    r.raise_for_status()


def send_photo(path, caption):
    with open(path, "rb") as f:
        r = requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto",
            data={"chat_id": TG_CHAT, "caption": caption, "parse_mode": "HTML"},
            files={"photo": f},
            timeout=30,
        )
    r.raise_for_status()


def notify(image, text):
    try:
        send_photo(image, text)
    except Exception:
        send(text)  # если картинки нет или отправка не удалась, шлём просто текст


def fmt(sec):
    h, m = divmod(int(sec // 60), 60)
    return f"{h} ч {m} мин" if h else f"{m} мин"


def load():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None


def save(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)


def main():
    try:
        online = is_online()
    except Exception as e:
        print("Ошибка проверки:", type(e).__name__)
        return  # состояние не меняем, попробуем в следующий раз

    now = time.time()
    cur = "online" if online else "offline"
    state = load()

    if state is None:
        send("✅ <b>Мониторинг запущен!</b>\n\n⚡ EcoFlow сейчас: "
             + ("🟢 <b>в сети</b>" if online else "🔴 <b>не в сети</b>"))
        save({"status": cur, "since": now, "candidate": None, "count": 0})
        return

    before = json.dumps(state, sort_keys=True)

    if cur == state["status"]:
        state["candidate"], state["count"] = None, 0
    else:
        if state["candidate"] == cur:
            state["count"] += 1
        else:
            state["candidate"], state["count"] = cur, 1

        if state["count"] >= NEEDED[cur]:
            t = datetime.now(TZ).strftime("%d.%m %H:%M")
            dur = fmt(now - state["since"])
            if cur == "offline":
                notify(
                    "no_light.jpg",
                    "🔴🔴🔴 <b>СВЕТА НЕТ!</b> 🔴🔴🔴\n\n"
                    f"🕐 Пропал около <b>{t}</b>\n"
                    f"💡 Свет был: <b>{dur}</b>\n"
                    "📡 EcoFlow потерял связь"
                )
            else:
                notify(
                    "light_on.jpg",
                    "🟢🟢🟢 <b>СВЕТ ВЕРНУЛСЯ!</b> 🟢🟢🟢\n\n"
                    f"🕐 Появился около <b>{t}</b>\n"
                    f"⏳ Не было: <b>{dur}</b>"
                )
            state = {"status": cur, "since": now, "candidate": None, "count": 0}

    if json.dumps(state, sort_keys=True) != before:
        save(state)


main()
