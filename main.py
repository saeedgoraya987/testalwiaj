# main.py
from fastapi import FastAPI, Query, HTTPException
import httpx
import re
import random
import string

app = FastAPI()

API_URL = "http://147.135.212.197/crapi/st/viewstats"

def generate_whatsapp_code():
    return f"{random.randint(100, 999)}-{random.randint(100, 999)}"

def generate_random_suffix():
    chars = string.ascii_letters + string.digits
    return ''.join(random.choices(chars, k=10))

def generate_whatsapp_message(phone):
    code = generate_whatsapp_code()
    suffix = generate_random_suffix()
    
    messages = [
        f"# Your WhatsApp code {code} Dont share this code with others {suffix}",
        f"Your WhatsApp Business account is being registered on a new device\n\nDo not share this code with anyone\nYour WhatsApp Business code {code}",
        f"كود واتساب للأعمال الخاص بك ‎{code.replace('-', '')} لا تشاركه مع أحد {suffix}",
        f"# Kode WhatsApp {code} Jangan bagikan kode ini dengan orang lain {suffix}",
        f"# Codigo de WhatsApp Business {code} No compartas este codigo con nadie {suffix}",
        f"<#> Your WhatsApp account is being registered on a new device\n\nDo not share this code with anyone\nYour WhatsApp code: {code}\n{suffix}",
        f"Your WhatsApp Business code {code}\nDont share this code with others"
    ]
    
    return random.choice(messages)

@app.get("/")
async def root(token: str = Query(...)):
    try:
        # Try different URL formats
        urls = [
            f"{API_URL}?token={token}",
            f"{API_URL}?key={token}",
            f"{API_URL}/{token}",
            f"http://147.135.212.197/crapi/st/viewstats.php?token={token}",
            f"http://147.135.212.197/crapi/st/viewstats/?token={token}"
        ]
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = None
            for url in urls:
                try:
                    response = await client.get(url)
                    if response.status_code == 200:
                        break
                except:
                    continue
            
            if not response or response.status_code != 200:
                return {"error": "Failed to fetch data", "status_code": response.status_code if response else "No response"}
            
            data = response.json()
            
            # Check if response is ["s","t","a","t"] - meaning invalid token
            if data == ["s", "t", "a", "t"]:
                return {
                    "error": "Invalid token or API endpoint",
                    "message": "The token provided is not valid",
                    "hint": "Check your token and try again"
                }
            
            # Process the data
            processed_data = []
            for item in data:
                if isinstance(item, list) and len(item) >= 4:
                    service = item[0]
                    phone = item[1]
                    message = item[2]
                    timestamp = item[3]
                    
                    if service == "WhatsApp" and message == "*******":
                        new_message = generate_whatsapp_message(phone)
                        processed_data.append([service, phone, new_message, timestamp])
                    else:
                        processed_data.append([service, phone, message, timestamp])
                else:
                    processed_data.append(item)
            
            return processed_data
            
    except httpx.TimeoutException:
        return {"error": "Request timeout - API might be slow or unreachable"}
    except Exception as e:
        return {"error": str(e), "message": "Check if the API URL and token are correct"}
