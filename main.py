from flask import Flask, jsonify, request
import requests
import re
import time
import os
from datetime import datetime, timedelta
import json
import threading
from collections import deque

app = Flask(__name__)

# ============================================
# CREDENTIALS - Use environment variables
# ============================================
USERNAME = os.environ.get("TEMP_NUMBERS_USERNAME", "antallhayat")
PASSWORD = os.environ.get("TEMP_NUMBERS_PASSWORD", "77889900")

BASE_URL = "http://tempnumbers.net"

USER_AGENT = (
    "Mozilla/5.0 (Linux; Android 10; K) "
    "Chrome/130.0.0.0 Mobile Safari/537.36"
)

session = requests.Session()

# Store for SMS messages
sms_storage = deque(maxlen=1000)  # Store last 1000 messages
seen_sms = set()
sms_lock = threading.Lock()

# For Railway, we'll use a simple file-based storage
SEEN_FILE = "seen_sms.json"
STORAGE_FILE = "sms_storage.json"


# ============================================
# PERSISTENT STORAGE
# ============================================
def load_data():
    """Load seen SMS and storage from files"""
    global seen_sms, sms_storage
    try:
        if os.path.exists(SEEN_FILE):
            with open(SEEN_FILE, 'r') as f:
                seen_sms = set(json.load(f))
            print(f"📂 Loaded {len(seen_sms)} seen SMS records")
    except Exception as e:
        print(f"⚠️ Could not load seen SMS: {e}")
        seen_sms = set()
    
    try:
        if os.path.exists(STORAGE_FILE):
            with open(STORAGE_FILE, 'r') as f:
                stored = json.load(f)
                sms_storage = deque(stored, maxlen=1000)
            print(f"📂 Loaded {len(sms_storage)} stored SMS messages")
    except Exception as e:
        print(f"⚠️ Could not load SMS storage: {e}")
        sms_storage = deque(maxlen=1000)


def save_data():
    """Save seen SMS and storage to files"""
    try:
        with open(SEEN_FILE, 'w') as f:
            json.dump(list(seen_sms), f)
        with open(STORAGE_FILE, 'w') as f:
            json.dump(list(sms_storage), f)
    except Exception as e:
        print(f"⚠️ Could not save data: {e}")


# ============================================
# LOGIN
# ============================================
def login():
    print(f"🔐 Logging in as {USERNAME}...")

    try:
        response = session.get(
            f"{BASE_URL}/login",
            headers={"User-Agent": USER_AGENT},
            timeout=20
        )

        captcha_match = re.search(
            r"What is (\d+) \+ (\d+) = ?",
            response.text
        )

        if not captcha_match:
            print("❌ Captcha not found")
            return False

        num1 = int(captcha_match.group(1))
        num2 = int(captcha_match.group(2))
        captcha_answer = num1 + num2

        print(f"🧩 Captcha: {num1} + {num2} = {captcha_answer}")

        login_response = session.post(
            f"{BASE_URL}/signin",
            data={
                "username": USERNAME,
                "password": PASSWORD,
                "capt": captcha_answer,
                "remember-me": "on"
            },
            headers={
                "User-Agent": USER_AGENT,
                "Referer": f"{BASE_URL}/login"
            },
            allow_redirects=True,
            timeout=20
        )

        if "x12" in session.cookies:
            print("✅ Login successful")
            return True

        print("❌ Login failed")
        return False

    except requests.RequestException as e:
        print(f"❌ Login error: {e}")
        return False


# ============================================
# SESSION CHECK
# ============================================
def session_is_valid():
    if "x12" not in session.cookies:
        return False

    try:
        response = session.get(
            f"{BASE_URL}/agent/SMSCDRReports",
            headers={"User-Agent": USER_AGENT},
            timeout=20,
            allow_redirects=True
        )

        if "/login" in response.url.lower():
            return False

        if "signin" in response.text.lower() and "username" in response.text.lower():
            return False

        return response.status_code == 200

    except requests.RequestException:
        return False


# ============================================
# ENSURE LOGIN
# ============================================
def ensure_login():
    if session_is_valid():
        return True

    print("⚠️ Session expired")
    print("🔄 Logging in again...")

    session.cookies.clear()

    for attempt in range(1, 4):
        if login():
            return True
        print(f"❌ Login attempt {attempt}/3 failed")
        if attempt < 3:
            time.sleep(5)

    return False


# ============================================
# FETCH SMS
# ============================================
def fetch_sms():
    if not ensure_login():
        return None

    start_date = datetime.now().strftime("%Y-%m-%d")
    end_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

    try:
        response = session.post(
            f"{BASE_URL}/agent/res/exportsmscdr",
            data={
                "fdate1": start_date,
                "fdate2": end_date,
                "frange": "",
                "fclient": "",
                "fnum": "",
                "fcli": ""
            },
            headers={
                "X-Requested-With": "XMLHttpRequest",
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": f"{BASE_URL}/agent/SMSCDRReports",
                "User-Agent": USER_AGENT
            },
            timeout=20
        )

        # Check for session expiration
        if (
            response.status_code in (401, 403)
            or "/login" in response.url.lower()
            or ("signin" in response.text.lower() and "username" in response.text.lower())
        ):
            print("⚠️ Session expired, re-logging...")
            session.cookies.clear()
            if not login():
                return None
            
            # Retry request
            response = session.post(
                f"{BASE_URL}/agent/res/exportsmscdr",
                data={
                    "fdate1": start_date,
                    "fdate2": end_date,
                    "frange": "",
                    "fclient": "",
                    "fnum": "",
                    "fcli": ""
                },
                headers={
                    "X-Requested-With": "XMLHttpRequest",
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Referer": f"{BASE_URL}/agent/SMSCDRReports",
                    "User-Agent": USER_AGENT
                },
                timeout=20
            )

        if response.status_code == 200 and "html" not in response.text.lower():
            return response.text

        print(f"❌ Request failed: {response.status_code}")
        return None

    except requests.RequestException as e:
        print(f"❌ Request error: {e}")
        return None


# ============================================
# PARSE SMS
# ============================================
def parse_sms(data):
    """Parse CSV data and return list of SMS messages"""
    if not data:
        return []

    lines = data.splitlines()
    if not lines:
        return []

    new_records = []

    for line in lines:
        if not line.strip():
            continue

        if re.match(r"^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2},", line):
            parts = line.split(',')
            
            if len(parts) >= 6:
                timestamp = parts[0].strip()
                phone_number = parts[2].strip() if len(parts) > 2 else ""
                sender = parts[3].strip() if len(parts) > 3 else ""
                
                # Build message from columns 4 and 5
                message = ""
                if len(parts) > 4:
                    message = parts[4].strip()
                if len(parts) > 5 and parts[5].strip():
                    if message:
                        message += " " + parts[5].strip()
                    else:
                        message = parts[5].strip()
                
                # Create record in the format: [sender, phone_number, message, timestamp]
                record = [sender, phone_number, message, timestamp]
                
                # Create unique identifier
                sms_id = f"{timestamp}_{sender}_{phone_number}_{message[:20]}"
                
                with sms_lock:
                    if sms_id not in seen_sms:
                        seen_sms.add(sms_id)
                        sms_storage.append(record)
                        new_records.append(record)

    return new_records


# ============================================
# BACKGROUND SMS MONITOR
# ============================================
def monitor_sms():
    """Background thread to continuously fetch SMS"""
    print("🔄 SMS monitor thread started")
    
    # Initial login
    if not login():
        print("❌ Initial login failed")
        return

    while True:
        try:
            data = fetch_sms()
            if data:
                new_records = parse_sms(data)
                if new_records:
                    print(f"📩 Received {len(new_records)} new SMS messages")
                    save_data()
            else:
                print(f"⏳ {datetime.now().strftime('%H:%M:%S')} - No new SMS")
        except Exception as e:
            print(f"❌ Monitor error: {e}")
        
        time.sleep(30)  # Check every 30 seconds


# ============================================
# FLASK API ROUTES
# ============================================

@app.route('/', methods=['GET'])
def home():
    """Home endpoint"""
    return jsonify({
        "service": "SMS Monitor API",
        "status": "running",
        "version": "1.0.0",
        "endpoints": [
            "/api/sms - GET all SMS messages",
            "/api/sms/latest - GET latest SMS messages",
            "/api/sms/search?q=keyword - Search SMS",
            "/api/sms/count - Get total count",
            "/health - Health check"
        ]
    })


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint for Railway"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "sms_count": len(sms_storage),
        "seen_count": len(seen_sms)
    })


@app.route('/api/sms', methods=['GET'])
def get_all_sms():
    """Get all SMS messages"""
    limit = request.args.get('limit', 100, type=int)
    offset = request.args.get('offset', 0, type=int)
    
    with sms_lock:
        sms_list = list(sms_storage)
        # Reverse to show newest first
        sms_list.reverse()
        
        # Apply pagination
        paginated = sms_list[offset:offset+limit]
        
        return jsonify({
            "status": "success",
            "count": len(paginated),
            "total": len(sms_list),
            "data": paginated
        })


@app.route('/api/sms/latest', methods=['GET'])
def get_latest_sms():
    """Get latest SMS messages"""
    count = request.args.get('count', 10, type=int)
    
    with sms_lock:
        sms_list = list(sms_storage)
        # Get latest messages (last ones in the list)
        latest = sms_list[-count:] if len(sms_list) > count else sms_list
        # Reverse to show newest first
        latest.reverse()
        
        return jsonify({
            "status": "success",
            "count": len(latest),
            "data": latest
        })


@app.route('/api/sms/search', methods=['GET'])
def search_sms():
    """Search SMS messages by keyword"""
    query = request.args.get('q', '')
    if not query:
        return jsonify({
            "status": "error",
            "message": "Missing 'q' parameter"
        }), 400
    
    with sms_lock:
        sms_list = list(sms_storage)
        results = []
        
        for sms in sms_list:
            # Search in sender, number, and message
            if (query.lower() in sms[0].lower() or 
                query.lower() in sms[1].lower() or 
                query.lower() in sms[2].lower()):
                results.append(sms)
        
        # Reverse to show newest first
        results.reverse()
        
        return jsonify({
            "status": "success",
            "count": len(results),
            "query": query,
            "data": results
        })


@app.route('/api/sms/count', methods=['GET'])
def get_count():
    """Get total SMS count"""
    with sms_lock:
        return jsonify({
            "status": "success",
            "total_sms": len(sms_storage),
            "seen_sms": len(seen_sms)
        })


@app.route('/api/sms/fetch', methods=['POST'])
def fetch_now():
    """Force fetch new SMS messages"""
    try:
        data = fetch_sms()
        if data:
            new_records = parse_sms(data)
            save_data()
            return jsonify({
                "status": "success",
                "message": f"Fetched {len(new_records)} new SMS messages",
                "new_messages": new_records
            })
        else:
            return jsonify({
                "status": "success",
                "message": "No new messages found"
            })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


# ============================================
# MAIN
# ============================================
if __name__ == "__main__":
    # Load data from files
    load_data()
    
    # Start background monitor thread
    monitor_thread = threading.Thread(target=monitor_sms, daemon=True)
    monitor_thread.start()
    
    # Get port from environment variable for Railway
    port = int(os.environ.get("PORT", 5000))
    
    print(f"🚀 SMS Monitor API running on port {port}")
    print("📊 API endpoints available at:")
    print(f"   http://localhost:{port}/")
    print(f"   http://localhost:{port}/api/sms")
    print(f"   http://localhost:{port}/api/sms/latest")
    print(f"   http://localhost:{port}/api/sms/search?q=keyword")
    print(f"   http://localhost:{port}/health")
    
    # Run Flask app
    app.run(host='0.0.0.0', port=port, debug=False)
