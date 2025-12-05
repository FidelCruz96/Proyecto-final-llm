import os
import httpx
import asyncio

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

async def list_models():
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={GEMINI_API_KEY}"
    async with httpx.AsyncClient() as client:
        r = await client.get(url)
        print(f"Status: {r.status_code}")
        print(r.text)

if __name__ == "__main__":
    asyncio.run(list_models())
