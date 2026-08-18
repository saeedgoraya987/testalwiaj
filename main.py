# main.py
from fastapi import FastAPI, Query
import httpx
import re
import random
import string

app = FastAPI()

API_URL = "http://147.135.212.197/crapi/st/viewstats"

def generate_whatsapp_code():
    """Generate a random WhatsApp code format 933-473"""
    return f"{random.randint(100, 999)}-{random.randint(100, 999)}"

def generate_random_suffix():
    """Generate random 10-character suffix like 4sgLq1p5sV6"""
    chars = string.ascii_letters + string.digits
    return ''.join(random.choices(chars, k=10))

def generate_whatsapp_message(phone):
    """Generate a realistic WhatsApp registration message"""
    code = generate_whatsapp_code()
    suffix = generate_random_suffix()
    
    messages = [
        f"# Your WhatsApp code {code} Dont share this code with others {suffix}",
        f"Jou WhatsApp-rekening word op nuwe toestel geregistreer Moenie hierdie kode met enigiemand deel nie Jou WhatsApp-kode {code} {suffix}",
        f"Your WhatsApp Business account is being registered on a new device\n\nDo not share this code with anyone\nYour WhatsApp Business code {code}",
        f"كود واتساب للأعمال الخاص بك ‎{code.replace('-', '')} لا تشاركه مع أحد {suffix}",
        f"# Kode WhatsApp {code} Jangan bagikan kode ini dengan orang lain {suffix}",
        f"# Codigo de WhatsApp Business {code} No compartas este codigo con nadie {suffix}",
        f"# Codigo de WhatsApp {code} No compartas este codigo con nadie {suffix}",
        f"<#> Your WhatsApp account is being registered on a new device\n\nDo not share this code with anyone\nYour WhatsApp code: {code}\n{suffix}",
        f"Your WhatsApp Business code {code}\nDont share this code with others",
        f"كود واتساب للأعمال الخاص بك ‎{code.replace('-', '')}\nلا تشاركه مع أحد"
    ]
    
    return random.choice(messages)

async def fetch_data(token: str):
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{API_URL}?token={token}")
        response.raise_for_status()
        return response.json()

def detect_whatsapp_codes(text):
    """Check if message contains WhatsApp code pattern"""
    # Look for code patterns like 933-473 or 933473
    patterns = [
        r'\b\d{3}-\d{3}\b',  # 933-473
        r'\b\d{6}\b',        # 933473
        r'code\s*[:]?\s*\d{3}-\d{3}',
        r'كود\s*\d{6}',
        r'Kode\s*\d{3}-\d{3}'
    ]
    
    for pattern in patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False

@app.get("/")
async def root(token: str = Query(...)):
    try:
        data = await fetch_data(token)
        
        # Process each message
        processed_data = []
        for item in data:
            if len(item) >= 4:
                service = item[0]
                phone = item[1]
                message = item[2]
                timestamp = item[3]
                
                # If it's WhatsApp with ******, generate realistic message
                if service == "WhatsApp" and message == "*******":
                    # Generate realistic WhatsApp message
                    new_message = generate_whatsapp_message(phone)
                    processed_data.append([service, phone, new_message, timestamp])
                else:
                    processed_data.append([service, phone, message, timestamp])
        
        return processed_data
        
    except Exception as e:
        return {"error": str(e)}
