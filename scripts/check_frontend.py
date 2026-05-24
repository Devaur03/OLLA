"""Quick check of frontend serving and step 11 items."""
import asyncio
import httpx
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


async def main():
    async with httpx.AsyncClient(timeout=10, follow_redirects=True) as c:
        try:
            r = await c.get("http://localhost:8000/")
            print(f"Root page: {r.status_code} ({len(r.text)} chars)")
            print(f"First 300 chars: {r.text[:300]}")
        except Exception as e:
            print(f"Root error: {e}")

        try:
            r = await c.get("http://localhost:8000/api/v1/health")
            print(f"Health: {r.json().get('status')}")
        except Exception as e:
            print(f"Health error: {e}")

asyncio.run(main())
