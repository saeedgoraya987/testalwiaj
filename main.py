# main.py
from fastapi import FastAPI, Query
import httpx
import random
import string
from typing import Optional

app = FastAPI()

API_URL = "http://147.135.212.197/crapi/st/viewstats"

def generate_whatsapp_code():
    return f"{random.randint(100, 999)}-{random.randint(100, 999)}"

def generate_random_suffix():
    chars = string.ascii_letters + string.digits
    return ''.join(random.choices(chars, k=10))

def generate_whatsapp_message():
    code = generate_whatsapp_code()
    suffix = generate_random_suffix()
    
    messages = [
        f"# Your WhatsApp code {code} Dont share this code with others {suffix}",
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

@app.get("/")
async def root(token: Optional[str] = Query(None)):
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            if token:
                response = await client.get(f"{API_URL}?token={token}")
            else:
                response = await client.get(API_URL)
            
            data = response.json()
            
            # Check if data is a list (successful response with messages)
            if isinstance(data, list) and len(data) > 0:
                processed_data = []
                for item in data:
                    if isinstance(item, list) and len(item) >= 4:
                        service = item[0]
                        phone = item[1]
                        message = item[2]
                        timestamp = item[3]
                        
                        # Replace WhatsApp ******* with realistic messages
                        if service == "WhatsApp" and message == "*******":
                            new_message = generate_whatsapp_message()
                            processed_data.append([service, phone, new_message, timestamp])
                        else:
                            processed_data.append([service, phone, message, timestamp])
                    else:
                        processed_data.append(item)
                
                return processed_data
            else:
                # Return original response (error, no records, etc.)
                return data
            
    except Exception as e:
        # Only return error if there's a connection issue
        return {
            "status": "error",
            "msg": str(e)
        }

@app.get("/health")
async def health():
    return {"status": "ok"}
