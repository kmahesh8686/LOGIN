#!/usr/bin/env python3
from flask import Flask, request, jsonify
from collections import deque
from flask_cors import CORS
import threading
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo   # <<< BUILT-IN, PERFECT FOR CLOUD

app = Flask(__name__)
CORS(app)

# Timezone object (NO external libs)
IST = ZoneInfo("Asia/Kolkata")

lock = threading.Lock()
login_queue = deque()
latest_batch = []
assigned_today = set()
cycle_index = 0
browser_counter = 0
stored_server_time = None

auto_refill_enabled = True

CYCLE_TIMES = [
    (10, 1, 25, 0),
    (10, 1, 30, 0),
    (10, 1, 26, 0),
    (10, 1, 29, 0),
    (10, 1, 27, 0),
    (10, 1, 28, 0)
]

def make_time_today(base, h, m, s, ms):
    return base.replace(hour=h, minute=m, second=s, microsecond=ms * 1000)

def find_next_click_time(now):
    global cycle_index, assigned_today
    total = len(CYCLE_TIMES)
    attempts = 0

    while attempts < total:
        h, m, s, ms = CYCLE_TIMES[cycle_index]
        t = make_time_today(now, h, m, s, ms)
        key = t.strftime("%H:%M:%S")

        cycle_index = (cycle_index + 1) % total
        attempts += 1

        if t < now or key in assigned_today:
            continue

        assigned_today.add(key)
        return t

    # fallback same day
    for h, m, s, ms in CYCLE_TIMES:
        t = make_time_today(now, h, m, s, ms)
        key = t.strftime("%H:%M:%S")
        if t > now and key not in assigned_today:
            assigned_today.add(key)
            return t

    # next day
    assigned_today.clear()
    h, m, s, ms = CYCLE_TIMES[0]
    next_day_time = make_time_today(now, h, m, s, ms) + timedelta(days=1)
    assigned_today.add(next_day_time.strftime("%H:%M:%S"))
    cycle_index = 1
    return next_day_time

@app.route('/')
def home():
    return "Flask Login Assign + Click-Time Server Running (IST Enabled)"

@app.route('/api/get-server-time', methods=['GET'])
def get_server_time():
    global stored_server_time

    if stored_server_time:
        return jsonify({"serverTime": stored_server_time}), 200

    return jsonify({"serverTime": datetime.now(IST).isoformat()}), 200

@app.route('/api/set-time', methods=['POST'])
def set_time():
    global stored_server_time
    data = request.get_json(silent=True) or {}
    new_time = data.get("time", "").strip()

    if not new_time:
        return jsonify({"error": "Missing 'time' field"}), 400

    stored_server_time = new_time
    return jsonify({"status": "saved", "serverTime": stored_server_time}), 200

@app.route('/login_data', methods=['POST', 'OPTIONS'])
def login_data():
    global login_queue, latest_batch, auto_refill_enabled

    if request.method == 'OPTIONS':
        return jsonify({"status": "ok"}), 200

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"status": "error", "message": "Invalid or missing JSON"}), 400

    new_queue = deque()
    new_batch = []

    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                u = item.get("username")
                p = item.get("password")
                if u and p:
                    rec = {"username": str(u), "password": str(p)}
                    new_queue.append(rec)
                    new_batch.append(rec)

    elif isinstance(data, dict):
        u = data.get("username")
        p = data.get("password")
        if u and p:
            rec = {"username": str(u), "password": str(p)}
            new_queue.append(rec)
            new_batch.append(rec)

    else:
        return jsonify({"status": "error", "message": "Invalid JSON"}), 400

    if not new_batch:
        return jsonify({"status": "error", "message": "Empty login batch"}), 400

    with lock:
        login_queue = new_queue
        latest_batch = new_batch
        auto_refill_enabled = True

    return jsonify({
        "status": "success",
        "message": f"Stored {len(new_batch)} login(s)",
        "queue_length": len(login_queue)
    }), 200

@app.route('/login_assign', methods=['GET'])
def login_assign():
    global login_queue, latest_batch, auto_refill_enabled

    cancel_req = request.args.get("cancel", "").strip()
    mobile_to_remove = request.args.get("mobile", "").strip()

    with lock:
        if mobile_to_remove:
            login_queue = deque([i for i in login_queue if i["username"] != mobile_to_remove])
            latest_batch = [i for i in latest_batch if i["username"] != mobile_to_remove]
            return jsonify({
                "status": "removed",
                "queue_length": len(login_queue)
            }), 200

        if cancel_req == "1":
            auto_refill_enabled = False
            return jsonify({"status": "cancelled"}), 200

        if not login_queue:
            if not auto_refill_enabled:
                return jsonify({"status": "empty"}), 200
            if not latest_batch:
                return jsonify({"status": "empty"}), 200
            login_queue = deque([dict(i) for i in latest_batch])

        next_login = login_queue.popleft()

    return jsonify({"status": "success", "data": next_login}), 200

@app.route('/api/get-click-time', methods=['POST'])
def get_click_time():
    data = request.get_json(silent=True) or {}
    mobile = str(data.get("mobile", "")).strip()

    if not mobile:
        return jsonify({"error": "Missing mobile"}), 400

    now = datetime.now(IST)  # <<< IMPORTANT
    click_time = find_next_click_time(now)

    return jsonify({"clickTime": click_time.isoformat()}), 200

@app.route('/api/browser-count', methods=['GET'])
def browser_count():
    global browser_counter
    with lock:
        browser_counter += 1
        count_value = browser_counter
    return jsonify({"count": count_value}), 200

@app.route('/api/browser-count/clear', methods=['GET'])
def clear_browser_count():
    global browser_counter
    with lock:
        browser_counter = 0
    return jsonify({"count": 0}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
