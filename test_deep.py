import asyncio
import httpx
import json

async def test_deep_mode():
    url = "http://localhost:8000/api/v1/search/hybrid"
    payload = {
        "query": "Who won the 2024 Super Bowl and what was the final score?",
        "mode": "DEEP"
    }
    headers = {
        "Content-Type": "application/json",
        "X-Workspace-Id": "default"
    }
    
    print("Sending DEEP mode request...")
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(url, json=payload, headers=headers)
        
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print("Answer:")
            print(data.get("answer"))
            print("\nTrace:")
            for t in data.get("routing_trace", []):
                print(f" - {t}")
        else:
            print("Error:")
            print(response.text)

if __name__ == "__main__":
    asyncio.run(test_deep_mode())
