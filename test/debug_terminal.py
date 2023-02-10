import asyncio
import functools
import sys
import os

from binance_aio import BinanceWsAsync
from binance_aio import BinanceWsUserdata


SUBSCRIBE_AGGTRADE = 'aggtrade'
UNSUBSCRIBE_AGGTRADE = 'stop_aggtrade'
SUBSCRIBE_ORDERBOOK = 'orderbook'
UNSUBSCRIBE_ORDERBOOK = 'stop_orderbook'

RENEW = 'renew'

PRINT = 'print'
LIST = 'list'
RECOVER = 'recover'
ASSET = 'asset'
GETORDER = 'getorder'
GETOPEN = 'getopen'
ORDER = 'order'
CANCEL = 'cancel'

class Prompt:
    def __init__(self, loop=None):
        self.loop = loop or asyncio.get_event_loop()
        self.q = asyncio.Queue()
        self.loop.add_reader(sys.stdin, self.got_input)

    def got_input(self):
        asyncio.ensure_future(self.q.put(sys.stdin.readline()), loop=self.loop)

    async def __call__(self, msg, end='\n', flush=False):
        print(msg, end=end, flush=flush)
        return (await self.q.get()).rstrip('\n')


prompt = Prompt()
raw_input = functools.partial(prompt, end='', flush=True)

async def recv_msg(msg):
    print(msg)
    

async def get_input():
    binance_wa = BinanceWsAsync()
    await binance_wa.run()
    binance_wu = BinanceWsUserdata(os.getenv('BINANCE_API_KEY'), os.getenv('BINANCE_API_PASSWORD'))
    binance_wu.subscribe(recv_msg, '1')
    await binance_wu.run()

    while True:
        command = (await raw_input('> ')).strip()
        cmd = command.split(' ')[0]
        args = command.split(' ')[1:]
        if cmd == SUBSCRIBE_AGGTRADE:
            await binance_wa.subscribe_aggtrade(args[0], recv_msg)
        elif cmd == UNSUBSCRIBE_AGGTRADE:
            await binance_wa.unsubscribe_aggtrade(args[0])
        elif cmd == SUBSCRIBE_ORDERBOOK:
            await binance_wa.subscribe_orderbook(args[0], recv_msg)
        elif cmd == UNSUBSCRIBE_ORDERBOOK:
            await binance_wa.unsubscribe_orderbook(args[0], recv_msg)
        elif cmd == LIST:
            print(await binance_wa.list_subscribe())
        elif cmd == PRINT:
            await binance_wa.print_last_messages()
        elif cmd == RECOVER:
            await binance_wa.recover()
            await binance_wu.recover()
        elif cmd == RENEW:
            print(await binance_wu.renew_listen_key())
        elif cmd == ASSET:
            print(await binance_wu.get_asset_list())
        elif cmd == GETOPEN:
            print(await binance_wu.get_open_orders())
        elif cmd == ORDER:
            try:
                print(await binance_wu.new_order('BTCUSDT', 'BUY', 'LIMIT', 
                                                price=15500.99,
                                                quantity=1, timeInForce='GTC'))
            except Exception as e:
                print(str(e))
        elif cmd == CANCEL:
            print(await binance_wu.cancel_order('BTCUSDT', orderId=16888397680))

asyncio.get_event_loop().run_until_complete(get_input())
