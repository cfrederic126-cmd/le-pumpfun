#!/usr/bin/env python3
"""
Scanner de pattern "triangle ascendant -> cassure -> retest -> objectifs Fibonacci"
sur les cryptos USDT de Binance.

A executer EN LOCAL (ton laptop / VPS), pas dans un artifact claude.ai
(les artifacts bloquent les appels reseau externes en direct).

Dependance unique: requests
    pip install requests

Usage:
    python scanner_triangle_retest.py
    python scanner_triangle_retest.py --limit 80 --interval 4h
    python scanner_triangle_retest.py --interval 1h --limit 150 --json out.json

Alertes Telegram (optionnel) :
    1. Parle a @BotFather sur Telegram, envoie /newbot, suis les instructions
       -> tu recois un token du type 123456789:AAExxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
    2. Envoie un message quelconque a TON bot (pour qu'il te "connaisse")
    3. Recupere ton chat_id en ouvrant dans un navigateur :
       https://api.telegram.org/bot<TON_TOKEN>/getUpdates
       -> cherche le champ "chat":{"id": ...} dans la reponse JSON
    4. Lance le scanner avec :
       python scanner_triangle_retest.py --telegram-token "TON_TOKEN" --telegram-chat "TON_CHAT_ID"
       (ou exporte TELEGRAM_BOT_TOKEN et TELEGRAM_CHAT_ID comme variables d'environnement)

Mode continu (scan automatique toutes les N minutes) :
    python scanner_triangle_retest.py --loop 15 --telegram-token "..." --telegram-chat "..."
    -> a lancer dans un tmux/screen sur ton VPS, ou via cron pour un scan ponctuel.

Les alertes ne sont envoyees que pour les setups NOUVEAUX ou dont le statut a
change depuis le dernier scan (etat garde dans scanner_state.json), pour eviter
de recevoir le meme message a chaque passage.
"""

import argparse
import json
import os
import time
import sys
from datetime import datetime

try:
    import requests
except ImportError:
    print("Il manque le module 'requests'. Installe-le avec : pip install requests")
    sys.exit(1)

BINANCE_HOSTS = [
    "https://api.binance.com",
    "https://api1.binance.com",
    "https://api2.binance.com",
    "https://data-api.binance.vision",
]

STATE_FILE = "scanner_state.json"


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------

def send_telegram(token, chat_id, text):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        r = requests.post(url, data={"chat_id": chat_id, "text": text, "parse_mode": "HTML"}, timeout=10)
        if not r.ok:
            print(f"  [Telegram] echec envoi: HTTP {r.status_code} — {r.text[:200]}")
    except Exception as e:
        print(f"  [Telegram] echec envoi: {e}")


def format_alert(f):
    label = STATUS_LABEL[f["status"]]
    emoji = {
        "retest-en-cours": "\U0001F7E2",
        "casse-sans-retest": "\U0001F7E1",
        "retest-confirme": "\U0001F535",
        "approche": "\u26AA",
        "invalide": "\U0001F534",
    }.get(f["status"], "")
    return (
        f"{emoji} <b>{f['symbol']}</b> — {label}\n"
        f"Prix: {f['last_close']:.6f}\n"
        f"Resistance/retest: {f['resistance']:.6f}\n"
        f"Ecart: {((f['last_close']-f['resistance'])/f['resistance'])*100:+.2f}%\n"
        f"Fib 1.272/1.414/1.618: {f['fib_targets'][0]:.6f} / {f['fib_targets'][1]:.6f} / {f['fib_targets'][2]:.6f}"
    )


def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as fh:
                return json.load(fh)
        except Exception:
            return {}
    return {}


def save_state(state):
    with open(STATE_FILE, "w") as fh:
        json.dump(state, fh, indent=2)


# ---------------------------------------------------------------------------
# Reseau
# ---------------------------------------------------------------------------

def get_json(path, params=None, timeout=10):
    last_err = None
    for host in BINANCE_HOSTS:
        try:
            r = requests.get(host + path, params=params, timeout=timeout)
            if r.ok:
                return r.json()
            last_err = f"HTTP {r.status_code} sur {host}"
        except Exception as e:
            last_err = str(e)
    raise RuntimeError(f"Echec reseau: {last_err}")


def fetch_top_symbols(limit):
    data = get_json("/api/v3/ticker/24hr")
    usdt = [
        t for t in data
        if t["symbol"].endswith("USDT")
        and "UPUSDT" not in t["symbol"]
        and "DOWNUSDT" not in t["symbol"]
    ]
    usdt.sort(key=lambda t: float(t["quoteVolume"]), reverse=True)
    return [t["symbol"] for t in usdt[:limit]]


def fetch_klines(symbol, interval, limit=300):
    raw = get_json("/api/v3/klines", {"symbol": symbol, "interval": interval, "limit": limit})
    if not isinstance(raw, list):
        return None
    return [
        {"t": k[0], "o": float(k[1]), "h": float(k[2]), "l": float(k[3]), "c": float(k[4])}
        for k in raw
    ]


# ---------------------------------------------------------------------------
# Detection de pattern (port du moteur JS)
# ---------------------------------------------------------------------------

def pivot_lows(data, w=3):
    idxs = []
    for i in range(w, len(data) - w):
        window = data[i - w:i + w + 1]
        if data[i]["l"] == min(d["l"] for d in window):
            idxs.append(i)
    return idxs


def pivot_highs(data, w=3):
    idxs = []
    for i in range(w, len(data) - w):
        window = data[i - w:i + w + 1]
        if data[i]["h"] == max(d["h"] for d in window):
            idxs.append(i)
    return idxs


def linreg(points):
    n = len(points)
    sx = sum(p[0] for p in points)
    sy = sum(p[1] for p in points)
    sxy = sum(p[0] * p[1] for p in points)
    sxx = sum(p[0] * p[0] for p in points)
    denom = (n * sxx - sx * sx) or 1
    slope = (n * sxy - sx * sy) / denom
    return slope


STATUS_LABEL = {
    "retest-en-cours": "RETEST EN COURS",
    "casse-sans-retest": "CASSURE - retest attendu",
    "retest-confirme": "Retest confirme",
    "approche": "Approche resistance",
    "invalide": "Retest invalide",
}
STATUS_ORDER = ["retest-en-cours", "casse-sans-retest", "retest-confirme", "approche", "invalide"]


def detect_setup(data):
    n = len(data)
    if n < 60:
        return None
    w = 3
    lows_idx = pivot_lows(data, w)
    highs_idx = pivot_highs(data, w)
    window_start = max(0, n - 220)

    candidate_lows = [i for i in lows_idx if window_start <= i <= n - 9]
    if len(candidate_lows) < 3:
        return None
    recent_lows = candidate_lows[-5:]
    low_pts = [(i, data[i]["l"]) for i in recent_lows]
    slope = linreg(low_pts)
    if slope <= 0:
        return None
    if data[recent_lows[-1]]["l"] <= data[recent_lows[0]]["l"]:
        return None

    first_low_idx = recent_lows[0]
    relevant_highs = [i for i in highs_idx if first_low_idx < i <= n - 1]
    if len(relevant_highs) < 2:
        return None

    clusters = []
    for i in relevant_highs:
        price = data[i]["h"]
        placed = False
        for c in clusters:
            if abs(price - c["avg"]) / c["avg"] < 0.025:
                c["members"].append(i)
                c["avg"] = sum(data[m]["h"] for m in c["members"]) / len(c["members"])
                placed = True
                break
        if not placed:
            clusters.append({"members": [i], "avg": price})

    valid_clusters = [c for c in clusters if len(c["members"]) >= 2]
    if not valid_clusters:
        return None
    valid_clusters.sort(key=lambda c: max(c["members"]), reverse=True)
    cap_cluster = valid_clusters[0]
    resistance = cap_cluster["avg"]
    cluster_end_idx = max(cap_cluster["members"])

    base_low = data[first_low_idx]["l"]
    height = resistance - base_low
    if height <= 0:
        return None
    fib_targets = [resistance + height * (r - 1) for r in (1.272, 1.414, 1.618)]

    breakout_idx = -1
    for i in range(cluster_end_idx + 1, n):
        if data[i]["c"] > resistance * 1.003:
            breakout_idx = i
            break

    last = n - 1
    status = None
    retest_idx = -1

    if breakout_idx == -1:
        dist_to_res = (resistance - data[last]["c"]) / resistance
        if 0 < dist_to_res < 0.03:
            status = "approche"
        else:
            return None
    else:
        for i in range(breakout_idx + 1, n):
            if resistance * 0.965 <= data[i]["l"] <= resistance * 1.02:
                retest_idx = i
                break
        if retest_idx != -1:
            if last - retest_idx <= 3 and data[last]["c"] > resistance * 0.99:
                status = "retest-en-cours"
            elif data[last]["c"] > resistance * 1.01:
                status = "retest-confirme"
            else:
                status = "invalide"
        else:
            if last - breakout_idx <= 10:
                status = "casse-sans-retest"
            else:
                return None

    return {
        "status": status,
        "resistance": resistance,
        "base_low": base_low,
        "fib_targets": fib_targets,
        "last_close": data[last]["c"],
    }


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def scan(limit, interval, pause=0.15):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Recuperation du classement par volume...")
    symbols = fetch_top_symbols(limit)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {len(symbols)} symboles a analyser (interval={interval})")

    found = []
    for i, symbol in enumerate(symbols, 1):
        try:
            data = fetch_klines(symbol, interval)
            if data and len(data) > 60:
                setup = detect_setup(data)
                if setup:
                    found.append({"symbol": symbol, **setup})
                    print(f"  [{i}/{len(symbols)}] {symbol:12s} -> {STATUS_LABEL[setup['status']]}")
        except Exception as e:
            print(f"  [{i}/{len(symbols)}] {symbol:12s} -> erreur: {e}")
        time.sleep(pause)

    found.sort(key=lambda f: STATUS_ORDER.index(f["status"]))
    return found


def alert_new_or_changed(found, token, chat_id, notify_statuses):
    """Envoie une alerte Telegram uniquement pour les setups nouveaux ou dont
    le statut a change depuis le dernier scan (evite le spam a chaque run)."""
    state = load_state()
    sent = 0
    for f in found:
        if f["status"] not in notify_statuses:
            continue
        key = f["symbol"]
        prev_status = state.get(key)
        if prev_status != f["status"]:
            send_telegram(token, chat_id, format_alert(f))
            sent += 1
            time.sleep(0.4)  # respecte le rate limit Telegram (~30 msg/s max, on reste large)
        state[key] = f["status"]
    # nettoie les symboles qui ne sont plus detectes du tout, pour repartir propre
    still_present = {f["symbol"] for f in found}
    state = {k: v for k, v in state.items() if k in still_present}
    save_state(state)
    if sent:
        print(f"[Telegram] {sent} alerte(s) envoyee(s).")


def print_report(found):
    print("\n" + "=" * 72)
    print(f"RESULTATS : {len(found)} setup(s) detecte(s)")
    print("=" * 72)
    for f in found:
        print(f"\n{f['symbol']}  —  {STATUS_LABEL[f['status']]}")
        print(f"  Dernier prix     : {f['last_close']:.6f}")
        print(f"  Resistance/retest: {f['resistance']:.6f}")
        print(f"  Base tendance    : {f['base_low']:.6f}")
        print(f"  Ecart au niveau  : {((f['last_close']-f['resistance'])/f['resistance'])*100:+.2f}%")
        print(f"  Fib 1.272 / 1.414 / 1.618 : "
              f"{f['fib_targets'][0]:.6f} / {f['fib_targets'][1]:.6f} / {f['fib_targets'][2]:.6f}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=40, help="Nombre de cryptos scannees (top volume)")
    parser.add_argument("--interval", type=str, default="1d", choices=["1h", "4h", "1d"], help="Unite de temps")
    parser.add_argument("--json", type=str, default=None, help="Chemin pour sauvegarder les resultats en JSON")
    parser.add_argument("--telegram-token", type=str, default=os.environ.get("TELEGRAM_BOT_TOKEN"),
                         help="Token du bot Telegram (ou variable d'env TELEGRAM_BOT_TOKEN)")
    parser.add_argument("--telegram-chat", type=str, default=os.environ.get("TELEGRAM_CHAT_ID"),
                         help="Chat ID Telegram (ou variable d'env TELEGRAM_CHAT_ID)")
    parser.add_argument("--notify", type=str, default="retest-en-cours,casse-sans-retest",
                         help="Statuts a notifier, separes par des virgules (defaut: retest-en-cours,casse-sans-retest)")
    parser.add_argument("--loop", type=int, default=0,
                         help="Relance le scan toutes les N minutes en continu (0 = un seul passage)")
    args = parser.parse_args()

    notify_statuses = set(args.notify.split(","))
    telegram_enabled = bool(args.telegram_token and args.telegram_chat)
    if not telegram_enabled:
        print("(Pas d'alertes Telegram configurees — utilise --telegram-token et --telegram-chat, "
              "voir le guide de configuration en commentaire en tete de fichier.)\n")

    def run_once():
        found = scan(args.limit, args.interval)
        print_report(found)
        if args.json:
            with open(args.json, "w") as f:
                json.dump(found, f, indent=2)
            print(f"\nResultats sauvegardes dans {args.json}")
        if telegram_enabled:
            alert_new_or_changed(found, args.telegram_token, args.telegram_chat, notify_statuses)

    if args.loop and args.loop > 0:
        print(f"Mode boucle : scan toutes les {args.loop} minutes. Ctrl+C pour arreter.\n")
        while True:
            run_once()
            print(f"\nProchain scan dans {args.loop} minutes...\n")
            time.sleep(args.loop * 60)
    else:
        run_once()


if __name__ == "__main__":
    main()
