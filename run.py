import asyncio
import sys
import uvicorn

def main():
    if sys.platform == "win32":
        import selectors
        # On Python 3.14, we can provide the loop factory directly or use set_event_loop
        loop = asyncio.SelectorEventLoop(selectors.SelectSelector())
        asyncio.set_event_loop(loop)
    else:
        loop = asyncio.get_event_loop()

    config = uvicorn.Config("app.main:app", host="127.0.0.1", port=8000, reload=False)
    server = uvicorn.Server(config)
    loop.run_until_complete(server.serve())

if __name__ == "__main__":
    main()
