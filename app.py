import json
import urllib.parse
import hashlib
import hmac
import base64
import time
import requests

from flask import Flask, request, render_template

from binance.client import Client
from binance.enums import *
from binance.streams import BinanceSocketManager
# from binance.websockets import BinanceSocketManager

import config
# import old_config as config

from kucoin.client import Client as Kucoin

app = Flask(__name__)


#Kraken
kraken_api_url = "https://api.kraken.com"
kraken_api_key = config.KRAKEN_API_KEY
kraken_api_sec = config.KRAKEN_API_SECRET

#Binance
client = Client(config.API_KEY, config.API_SECRET)

kucoin_client = Kucoin(config.KUCOIN_API_KEY, config.KUCOIN_API_SECRET, config.KUCOIN_PASSPHRASE)

def get_kraken_signature(urlpath, data, secret):
    postdata = urllib.parse.urlencode(data)
    encoded = (str(data['nonce']) + postdata).encode()
    message = urlpath.encode() + hashlib.sha256(encoded).digest()

    mac = hmac.new(base64.b64decode(secret), message, hashlib.sha512)
    sigdigest = base64.b64encode(mac.digest())
    return sigdigest.decode()

def kraken_request(uri_path, data, kraken_api_key, kraken_api_sec):
    headers = {}
    headers['API-Key'] = kraken_api_key
    # get_kraken_signature() as defined in the 'Authentication' section
    headers['API-Sign'] = get_kraken_signature(uri_path, data, kraken_api_sec)             
    req = requests.post((kraken_api_url + uri_path), headers=headers, data=data)
    return req


def process_message_trade_long(msg):
    socket_variable = float(msg['p'])
    # print(msg['p'])
    if socket_variable >= float(trading_bots[0]['price']) * trading_bots[0]['take_profit']['target_profit'] or trading_bots[0]['mark'] == True:
        trading_bots[0]['mark'] = True
        if socket_variable > trading_bots[0]['highest']:
            trading_bots[0]['highest'] = socket_variable
        if socket_variable <= (float(trading_bots[0]['price']) * trading_bots[0]['take_profit']['target_profit']) * (trading_bots[0]['take_profit']['trailing_deviation'] - 0.001) or trading_bots[0]['highest'] * trading_bots[0]['take_profit']['trailing_deviation'] >= socket_variable:
            binance_socket_close_long()
            print('Entry price: ', str(trading_bots[0]['price']))
            print('Exit price: ', str(socket_variable))

    if socket_variable < trading_bots[0]['highest']:
        print('Mark reached: ', trading_bots[0]['mark'], 'Highest point: ',trading_bots[0]['highest'])


def process_message_trade_short(msg):
    socket_variable = float(msg['p'])
    # print(msg['p'])
    if socket_variable <= float(trading_bots[1]['price']) / trading_bots[1]['take_profit']['target_profit'] or trading_bots[1]['mark'] == True:
        trading_bots[1]['mark'] = True
        if socket_variable < trading_bots[1]['highest']:
            trading_bots[1]['highest'] = socket_variable
        if socket_variable >= (float(trading_bots[1]['price']) / trading_bots[1]['take_profit']['target_profit']) / (trading_bots[1]['take_profit']['trailing_deviation'] - 0.001) or trading_bots[1]['highest'] / trading_bots[1]['take_profit']['trailing_deviation'] <= socket_variable:
            binance_socket_close_short()
            print('Entry price: ', str(trading_bots[1]['price']))
            print('Exit price: ', str(socket_variable))
    
    if socket_variable < trading_bots[1]['highest']:
        print('Mark reached: ', trading_bots[1]['mark'], 'Highest point: ',trading_bots[1]['highest'])


# Live trading function
def order_function_market(side, quantity, symbol, order_type):
    try:
        print(f"sending order {order_type} - {side} {quantity} {symbol}")
        order = client.create_order(symbol=symbol, side=side, type=order_type, quantity=quantity)
    except Exception as e:
        print("an exception occured - {}".format(e))
        return False

    return order

def order_function_limit(side, quantity, symbol, order_type, price):
    try:
        print(f"sending order {order_type} - {side} {quantity} {symbol} at {price}")
        order = client.create_order(symbol=symbol, side=side, type=order_type, quantity=quantity, price=price, timeInForce=TIME_IN_FORCE_GTC)
    except Exception as e:
        print("an exception occured - {}".format(e))
        return False

    return order

def binance_socket_start_long():
    global bm
    bm = BinanceSocketManager(client)
    # start any sockets here, i.e a trade socket
    bm.start_trade_socket(trading_bots[0]['exchange_pair'], process_message_trade_long)
    # then start the socket manager
    bm.start()


def binance_socket_close_long():
    bm.close()
    if trading_bots[0]['has_active_deal'] == True:
        crypto = requests.get("https://api.binance.com/api/v3/exchangeInfo?symbol=" + trading_bots[0]['exchange_pair']).json()
        assets = client.get_asset_balance(asset=crypto['symbols'][0]['baseAsset'])
        quantity = float(assets['free'])
        if trading_bots[1]['has_active_deal'] == True:
            quantity = quantity * (trading_bots[1]['strategy']['base_order_size']/100)
        step = client.get_symbol_info(trading_bots[0]['exchange_pair'])
        stepMin = step['filters'][2]['stepSize']
        stepMinSize = 8 - stepMin[::-1].find('1')
        order_function('SELL', round(quantity - float(stepMin), stepMinSize), trading_bots[0]['exchange_pair'], ORDER_TYPE_MARKET)
        # print('SELL', round(quantity - float(stepMin), stepMinSize), trading_bots[0]['exchange_pair'], ORDER_TYPE_MARKET)
        trading_bots[0]['has_active_deal'] = False

        with open('bot1.json', 'w') as f:
            json.dump(trading_bots[0], f)


def binance_socket_start_short():
    global bm
    bm = BinanceSocketManager(client)
    # start any sockets here, i.e a trade socket
    bm.start_trade_socket(trading_bots[1]['exchange_pair'], process_message_trade_short)
    # then start the socket manager
    bm.start()


def binance_socket_close_short():
    bm.close()
    if trading_bots[1]['has_active_deal'] == True:
        crypto = requests.get("https://api.binance.com/api/v3/exchangeInfo?symbol=" + trading_bots[1]['exchange_pair']).json()
        assets = client.get_asset_balance(asset=crypto['symbols'][0]['quoteAsset'])

        price = requests.get("https://api.binance.com/api/v3/ticker/price?symbol=" + trading_bots[1]['exchange_pair']).json()

        if trading_bots[0]['has_active_deal'] == True:
            quantity = float(((float(assets['free'])*(trading_bots[1]['strategy']['base_order_size']/100)) / float(price['price']))*0.9995)
        else:
            quantity = float((float(assets['free']) / float(price['price']))*0.9995)

        step = client.get_symbol_info(trading_bots[1]['exchange_pair'])
        stepMin = step['filters'][2]['stepSize']
        stepMinSize = 8 - stepMin[::-1].find('1')

        order_function('BUY', round(quantity - float(stepMin), stepMinSize), trading_bots[1]['exchange_pair'], ORDER_TYPE_MARKET)
        # print('BUY', round(quantity - float(stepMin), stepMinSize), trading_bots[1]['exchange_pair'], ORDER_TYPE_MARKET)
        trading_bots[1]['has_active_deal'] = False

        with open('bot2.json', 'w') as f:
            json.dump(trading_bots[1], f)


# Trade API
@app.route('/order', methods=['POST'])
def order():
    # Load data from post
    data = json.loads(request.data)

    time.sleep(data['delay_seconds'])

    # Check for security phrase
    if data['passphrase'] != config.WEBHOOK_PHRASE:
        return {
            "code": "error",
            "message": "Nice try, invalid passphrase"
        }

    # Binance Spot Trade
    if data['platform'].upper() == "BINANCE":

        # Get exchange information from binance
        crypto = requests.get("https://api.binance.com/api/v3/exchangeInfo?symbol=" + data['exchange_pair']).json()
        quoteAsset = crypto['symbols'][0]['quoteAsset']
        baseAsset = crypto['symbols'][0]['baseAsset']

        # Long trade
        if data['side'].upper() == 'LONG':
            assets = client.get_asset_balance(asset=quoteAsset)
            price = requests.get("https://api.binance.com/api/v3/ticker/price?symbol=" + data['exchange_pair']).json()

            quantity = float((float(assets['free']) / float(price['price']))*0.9995)

            if data['amount_type'].upper() == "PERCENTAGE":
                quantity = quantity * (data['amount'] / 100)

            if data['amount_type'].upper() == "BASE CURRENCY":
                quantity = float(data['amount'] / float(price['price']))*0.9995
            
            if data['amount_type'].upper() == "CONTRACTS":
                if quantity > data['amount']:
                    quantity = data['amount']

            step = client.get_symbol_info(data['exchange_pair'])
            stepMin = step['filters'][2]['stepSize']
            stepMinSize = 8 - stepMin[::-1].find('1')
       
        # Short trade
        if data['side'].upper() == 'SHORT':
            assets = client.get_asset_balance(asset=baseAsset)
            price = requests.get("https://api.binance.com/api/v3/ticker/price?symbol=" + data['exchange_pair']).json()

            quantity = float(assets['free'])

            step = client.get_symbol_info(data['exchange_pair'])
            stepMin = step['filters'][2]['stepSize']
            stepMinSize = 8 - stepMin[::-1].find('1')

        if quantity > 0:
            if data['order_type'].upper() == "MARKET":
                order_response = order_function_market(data['action'].upper(), round(quantity - float(stepMin), stepMinSize), data['exchange_pair'], ORDER_TYPE_MARKET)
            if data['order_type'].upper() == "LIMIT":
                order_response = order_function_limit(data['action'].upper(), round(quantity - float(stepMin), stepMinSize), data['exchange_pair'], ORDER_TYPE_LIMIT, str(data['price']))
        else:
            order_response = "Nothing to trade"
        

        if order_response == "Nothing to trade":
            return {
                "code": "error",
                "message": order_response
            }
        elif order_response:
            return {
                "code": "success",
                "message": "order executed"
            }
        else:
            return {
                "code": "error",
                "message": order_response
            }

    # Kraken Spot Trade
    if data['platform'].upper() == "KRAKEN":
        # Request user balances
        user_balance = kraken_request('/0/private/Balance', {
            "nonce": str(int(1000*time.time()))
        }, kraken_api_key, kraken_api_sec)

        pair_info = requests.get('https://api.kraken.com/0/public/AssetPairs?pair=' + data['exchange_pair'])
        quoteAsset = pair_info.json()['result'][data['exchange_pair']]['quote']
        baseAsset = pair_info.json()['result'][data['exchange_pair']]['base']

        
        if data['side'].upper() == "LONG":
            quantity = user_balance.json()['result'][quoteAsset]

            if data['amount_type'].upper() == "PERCENTAGE":
                quantity = (float(quantity) * (data['amount'] / 100)) / float(data['close'])

            if data['amount_type'].upper() == "BASE CURRENCY":
                quantity = float(data['amount'] / float(data['close'])) - 1
            
            if data['amount_type'].upper() == "CONTRACTS":
                if float(quantity) > data['amount']:
                    quantity = data['amount']


        if data['side'].upper() == "SHORT":
            quantity = user_balance.json()['result'][baseAsset]


        resp = kraken_request('/0/private/AddOrder', {
            "nonce": str(int(1000*time.time())),
            "ordertype": data['order_type'].lower(),
            "type": data['action'].lower(),
            "volume": quantity,
            "pair": data['exchange_pair'],
            "price": float(data['price'])
        }, kraken_api_key, kraken_api_sec)

        print(resp.json())
        return(resp.json())

        
    # Kucoin Spot Trade
    if data['platform'].upper() == "KUCOIN":
        # Get account balances
        user_account = kucoin_client.get_accounts()

        baseAsset = ""
        quoteAsset = ""

        # Assign IDs to trade
        for i in user_account:
            print(i)
            if i['currency'] == data['exchange_pair'].split('-')[0] and i['type'] == "trade":
                print(data['exchange_pair'].split('-')[0])
                
                baseAsset = i['id']
            elif i['currency'] == data['exchange_pair'].split('-')[1] and i['type'] == "trade":
                quoteAsset = i['id']
        
        if data['side'].upper() == "LONG":
            buying_amount = kucoin_client.get_account(quoteAsset)
            price = kucoin_client.get_ticker(symbol=data['exchange_pair'])
            buying_amount = float(round(float(buying_amount['balance']) - 1, 2))
            print(buying_amount)
            order = kucoin_client.create_market_order(data['exchange_pair'], Client.SIDE_BUY, funds=buying_amount)

        if data['side'].upper() == "SHORT":
            selling_amount = kucoin_client.get_account(baseAsset)
            selling_amount = float(round(float(selling_amount['balance']) - 0.1, 2))
            print(selling_amount)
            order = kucoin_client.create_market_order(data['exchange_pair'], Client.SIDE_SELL, size=selling_amount)

        print(order)
        return(order)
            

    


@app.route('/ordertesting', methods=['POST'])
def ordertesting():
    # Load data from post
    data = json.loads(request.data)

    time.sleep(data['delay_seconds'])

    # Check for security phrase
    if data['passphrase'] != config.WEBHOOK_PHRASE:
        return {
            "code": "error",
            "message": "Nice try, invalid passphrase"
        }

    for i in trading_bots:
        if i['bot_id'] == data['bot_id'] :
            broker = i['broker']
            exchange_pair = i['exchange_pair']
            strategy = i['strategy']

    crypto = requests.get("https://api.binance.com/api/v3/exchangeInfo?symbol=" + exchange_pair).json()
    quoteAsset = crypto['symbols'][0]['quoteAsset']
    baseAsset = crypto['symbols'][0]['baseAsset']

    #Save buy or sell into side
    side = data['order_action'].upper()

    #If Binance trade
    if broker == 'Binance':

        time.sleep(1)
        if strategy['strategy'] == 'long':

            # Buy case
            if side == "BUY":
                assets = client.get_asset_balance(asset=quoteAsset)
                price = requests.get("https://api.binance.com/api/v3/ticker/price?symbol=" + exchange_pair).json()
                if trading_bots[1]['has_active_deal'] == True:
                    quantity = float(((float(assets['free'])*(strategy['base_order_size']/100)) / float(price['price']))*0.9995)
                else:
                    quantity = float((float(assets['free']) / float(price['price']))*0.9995)
                trading_bots[0]['price'] = price['price']
                
                trading_bots[0]['has_active_deal'] = True
                # if trading_bots[0]["take_profit"]["using"]:
                    # binance_socket_start_long()
        
            step = client.get_symbol_info(exchange_pair)
            stepMin = step['filters'][2]['stepSize']
            stepMinSize = 8 - stepMin[::-1].find('1')

            trading_bots[0]['tokens'] = round(quantity - float(stepMin), stepMinSize)

            if quantity > 0:
                if strategy['order_type'] != "":
                    order_response = order_function(side, round(quantity - float(stepMin), stepMinSize), exchange_pair, strategy['order_type'])
                    # print(side, round(quantity - float(stepMin), stepMinSize), exchange_pair, strategy['order_type'])
                    # order_response = True
                else:
                    order_response = "This bot doesn't exist"
            else:
                order_response = "No allowance"
            
            with open('bot1.json', 'w') as f:
                json.dump(trading_bots[0], f)

            if order_response == "No allowance" or order_response == "This bot doesn't exist":
                return {
                    "code": "error",
                    "message": order_response
                }
            elif order_response:
                return {
                    "code": "success",
                    "message": "order executed"
                }
            else:
                return {
                    "code": "error",
                    "message": "not enought funds"
                }
        

        elif strategy['strategy'] == 'short':
            # Sell case
            if side == "SELL":
                assets = client.get_asset_balance(asset=baseAsset)
                price = requests.get("https://api.binance.com/api/v3/ticker/price?symbol=" + exchange_pair).json()

                if trading_bots[0]['has_active_deal'] == True:
                    quantity = float(assets['free']) * (strategy['base_order_size']/100)
                else:
                    quantity = float(assets['free'])
                
                trading_bots[1]['price'] = price['price']

                trading_bots[1]['has_active_deal'] = True
                # if trading_bots[1]["take_profit"]["using"]:
                    # binance_socket_start_short()
        
            step = client.get_symbol_info(exchange_pair)
            stepMin = step['filters'][2]['stepSize']
            stepMinSize = 8 - stepMin[::-1].find('1')

            trading_bots[1]['tokens'] = round(quantity - float(stepMin), stepMinSize)

            if quantity > 0:
                if strategy['order_type'] != "":
                    order_response = order_function(side, round(quantity - float(stepMin), stepMinSize), exchange_pair, strategy['order_type'])
                    # print(side, round(quantity - float(stepMin), stepMinSize), exchange_pair, strategy['order_type'])
                    # order_response = True
                else:
                    order_response = "This bot doesn't exist"
            else:
                order_response = "No allowance"

            with open('bot2.json', 'w') as f:
                json.dump(trading_bots[1], f)

            if order_response == "No allowance" or order_response == "This bot doesn't exist":
                return {
                    "code": "error",
                    "message": order_response
                }
            elif order_response:
                return {
                    "code": "success",
                    "message": "order executed"
                }
            else:
                return {
                    "code": "error",
                    "message": "not enought funds"
                }


@app.route('/binance_close_long', methods=['POST'])
def binance_socket_long_closer():
    # Load data from post
    data = json.loads(request.data)

    time.sleep(6)

    # Check for security phrase
    if data['passphrase'] != config.WEBHOOK_PHRASE:
        return {
            "code": "error",
            "message": "Nice try, invalid passphrase"
        }

    binance_socket_close_long()
    return("Socket Closed")

@app.route('/binance_close_short', methods=['POST'])
def binance_socket_short_closer():
    # Load data from post
    data = json.loads(request.data)

    time.sleep(6)

    # Check for security phrase
    if data['passphrase'] != config.WEBHOOK_PHRASE:
        return {
            "code": "error",
            "message": "Nice try, invalid passphrase"
        }

    binance_socket_close_short()
    return("Socket Closed")

@app.route('/ordercheck', methods=['POST'])
def ordercheck():
    # Load data from post
    data = json.loads(request.data)

    # Check for security phrase
    if data['passphrase'] != config.WEBHOOK_PHRASE:
        return {
            "code": "error",
            "message": "Nice try, invalid passphrase"
        }
    
    #Save buy or sell into side
    side = data['order_action'].upper()

    if side == "BUY":
        if trading_bots[0]['has_active_deal'] == True and trading_bots[1]['has_active_deal'] == False:
            return('All good here')
        else:
            binance_socket_short_closer()
            requests.post('https://cryptocake.herokuapp.com/ordertesting', json={
                "bot_id": "001",
                "passphrase": "S=]ypG]:oLg2gvfFNr/a2x52j+r|J=O0p]_+6x|GgAm1h;2oegx@tUebD1q<",
                "delay_seconds": 6,
                "order_action": "buy"
            })
            # requests.post('http://127.0.0.1:5000/ordertesting', json={
            #     "bot_id": "001",
            #     "passphrase": "S=]ypG]:oLg2gvfFNr/a2x52j+r|J=O0p]_+6x|GgAm1h;2oegx@tUebD1q<",
            #     "delay_seconds": 4,
            #     "order_action": "buy"
            # })
            time.sleep(3)
            trading_bots[0]['has_active_deal'] = True
            trading_bots[1]['has_active_deal'] = False
            return('Corrected Issue')
    
    
    if side == "SELL":
        if trading_bots[1]['has_active_deal'] == True and trading_bots[0]['has_active_deal'] == False:
            return('All good here')
        else:
            binance_socket_long_closer()
            requests.post('https://cryptocake.herokuapp.com/ordertesting', json={
                "bot_id": "002",
                "passphrase": "S=]ypG]:oLg2gvfFNr/a2x52j+r|J=O0p]_+6x|GgAm1h;2oegx@tUebD1q<",
                "delay_seconds": 6,
                "order_action": "sell"
            })
            # requests.post('http://127.0.0.1:5000/ordertesting', json={
            #     "bot_id": "002",
            #     "passphrase": "S=]ypG]:oLg2gvfFNr/a2x52j+r|J=O0p]_+6x|GgAm1h;2oegx@tUebD1q<",
            #     "delay_seconds": 4,
            #     "order_action": "sell"
            # })
            time.sleep(3)
            trading_bots[1]['has_active_deal'] = True
            trading_bots[0]['has_active_deal'] = False
            return('Corrected Issue')

# Return Bots
# @app.route('/bots1', methods=['GET'])
# def bots1():
#     return(trading_bots[0])

# Return Bots
# @app.route('/bots2', methods=['GET'])
# def bots2():
#     return(trading_bots[1])

@app.route('/binance_futures_fix', methods=['POST'])
def binance_futures_long():
    # Load data from post
    # data = json.loads(request.data)

    # client.futures_change_leverage(symbol="SXPUSDT", leverage=20)
    # client.futures_change_margin_type(symbol="SXPUSDT", marginType='CROSSED')

    resp = client.futures_get_open_orders(symbol='SXPUSDT')

    print(resp)
    return(resp)

    # for i in client.futures_account()['positions']:
    #     if i['symbol'] == "SXPUSDT":
    #         print(i)
    #     if i['symbol'] == "XRPUSDT":
    #         print(i)
    #     if i['symbol'] == "DOTUSDT":
    #         print(i)
    #     if i['symbol'] == "LINKUSDT":
    #         print(i)

@app.route('/binance_futures_trade', methods=['POST'])
def binance_futures_trade():
    # Load data from post
    data = json.loads(request.data)

    # Check for security phrase
    if data['passphrase'] != config.WEBHOOK_PHRASE:
        return {
            "code": "error",
            "message": "Nice try, invalid passphrase"
        }


    count = 0
    open_order = client.futures_get_open_orders(symbol=data['exchange_pair'])
    
    for i in open_order:
        if i['positionSide'] == data['side'].upper():
            count += 1

    if data['pyramid_count'] <= count:
        return("Too many trades already open")

    if data['side'].upper() == 'LONG':
        if data['action'].upper() == "OPEN":
            if data['using_roe'] == True:
                takeProfit = float(data['close']) + ((float(data['close']) * data['profit']) / data['leverage'])
            else:
                takeProfit = float(data['close']) + (float(data['close']) * (data['profit']/100))
            takeProfit = round(takeProfit, 2)

            client.futures_create_order(symbol=data['exchange_pair'], side=SIDE_BUY, positionSide='LONG', type=ORDER_TYPE_MARKET,  quantity=data['volume'], isolated=False)
            client.futures_create_order(symbol=data['exchange_pair'], side=SIDE_SELL, type=FUTURE_ORDER_TYPE_LIMIT, quantity=data['volume'], positionSide='LONG', price=takeProfit, timeInForce=TIME_IN_FORCE_GTC)
        
        if data['action'].upper() == "CLOSE":
            client.futures_cancel_all_open_orders(symbol=data['exchange_pair'])
            client.futures_create_order(symbol=data['exchange_pair'], side=SIDE_SELL, positionSide='LONG', type=ORDER_TYPE_MARKET,  quantity=data['volume'], isolated=False)

    elif data['side'].upper() == 'SHORT':
        if data['action'].upper() == "OPEN":
            if data['using_roe'] == True:
                takeProfit = float(data['close']) - ((float(data['close']) * data['profit']) / data['leverage'])
            else:
                takeProfit = float(data['close']) - (float(data['close']) * (data['profit']/100))
            takeProfit = round(takeProfit, 2)

            client.futures_create_order(symbol=data['exchange_pair'], side=SIDE_SELL, positionSide='SHORT', type=ORDER_TYPE_MARKET,  quantity=data['volume'], isolated=False)
            client.futures_create_order(symbol=data['exchange_pair'], side=SIDE_BUY, type=FUTURE_ORDER_TYPE_LIMIT, quantity=data['volume'], positionSide='SHORT', price=takeProfit, timeInForce=TIME_IN_FORCE_GTC)
        
        if data['action'].upper() == "CLOSE":
            client.futures_cancel_all_open_orders(symbol=data['exchange_pair'])
            client.futures_create_order(symbol=data['exchange_pair'], side=SIDE_BUY, positionSide='SHORT', type=ORDER_TYPE_MARKET,  quantity=data['volume'], isolated=False)

    return("Done")


@app.route('/kraken_trade', methods=['POST'])
def kraken_trade():
    # Load data from post
    data = json.loads(request.data)

    time.sleep(data['delay_seconds'])

    # Check for security phrase
    if data['passphrase'] != config.WEBHOOK_PHRASE:
        return {
            "code": "error",
            "message": "Nice try, invalid passphrase"
        }

    # Request user balances
    user_balance = kraken_request('/0/private/Balance', {
        "nonce": str(int(1000*time.time()))
    }, kraken_api_key, kraken_api_sec)

    if data['side'] == "SELL":
        vol = user_balance.json()['result']['MINA']
        resp = kraken_request('/0/private/AddOrder', {
            "nonce": str(int(1000*time.time())),
            "ordertype": "market",
            "type": "sell",
            "volume": vol,
            "pair": "MINAUSD"
        }, kraken_api_key, kraken_api_sec)

    if data['side'] == "BUY":
        vol = float(user_balance.json()['result']['ZUSD']) / float(data['close']) - 1
        resp = kraken_request('/0/private/AddOrder', {
            "nonce": str(int(1000*time.time())),
            "ordertype": "market",
            "type": "buy",
            "volume": vol,
            "pair": "MINAUSD"
        }, kraken_api_key, kraken_api_sec)    


    print(resp.json())
    return(resp.json())

@app.route('/kraken_account', methods=['POST'])
def kraken_account():
    # Load data from post
    data = json.loads(request.data)

    time.sleep(data['delay_seconds'])

    # Check for security phrase
    if data['passphrase'] != config.WEBHOOK_PHRASE:
        return {
            "code": "error",
            "message": "Nice try, invalid passphrase"
        }
    
    resp = kraken_request('/0/private/Balance', {
        "nonce": str(int(1000*time.time()))
    }, kraken_api_key, kraken_api_sec)

    print(resp.json()) 
    return(resp.json())



@app.route('/kucoin_trade', methods=['POST'])
def kucoin_trade():
    # Load data from post
    data = json.loads(request.data)

    time.sleep(data['delay_seconds'])

    # Check for security phrase
    if data['passphrase'] != config.WEBHOOK_PHRASE:
        return {
            "code": "error",
            "message": "Nice try, invalid passphrase"
        }

    if "SELL" == data["side"]:
        selling_amount = kucoin_client.get_account("610def8ee962a10006593007")
        selling_amount = float(round(float(selling_amount['balance']) - 0.1, 2))
        print(selling_amount)
        order = kucoin_client.create_market_order('ALPACA-USDT', Client.SIDE_SELL, size=selling_amount)

        print(order)
        return(order)

    if "BUY" == data["side"]:
        buying_amount = kucoin_client.get_account("610de221724a380006d7d795")
        price = kucoin_client.get_ticker(symbol="ALPACA-USDT")
        buying_amount = float(round(float(buying_amount['balance']) - 1, 2))
        print(buying_amount)
        order = kucoin_client.create_market_order('ALPACA-USDT', Client.SIDE_BUY, funds=buying_amount)

        print(order)
        return(order)

@app.route('/kucoin_account', methods=['POST'])
def kucoin_account():
    # Load data from post
    data = json.loads(request.data)

    time.sleep(data['delay_seconds'])

    # Check for security phrase
    if data['passphrase'] != config.WEBHOOK_PHRASE:
        return {
            "code": "error",
            "message": "Nice try, invalid passphrase"
        }

    resp = kucoin_client.get_accounts()

    for i in resp:
        if i['currency'] == "ALPACA":
            print(i)
    return(str(len(resp)))

# Home page
# @app.route('/')
# def welcome():
#     balances = client.get_account()['balances']

#     return render_template('index.html', balances=balances, trading_bots=trading_bots)


# @app.route('/moon')
# def moon():
#     return render_template('moon.html')

# @app.route('/product_card')
# def product_card():
#     return render_template('product_card.html')

# @app.route('/svg_animate')
# def svg_animate():
#     return render_template('svg_animate.html')

@app.route('/')
def nowich():
    return render_template('nowich.html')