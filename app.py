import asyncio
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
from binance.streams import BinanceSocketManager, ThreadedWebsocketManager

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
                quantity = (float(quantity) * (data['amount'] / 100)) / float(data['close']) - 0.5

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

            # client.futures_create_order(symbol=data['exchange_pair'], side=SIDE_SELL, type=FUTURE_ORDER_TYPE_TAKE_PROFIT, quantity=data['volume'], positionSide='LONG', price=takeProfit, stopPrice=data['close'], timeInForce=TIME_IN_FORCE_GTC)

            client.futures_create_order(symbol=data['exchange_pair'], side=SIDE_BUY, positionSide='LONG', type=FUTURE_ORDER_TYPE_MARKET,  quantity=data['volume'], isolated=False)
            client.futures_create_order(symbol=data['exchange_pair'], side=SIDE_SELL, type=FUTURE_ORDER_TYPE_LIMIT, quantity=data['volume'], positionSide='LONG', price=takeProfit, timeInForce=TIME_IN_FORCE_GTC)
            
        
        if data['action'].upper() == "CLOSE":
            client.futures_cancel_all_open_orders(symbol=data['exchange_pair'])
            client.futures_create_order(symbol=data['exchange_pair'], side=SIDE_SELL, positionSide='LONG', type=FUTURE_ORDER_TYPE_MARKET,  quantity=data['volume'], isolated=False)

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



@app.route('/binance_sockets', methods=['POST'])
def binance_sockets():
    twm = ThreadedWebsocketManager(tld='us')


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
    return render_template('index.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/projects')
def projects():
    return render_template('projects.html')

@app.route('/contact')
def contact():
    return render_template('contact.html')


@app.route('/project1')
def project1():
    return render_template('work/project-1.html')

@app.route('/project2')
def project2():
    return render_template('work/project-2.html')

@app.route('/project3')
def project3():
    return render_template('work/project-3.html')

@app.route('/project4')
def project4():
    return render_template('work/project-4.html')

@app.route('/project5')
def project5():
    return render_template('work/project-5.html')