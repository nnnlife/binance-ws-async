import json
import time
import requests
import logging

from binance_aio.util import cleanNoneValue, encoded_string
from .authentication import hmac_hashing
from .error import ClientError, ServerError
from .__version__ import __version__


LOGGER = logging.getLogger('__name__')


class BinanceRestAuth(object):
    def __init__(
        self,
        api_key:str,
        api_secret:str
    ):
        self.base_url = 'https://api.binance.com'
        self.api_key = api_key
        self.api_secret = api_secret
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Content-Type": "application/json;charset=utf-8",
                "User-Agent": "akross/" + __version__,
                "X-MBX-APIKEY": api_key,
            }
        )

    def _get_sign(self, payload):
        return hmac_hashing(self.api_secret, payload)

    def _prepare_params(self, params):
        return encoded_string(cleanNoneValue(params))

    def _dispatch_request(self, http_method):
        return {
            "GET": self.session.get,
            "DELETE": self.session.delete,
            "PUT": self.session.put,
            "POST": self.session.post,
        }.get(http_method, "GET")

    def send_request(self, http_method, url_path, payload=None):
        if payload is None:
            payload = {}
        url = self.base_url + url_path
        LOGGER.debug("url: " + url)
        params = cleanNoneValue(
            {
                "url": url,
                "params": self._prepare_params(payload),
                # "timeout": self.timeout,
                # "proxies": self.proxies,
            }
        )
        response = self._dispatch_request(http_method)(**params)
        LOGGER.debug("raw response from server:" + response.text)
        self._handle_exception(response)

        try:
            data = response.json()
        except ValueError:
            data = response.text
        result = {}

        if len(result) != 0:
            result["data"] = data
            return result

        return data

    def sign_request(self, http_method, url_path, payload=None):
        if payload is None:
            payload = {}
        payload["timestamp"] = int(time.time() * 1000)
        query_string = self._prepare_params(payload)
        payload["signature"] = self._get_sign(query_string)
        return self.send_request(http_method, url_path, payload)

    def _handle_exception(self, response):
        status_code = response.status_code
        if status_code < 400:
            return
        if 400 <= status_code < 500:
            try:
                err = json.loads(response.text)
            except json.JSONDecodeError:
                raise ClientError(
                    status_code, None, response.text, None, response.headers
                )
            error_data = None
            if "data" in err:
                error_data = err["data"]
            raise ClientError(
                status_code, err["code"], err["msg"], response.headers, error_data
            )
        raise ServerError(status_code, response.text)

    def _get_user_asset(self, **kwargs):
        return self.sign_request('POST', '/sapi/v3/asset/getUserAsset', {**kwargs})

    def new_listen_key(self):
        # https://binance-docs.github.io/apidocs/spot/en/#listen-key-spot
        url_path = "/api/v3/userDataStream"
        return self.send_request("POST", url_path)

    def _renew_listen_key(self, listenKey: str):
        # Ping/Keep-alive a ListenKey (USER_STREAM)
        # https://binance-docs.github.io/apidocs/spot/en/#listen-key-spot
        url_path = "/api/v3/userDataStream"
        return self.send_request("PUT", url_path, {"listenKey": listenKey})

    # Margin
    def new_margin_listen_key(self):
        # https://binance-docs.github.io/apidocs/spot/en/#listen-key-margin
        url_path = "/sapi/v1/userDataStream"
        return self.send_request("POST", url_path)

    def _new_order(self, symbol: str, side: str, type: str, **kwargs):
        """New Order (TRADE)

        Post a new order

        POST /api/v3/order

        https://binance-docs.github.io/apidocs/spot/en/#new-order-trade

        Args:
            symbol (str)
            side (str) - 'BUY' or 'SELL'
            type (str) - 'LIMIT', 'MARKET', 'STOP_LOSS', 'STOP_LOSS_LIMIT', 'TAKE_PROFIT', 'TAKE_PROFIT_LIMIT', 'LIMIT_MAKER'
        Keyword Args:
            timeInForce (str, optional) - GTC(Good-till-cancel), IOC(Immediate-or-cancel), FOK
            quantity (float, optional)
            quoteOrderQty (float, optional)
            price (float, optional)
            newClientOrderId (str, optional): A unique id among open orders. Automatically generated if not sent.
            strategyId (int, optional)
            strategyType (int, optional): The value cannot be less than 1000000.
            stopPrice (float, optional): Used with STOP_LOSS, STOP_LOSS_LIMIT, TAKE_PROFIT, and TAKE_PROFIT_LIMIT orders.
            icebergQty (float, optional): Used with LIMIT, STOP_LOSS_LIMIT, and TAKE_PROFIT_LIMIT to create an iceberg order.
            newOrderRespType (str, optional): Set the response JSON. ACK, RESULT, or FULL;
                    MARKET and LIMIT order types default to FULL, all other orders default to ACK.
            recvWindow (int, optional): The value cannot be greater than 60000

            Type
            LIMIT - timeInForce, quantity, price
            MARKET - quantity or quoteOrderQty
        """
        params = {"symbol": symbol, "side": side, "type": type, **kwargs}
        url_path = "/api/v3/order"
        return self.sign_request("POST", url_path, params)


    def _cancel_order(self, symbol: str, **kwargs):
        """Cancel Order (TRADE)

        Cancel an active order.

        DELETE /api/v3/order

        https://binance-docs.github.io/apidocs/spot/en/#cancel-order-trade

        Args:
            symbol (str)
        Keyword Args:
            orderId (int, optional)
            origClientOrderId (str, optional)
            newClientOrderId (str, optional)
            recvWindow (int, optional): The value cannot be greater than 60000
        """
        url_path = "/api/v3/order"
        payload = {"symbol": symbol, **kwargs}
        return self.sign_request("DELETE", url_path, payload)

    def _get_order(self, symbol, **kwargs):
        """Query Order (USER_DATA)

        Check an order's status.

        GET /api/v3/order

        https://binance-docs.github.io/apidocs/spot/en/#query-order-user_data

        Args:
            symbol (str)
        Keyword Args:
            orderId (int, optional)
            origClientOrderId (str, optional)
            recvWindow (int, optional): The value cannot be greater than 60000
        """
        url_path = "/api/v3/order"
        payload = {"symbol": symbol, **kwargs}
        return self.sign_request("GET", url_path, payload)

    def _get_open_orders(self, symbol=None, **kwargs):
        """Current Open Orders (USER_DATA)

        Get all open orders on a symbol.

        GET /api/v3/openOrders

        https://binance-docs.github.io/apidocs/spot/en/#current-open-orders-user_data

        Args:
            symbol (str, optional)
        Keyword Args:
            recvWindow (int, optional): The value cannot be greater than 60000
        """
        url_path = "/api/v3/openOrders"
        payload = {"symbol": symbol, **kwargs}
        return self.sign_request("GET", url_path, payload)

    def _get_trade_list(self, symbol:str, **kwargs):
        """Account Trade List (USER_DATA)

        Get trades for a specific account and symbol.

        GET /api/v3/myTrades

        https://binance-docs.github.io/apidocs/spot/en/#account-trade-list-user_data

        Args:
            symbol (str)
        Keyword Args:
            fromId (int, optional): TradeId to fetch from. Default gets most recent trades.
            orderId (int, optional): This can only be used in combination with symbol
            startTime (int, optional)
            endTime (int, optional)
            limit (int, optional): Default Value: 500; Max Value: 1000
            recvWindow (int, optional): The value cannot be greater than 60000
        ex:
        [
            {
                "symbol": "BNBBTC",
                "id": 28457,
                "orderId": 100234,
                "orderListId": -1, //Unless OCO, the value will always be -1
                "price": "4.00000100",
                "qty": "12.00000000",
                "quoteQty": "48.000012",
                "commission": "10.10000000",
                "commissionAsset": "BNB",
                "time": 1499865549590,
                "isBuyer": true,
                "isMaker": false,
                "isBestMatch": true
            }
        ]
        """
        url_path = "/api/v3/myTrades"
        payload = {"symbol": symbol, **kwargs}
        return self.sign_request("GET", url_path, payload)

if __name__ == '__main__':
    import os
    LOG_FORMAT = ('%(levelname) -10s %(asctime)s %(name) -30s %(funcName) '
                '-35s %(lineno) -5d: %(message)s')
    logging.basicConfig(level=logging.DEBUG, format=LOG_FORMAT)
    ba = BinanceRestAuth(os.getenv('BINANCE_API_KEY'), os.getenv('BINANCE_API_PASSWORD'))
    # print(ba._get_user_asset())
    l = ba._get_trade_list('BTCUSDT', limit=1000)
    for trade in l:
        print(trade)
    
