# main.py
from fastapi import FastAPI, Query, HTTPException
import httpx
import re
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
        f"Your WhatsApp Business code {code}\nDont share this code with others",
        f"كود واتساب للأعمال الخاص بك ‎{code.replace('-', '')}\nلا تشاركه مع أحد"
    ]
    
    return random.choice(messages)

@app.get("/")
async def root(token: Optional[str] = Query(None)):
    # Check if token is provided
    if not token:
        return {
            "error": "Missing token parameter",
            "message": "Please provide a token: ?token=YOUR_TOKEN_HERE",
            "example": "https://your-app.railway.app/?token=your_token_here"
        }
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(f"{API_URL}?token={token}")
            
            # Check response status
            if response.status_code != 200:
                return {
                    "error": f"API returned status {response.status_code}",
                    "message": "The token might be invalid or expired",
                    "response": response.text
                }
            
            data = response.json()
            
            # Check for invalid responses
            if data == ["s", "t", "a", "t"]:
                return {
                    "error": "Invalid token",
                    "message": "The token provided is not valid or has expired",
                    "hint": "Please check your token and try again"
                }
            
            if data == ["status", "msg"]:
                return {
                    "error": "API requires valid token",
                    "message": "The token might be missing or incorrect",
                    "hint": "Make sure to use: ?token=YOUR_TOKEN_HERE"
                }
            
            # If data is a list, process it
            if isinstance(data, list):
                processed_data = []
                for item in data:
                    if isinstance(item, list) and len(item) >= 4:
                        service = item[0]
                        phone = item[1]
                        message = item[2]
                        timestamp = item[3]
                        
                        # Replace WhatsApp ******* with realistic messages
                        if service == "WhatsApp" and message == "*******":
                            new_message = generate_whatsapp_message(phone)
                            processed_data.append([service, phone, new_message, timestamp])
                        else:
                            processed_data.append([service, phone, message, timestamp])
                    else:
                        processed_data.append(item)
                
                return processed_data
            else:
                # If data is not a list, return as-is
                return {
                    "original_response": data,
                    "note": "Response format is not the expected list format"
                }
            
    except httpx.TimeoutException:
        return {"error": "Request timeout - API is slow or unreachable"}
    except httpx.ConnectError:
        return {"error": "Cannot connect to API - server might be down"}
    except Exception as e:
        return {"error": str(e)}

@app.get("/health")
async def health():
    return {"status": "ok", "message": "API is running"}

# For development
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
