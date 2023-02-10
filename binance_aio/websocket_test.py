import asyncio
import websockets
import ssl

ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

async def main():
    ws = await websockets.connect('wss://stream.binance.com:9443/stream', ping_interval=None, ssl=ssl_context)



asyncio.run(main())