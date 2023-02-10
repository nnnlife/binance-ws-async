import asyncio
import websockets
import json
import ssl
import logging
from datetime import datetime, timedelta

from binance_aio.binance_rest_auth import BinanceRestAuth
from binance_aio.util import cleanNoneValue, encoded_string


LOGGER = logging.getLogger(__name__)


ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

"""
{
  "e": "outboundAccountPosition", //Event type
  "E": 1564034571105,             //Event Time
  "u": 1564034571073,             //Time of last account update
  "B": [                          //Balances Array
    {
      "a": "ETH",                 //Asset
      "f": "10000.000000",        //Free
      "l": "0.000000"             //Locked
    }
  ]
}

{
  "e": "balanceUpdate",         //Event Type
  "E": 1573200697110,           //Event Time
  "a": "BTC",                   //Asset
  "d": "100.00000000",          //Balance Delta
  "T": 1573200697068            //Clear Time
}

"""


class BinanceWsUserdata(BinanceRestAuth):

    def __init__(self, api_key, api_secret):
        # multi-stream should be '/stream' suffix
        super().__init__(api_key, api_secret)
        self._url = 'wss://stream.binance.com:9443/ws/'
        self._ws = None
        self._running = False
        self._receive_task = None
        self._callbacks = {}
        self._session_start_time = datetime.now()
        self._ping_sent_time = datetime.now()
        self._listen_key = ''
    
    async def _check_session_time(self):
        while True:
            await asyncio.sleep(600)
            # binance keeps 24hours for single ws session
            if datetime.now() - self._ping_sent_time > timedelta(minutes=45):
                LOGGER.info('send ping')
                self._ping_sent_time = datetime.now()
                await self.renew_listen_key()
            elif datetime.now() - self._session_start_time > timedelta(hours=23):
                await self.recover()
                break

    async def renew_listen_key(self):
        LOGGER.info('')
        return self._renew_listen_key(self._listen_key)

    async def get_asset_list(self):
        res = self._get_user_asset(recvWindow=60000)
        return res

    async def get_open_orders(self):
        res = self._get_open_orders(recvWindow=60000)
        LOGGER.info('get open order %s', res)
        return res

    async def get_trade_list(self, symbol:str):
        res = self._get_trade_list(symbol, limit=1000)
        LOGGER.info('get trade list')
        return res

    async def query_order(self, symbol: str, orderId:int):
        res = self._get_order(symbol, orderId=orderId, recvWindow=60000)
        LOGGER.info('query order %s', res)
        return res

    async def new_order(self, symbol: str, side: str, type: str, **kwargs):
        LOGGER.info('order %s %s %s %s', symbol, side, type, kwargs)
        try:
            res = self._new_order(symbol, side, type, **kwargs)
        except Exception as e:
            if len(e.args) > 2:
                raise Exception(str(e.args[0]) + ':' + e.args[2])
            else:
                raise Exception(str(e))
        return res

    async def cancel_order(self, symbol: str, **kwargs):
        LOGGER.info('cancel order %s %s', symbol, kwargs)
        try:
            res = self._cancel_order(symbol, **kwargs)
        except Exception as e:
            if len(e.args) > 2:
                raise Exception(str(e.args[0]) + ':' + e.args[2])
            else:
                raise Exception(str(e))
        return res

    async def recover(self):
        self._running = False

        LOGGER.warning('start recover')
        if self._receive_task:
            LOGGER.warning('cancel task')
            self._receive_task.cancel()
        
        if self._ws:
            LOGGER.warning('close socket')
            asyncio.create_task(self._ws.close())
        LOGGER.warning('rerunning ws')
        
        await self.run()
        LOGGER.warning('recover done')

    def subscribe(self, callback, obj):
        self._callbacks[obj] = callback

    def unsubscribe(self, obj):
        if obj in self._callbacks:
            del self._callbacks[obj]
        
    async def receive_data(self):
        while self._running:
            recv = await self._ws.recv()
            try:
                data = json.loads(recv)
                LOGGER.info('userdata recv %s', recv)
                for callback in self._callbacks.values():
                    await callback(data)
            except Exception as e:
                LOGGER.error(str(e))
        LOGGER.error('stop receive ws data')

    async def run(self):
        # just respond to pong frame from server
        while True:
            try:
                self._listen_key = self.new_listen_key()['listenKey']
                LOGGER.info('get listen key %s', self._listen_key)
                LOGGER.info('try to connect %s', self._url + self._listen_key)
                self._ws = await websockets.connect(
                    self._url + self._listen_key, ssl=ssl_context)
                LOGGER.info('connected')
                break
            except Exception as e:
                LOGGER.error('cannot initiate connection %s', str(e))
                await asyncio.sleep(1)
        
        self._session_start_time = datetime.now()
        self._ping_sent_time = datetime.now()
        asyncio.create_task(self._check_session_time())
        self._running = True
        self._receive_task = asyncio.create_task(self.receive_data())


    


