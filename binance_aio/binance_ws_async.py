import asyncio
import websockets
import json
import ssl
import logging
from datetime import datetime, timedelta

LOGGER = logging.getLogger(__name__)
# logger.setLevel(logging.INFO)
# logger.addHandler(logging.StreamHandler())

ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE


class BinanceWsAsync(object):
    MAX_SUBSCRIBE_COUNT = 100 # 1024

    def __init__(self):
        # multi-stream should be '/stream' suffix
        self._url = 'wss://stream.binance.com:9443/stream'
        self._ws = None
        self._response_dict = {}
        self._seq_id = 0
        self._running = False
        self._receive_task = None
        self._callbacks = {}
        self._session_start_time = datetime.now()
        self._last_message_time = datetime.now()
        self._last_messages = []

    @property
    def seq_id(self):
        self._seq_id += 1
        return self._seq_id
    
    async def _check_session_time(self):
        while True:
            await asyncio.sleep(600)
            # binance keeps 24hours for single ws session
            if datetime.now() - self._session_start_time > timedelta(hours=23):
                await self.recover()
                break

    async def _send_data(self, payload, blocking):
        if blocking:
            self._response_dict[self._seq_id] = asyncio.Future()
        packet = json.dumps(payload, ensure_ascii=False)

        diff = datetime.now() - self._last_message_time
        delay = timedelta(milliseconds=350) # 5 message per 1 sec but pong response included
        if diff < delay:
            await asyncio.sleep((delay - diff).total_seconds())
        
        if self._ws:
            await self._ws.send(str(packet)) # since binance accepts TEXT not BINARY
        self._last_message_time = datetime.now()
        if blocking:
            LOGGER.info('WAITING seq_id : %d', self._seq_id)
            return await self._response_dict[self._seq_id]
        return True

    async def recover(self):
        self._running = False

        LOGGER.warning('recover')
        if self._receive_task:
            LOGGER.warning('cancel task')
            self._receive_task.cancel()
        
        if self._ws:
            LOGGER.warning('close socket')
            asyncio.create_task(self._ws.close())
            # await self._ws.close()
        LOGGER.warning('rerunning ws')
        self._seq_id = 0
        await self.run()
        LOGGER.warning('subscribe exising list')
        for key in self._callbacks.keys():
            if key.endswith('aggTrade'):
                await self.subscribe_aggtrade(key.split('@')[0], self._callbacks[key])
            elif key.endswith('trade'):
                await self.subscribe_trade(key.split('@')[0], self._callbacks[key])
            elif key.endswith('depth20@100ms'):
                await self.subscribe_orderbook(key.split('@')[0], self._callbacks[key])
        LOGGER.warning('recover done')

    async def list_subscribe(self):
        data = {"method": "LIST_SUBSCRIPTIONS", "id": self.seq_id}
        return await self._send_data(data, True)

    async def subscribe(self, subscribe_type, symbol, callback, blocking):
        if not self._running or len(self._callbacks) > BinanceWsAsync.MAX_SUBSCRIBE_COUNT:
            LOGGER.warning('not running or subscribe count reached to max(%d/%d)',
                            len(self._callbacks),
                            BinanceWsAsync.MAX_SUBSCRIBE_COUNT)
            return False

        symbol = f'{symbol.lower()}@{subscribe_type}'
        # do not check duplicated, below will block subscribe during recover
        # if symbol in self._callbacks:
        #     LOGGER.warning('already subscribe %s, skip subscribe duplicated(maybe agent msg block timeout)', symbol)
        #     return True
        self._callbacks[symbol] = callback
        data = {"method": "SUBSCRIBE", "params": [symbol], "id": self.seq_id}
        LOGGER.info('subscribe %s, id:%d', symbol, self._seq_id)
        return await self._send_data(data, blocking)

    async def unsubscribe(self, subscribe_type, symbol, blocking):
        symbol = f'{symbol.lower()}@{subscribe_type}'
        if symbol in self._callbacks:
            del self._callbacks[symbol]
            if not self._running:
                LOGGER.warning('unsubscribe without sending data(recover) %s', symbol)
                return True
            data = {"method": "UNSUBSCRIBE", "params": [symbol], "id": self.seq_id}
            return await self._send_data(data, blocking)
        LOGGER.warning('%s is not subscribe status', symbol)
        return False        

    async def subscribe_orderbook(self, symbol, callback, blocking=True):
        return await self.subscribe('depth20@100ms', symbol, callback, blocking)

    async def unsubscribe_orderbook(self, symbol, blocking=True):
        return await self.unsubscribe('depth20@100ms', symbol, blocking)

    async def subscribe_aggtrade(self, symbol, callback, blocking=True):
        return await self.subscribe('aggTrade', symbol, callback, blocking)
    
    async def unsubscribe_aggtrade(self, symbol, blocking=True):
        return await self.unsubscribe('aggTrade', symbol, blocking)

    async def subscribe_trade(self, symbol, callback, blocking=True):
        return await self.subscribe('trade', symbol, callback, blocking)
    
    async def unsubscribe_trade(self, symbol, blocking=True):
        return await self.unsubscribe('trade', symbol, blocking)

    async def print_last_messages(self):
        for msg in self._last_messages:
            print(msg)

    async def receive_data(self):
        while self._running:
            try:
                if self._ws:
                    recv = await self._ws.recv()
                    LOGGER.debug('recv %s', recv)
                    data = json.loads(recv)
                    if 'stream' in data and 'data' in data and data['stream'] in self._callbacks:
                        await self._callbacks[data['stream']](data['data'])
                    elif 'id' in data and data['id'] in self._response_dict:
                        LOGGER.info('response ID: %d', data['id'])
                        if 'result' in data:
                            self._response_dict[data['id']].set_result(data['result'])
                        else:
                            self._response_dict[data['id']].set_result(0)
                    
                    self._last_messages.append(data)
                    if len(self._last_messages) > 10:
                        self._last_messages = self._last_messages[-10:]
            except Exception as e:
                LOGGER.error('error(try recover) %s', str(e))
                await self.recover()
                break
        LOGGER.error('stop receive ws data')

    async def run(self):
        # just respond to pong frame from server
        while True:
            try:
                LOGGER.info('try to connect %s', self._url)
                self._ws = await websockets.connect(self._url, ssl=ssl_context, ping_interval=None)
                LOGGER.info('connected')
                break
            except Exception as e:
                LOGGER.error('cannot initiate connection %s', str(e))
                await asyncio.sleep(1)

        self._session_start_time = datetime.now()
        asyncio.create_task(self._check_session_time())
        self._running = True
        self._receive_task = asyncio.create_task(self.receive_data())



