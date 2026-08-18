# main.py
from fastapi import FastAPI, Query
import httpx
import hashlib
from typing import Optional

app = FastAPI()

API_URL = "http://147.135.212.197/crapi/st/viewstats"

def generate_consistent_whatsapp_message(phone, original_message):
    """
    Generate consistent WhatsApp messages based on phone number
    Same phone number always gets the same message
    """
    # Use phone number to generate consistent codes
    hash_obj = hashlib.md5(phone.encode())
    hash_hex = hash_obj.hexdigest()
    
    # Generate consistent 6-digit code
    code_int = int(hash_hex[:8], 16) % 900 + 100
    code = f"{code_int}-{code_int + 100}"
    
    # Generate consistent suffix (10 chars)
    suffix_chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
    suffix = ''
    for i in range(10):
        idx = int(hash_hex[i:i+2], 16) % len(suffix_chars)
        suffix += suffix_chars[idx]
    
    # Use phone number to deterministically pick a template
    template_index = int(hash_hex[:4], 16) % 9
    
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
    
    return messages[template_index]

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
                        
                        # Replace WhatsApp ******* with consistent messages
                        if service == "WhatsApp" and message == "*******":
                            new_message = generate_consistent_whatsapp_message(phone, message)
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
        return {
            "status": "error",
            "msg": str(e)
        }

@app.get("/health")
async def health():
    return {"status": "ok"}
