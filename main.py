import requests
import re
import time
import os
from datetime import datetime, timedelta
import json

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

# Already printed records
seen_sms = set()

# For Railway, we'll use a simple file-based storage for seen_sms
# to persist across restarts
SEEN_FILE = "seen_sms.json"


# ============================================
# PERSIST SEEN SMS
# ============================================
def load_seen_sms():
    """Load seen SMS from file"""
    global seen_sms
    try:
        if os.path.exists(SEEN_FILE):
            with open(SEEN_FILE, 'r') as f:
                seen_sms = set(json.load(f))
            print(f"📂 Loaded {len(seen_sms)} seen SMS records")
    except Exception as e:
        print(f"⚠️ Could not load seen SMS: {e}")
        seen_sms = set()


def save_seen_sms():
    """Save seen SMS to file"""
    try:
        with open(SEEN_FILE, 'w') as f:
            json.dump(list(seen_sms), f)
    except Exception as e:
        print(f"⚠️ Could not save seen SMS: {e}")


# ============================================
# LOGIN
# ============================================
def login():
    print(f"🔐 Logging in as {USERNAME}...")

    try:
        response = session.get(
            f"{BASE_URL}/login",
            headers={
                "User-Agent": USER_AGENT
            },
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

        print(
            f"🧩 Captcha: "
            f"{num1} + {num2} = {captcha_answer}"
        )

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
            headers={
                "User-Agent": USER_AGENT
            },
            timeout=20,
            allow_redirects=True
        )

        if "/login" in response.url.lower():
            return False

        if (
            "signin" in response.text.lower()
            and "username" in response.text.lower()
        ):
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

        print(
            f"❌ Login attempt "
            f"{attempt}/3 failed"
        )

        if attempt < 3:
            time.sleep(5)

    return False


# ============================================
# FETCH CSV
# ============================================
def fetch_sms():

    if not ensure_login():
        return None

    start_date = datetime.now().strftime("%Y-%m-%d")

    end_date = (
        datetime.now() + timedelta(days=1)
    ).strftime("%Y-%m-%d")

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
                "Content-Type":
                    "application/x-www-form-urlencoded",
                "Referer":
                    f"{BASE_URL}/agent/SMSCDRReports",
                "User-Agent": USER_AGENT
            },
            timeout=20
        )

        # ========================================
        # SESSION EXPIRED
        # ========================================
        if (
            response.status_code in (401, 403)
            or "/login" in response.url.lower()
            or (
                "signin" in response.text.lower()
                and "username" in response.text.lower()
            )
        ):

            print("⚠️ Session expired")
            print("🔄 Re-logging in...")

            session.cookies.clear()

            if not login():
                return None

            print("🔁 Retrying SMS request...")

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
                    "X-Requested-With":
                        "XMLHttpRequest",
                    "Content-Type":
                        "application/x-www-form-urlencoded",
                    "Referer":
                        f"{BASE_URL}/agent/SMSCDRReports",
                    "User-Agent": USER_AGENT
                },
                timeout=20
            )

        if (
            response.status_code == 200
            and "html" not in response.text.lower()
        ):
            return response.text

        print(
            f"❌ Request failed: "
            f"{response.status_code}"
        )

        return None

    except requests.RequestException as e:
        print(f"❌ Request error: {e}")
        return None


# ============================================
# PARSE AND PRINT SMS IN REQUIRED FORMAT
# ============================================
def parse_and_print_sms(data):
    """
    Parse CSV data and print SMS in the format:
    [
      ["Google", "22220197732", "G-540150 est votre code de validation Google", "2026-08-28 03:35:17"]
    ]
    """
    if not data:
        return

    lines = data.splitlines()
    if not lines:
        return

    # Track new SMS records
    new_records = []

    for line in lines:
        # Skip empty lines
        if not line.strip():
            continue

        # Check if this is a valid CSV line with timestamp
        if re.match(r"^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2},", line):
            # Parse the CSV line
            parts = line.split(',')
            
            # We expect at least 4 columns
            if len(parts) >= 4:
                # Extract data
                # Column order might vary, but typically:
                # timestamp, sender, number, message, etc.
                timestamp = parts[0].strip()
                
                # Try to find sender (could be in different positions)
                # Based on your format, sender might be in column 1 or 2
                sender = ""
                message = ""
                number = ""
                
                # This is a simplified parsing - adjust based on actual CSV structure
                for i, part in enumerate(parts):
                    part = part.strip()
                    # Look for sender
                    if not sender and part and not part.startswith('+') and not re.match(r'^\d{4}-\d{2}-\d{2}', part):
                        sender = part
                    # Look for message
                    if not message and part and len(part) > 10 and not part.startswith('+'):
                        message = part
                    # Look for number
                    if not number and part and part.startswith('+'):
                        number = part
                    # If we have sender, number, and message, break
                    if sender and number and message:
                        break
                
                # If we didn't find them, use fallback positions
                if not sender and len(parts) > 1:
                    sender = parts[1].strip() if parts[1].strip() else "Unknown"
                if not number and len(parts) > 2:
                    # Try to find a number format
                    for part in parts[2:]:
                        if re.search(r'\+?\d{8,15}', part):
                            number = part.strip()
                            break
                    if not number:
                        number = parts[2].strip() if len(parts) > 2 else ""
                if not message and len(parts) > 3:
                    message = parts[3].strip() if len(parts) > 3 else ""
                
                # Create record in the format: [sender, number, message, timestamp]
                # Your format: ["Google", "22220197732", "G-540150 est votre code de validation Google", "2026-08-28 03:35:17"]
                record = [sender, number, message, timestamp]
                
                # Create a unique identifier for this SMS
                sms_id = f"{timestamp}_{sender}_{number}_{message[:20]}"
                
                # Check if we've seen this SMS before
                if sms_id not in seen_sms:
                    seen_sms.add(sms_id)
                    new_records.append(record)
                    
                    # Print in the required format
                    print("\n📩 NEW SMS:")
                    print(json.dumps([record], indent=2, ensure_ascii=False))
                    
                    # Save seen SMS periodically
                    save_seen_sms()

    return new_records


# ============================================
# MAIN
# ============================================
def main():
    # Load previously seen SMS
    load_seen_sms()
    
    # Initial login
    if not login():
        print("❌ Initial login failed")
        return

    print("🚀 SMS monitor started")
    print(f"📊 Monitoring on Railway - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("⏱️ Checking every 30 seconds\n")

    # For Railway, we should handle graceful shutdown
    try:
        while True:
            try:
                data = fetch_sms()
                if data:
                    parse_and_print_sms(data)
                else:
                    print("⏳ No new SMS data received")
            except Exception as e:
                print(f"❌ Error in main loop: {e}")
            
            # Save seen SMS periodically
            save_seen_sms()
            
            # Wait 30 seconds before next check
            time.sleep(30)
    except KeyboardInterrupt:
        print("\n👋 Shutting down gracefully...")
        save_seen_sms()
        print("💾 Saved seen SMS records")


if __name__ == "__main__":
    main()
