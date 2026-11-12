import hashlib, hmac, json, os, random, time
from datetime import datetime
from zoneinfo import ZoneInfo
import requests

HOST = "https://api-e.ecoflow.com"
AK = os.environ["q8rVYYMc3T4RR4lHIhOK3Z3XNyfhEfeV"]
SK = os.environ["yBcu5JjF6jwVP5wdsP8fYvnpMgTwWBvH"]
SN = os.environ["R631ZEBAWH3W0378"]
TG_TOKEN = os.environ["9022343226:AAFCM8xqrjYL5oxf2A7xf7BaAzyrke-6tus"]
TG_CHAT = os.environ["107095115"]

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
        data={"chat_id": TG_CHAT, "text": text},
        timeout=20,
    )
    r.raise_for_status()


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
        send("Мониторинг запущен. EcoFlow сейчас: " + ("в сети." if online else "не в сети."))
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
            t = datetime.now(TZ).strftime("%H:%M")
            dur = fmt(now - state["since"])
            if cur == "offline":
                send(f"🔴 Света нет (EcoFlow офлайн), около {t}. Свет был {dur}.")
            else:
                send(f"🟢 Свет появился (EcoFlow онлайн), около {t}. Не было {dur}.")
            state = {"status": cur, "since": now, "candidate": None, "count": 0}

    if json.dumps(state, sort_keys=True) != before:
        save(state)


main()
