import hmac
import json, config
import time
import requests
import urllib.parse
import hashlib
import base64
from flask import Flask, request, render_template
from binance.client import Client
from binance.enums import *


app = Flask(__name__)


trading_bots_binance = [
    {
        'name': "Cake Bot",
        'exchange_pair': "CAKEBUSD",
        'crypto': 'CAKE',
        'hold': 100,
        'holds': True,
        'value': 200,
        'profit': 0,
        '7days': 0,
        'order_type': ORDER_TYPE_MARKET
    }    
]

trading_bots_kraken = [
    {
        'name': "Bitcoin Bot",
        'exchange_pair': "MINAUSD",
        'crypto': 'MINA',
        'hold': 100,
        'holds': True,
        'value': 800,
        'profit': 0,
        '7days': 0,
        'order_type': 'market'
    }
]


#Binance
client = Client(config.API_KEY, config.API_SECRET)

#Kraken
kraken_api_url = "https://api.kraken.com"
kraken_api_key = config.KRAKEN_API_KEY
kraken_api_sec = config.KRAKEN_API_SECRET


# Adding bot
def add_bot(new_bot):

    balances = client.get_account()['balances']

    wallet_total = 0 #Wallet total in USD
    for i in balances:
        if i['free'] != "0.00000000":
            if i['free'] != "0.00":
                if i['asset'] != "BUSD":
                    price = requests.get("https://api.binance.com/api/v3/ticker/price?symbol=" + i['asset'] + "BUSD").json()
                    wallet_total += float(price['price']) * float(i['free'])
                else:
                    price = i['free']
                    wallet_total += float(price)
                print(i, price)

    for x in trading_bots_binance:
        x['hold'] = wallet_total * (x['hold'] / 100) #Change bot holds to amount

    wallet_total += new_bot['hold'] #Add new Bots hold

    trading_bots_binance.append(new_bot) #Add new Bot

    for x in trading_bots_binance:
        x['hold'] = (x['hold'] / wallet_total) * 100   #Change bot holds to %


# Live trading function
def order_function(side, quantity, symbol, order_type):
    try:
        print(f"sending order {order_type} - {side} {quantity} {symbol}")
        order = client.create_order(symbol=symbol, side=side, type=order_type, quantity=quantity)
    except Exception as e:
        print("an exception occured - {}".format(e))
        return False

    return order


# Test trading function
def test_order_function(side, quantity, symbol, order_type):
    try:
        print(f"sending order {order_type} - {side} {quantity} {symbol}")
        order = client.create_test_order(symbol=symbol, side=side, type=order_type, quantity=quantity)
    except Exception as e:
        print("an exception occured - {}".format(e))
        return False

    return order


#Get Kraken Signature
def get_kraken_signature(urlpath, data, secret):

    postdata = urllib.parse.urlencode(data)
    encoded = (str(data['nonce']) + postdata).encode()
    message = urlpath.encode() + hashlib.sha256(encoded).digest()

    mac = hmac.new(base64.b64decode(secret), message, hashlib.sha512)
    sigdigest = base64.b64encode(mac.digest())
    return sigdigest.decode()


# Attaches auth headers and returns results of a POST request
def kraken_request(uri_path, data, kraken_api_key, kraken_api_sec):
    headers = {}
    headers['API-Key'] = kraken_api_key
    # get_kraken_signature() as defined in the 'Authentication' section
    headers['API-Sign'] = get_kraken_signature(uri_path, data, kraken_api_sec)             
    req = requests.post((kraken_api_url + uri_path), headers=headers, data=data)
    return req


#Kraken API Balance
@app.route('/kraken', methods=['POST'])
def kraken_balance():
    # Construct the request and print the result
    resp = kraken_request('/0/private/Balance', {
        "nonce": str(int(1000*time.time()))
    }, kraken_api_key, kraken_api_sec)

    return(resp.json()) 


# Home page
@app.route('/')
def welcome():
    balances = client.get_account()['balances']

    return render_template('index.html', balances=balances)


# Bots Page
@app.route('/bots')
def show_bots():

    for i in trading_bots_binance:
        pair_price = requests.get("https://api.binance.com/api/v3/ticker/price?symbol=" + i['exchange_pair']).json()
        token_holding = client.get_asset_balance(asset=i['crypto'])
        i['value'] = round(float(pair_price['price']) * float(token_holding['free']), 2)

    return render_template('bots.html', bots=trading_bots_binance)


# Trade API
@app.route('/order', methods=['POST'])
def order():
    # # Load data from post
    # data = json.loads(request.data)

    # order_type_binance = ORDER_TYPE_MARKET
    # order_type_kraken = "market"
    
    # # Check for security phrase
    # if data['passphrase'] != config.WEBHOOK_PHRASE:
    #     return {
    #         "code": "error",
    #         "message": "Nice try, invalid passphrase"
    #     }

    # side = data['strategy']['order_action'].upper()

    # #Binance Trades
    # if data['exchange'].upper() == 'BINANCE':
    #     # Buy case
    #     if side == "BUY":
    #         allowence = 0
    #         for i in trading_bots_binance:
    #             if i['exchange_pair'] == data['ticker']:
    #                 allowence += i['hold']
    #                 i['holds'] = True
    #             assets = client.get_asset_balance(asset="BUSD")
    #             price = requests.get("https://api.binance.com/api/v3/ticker/price?symbol=" + data['ticker']).json()
    #             quantity = float(((float(assets['free'])*(allowence/100)) / float(price['price']))*0.9995)

    #     # Sell case
    #     elif side == "SELL":
    #         for i in trading_bots_binance:
    #             if i['exchange_pair'] == data['ticker']:
    #                 i['holds'] = False
    #         assets = client.get_asset_balance(asset=data['crypto'])
    #         quantity = float(assets['free'])

    #     exchange = data['ticker']
    #     if data['ticker'] == 'CAKEBUSD':
    #         if quantity > 0:
    #             order_response = order_function(side, round(quantity - 0.001, 3), exchange, order_type_binance)
    #         else:
    #             order_response = True
    #     elif data['ticker'] == 'BTCBUSD':
    #         if quantity > 0:
    #             order_response = order_function(side, round(quantity - 0.000001, 6), exchange, order_type_binance)
    #         else:
    #             order_response = True
    #     elif data['ticker'] == 'BNBBUSD':
    #         if quantity > 0:
    #             order_response = order_function(side, round(quantity - 0.0001, 4), exchange, order_type_binance)
    #         else:
    #             order_response = True


    #     if float(client.get_asset_balance(asset="BUSD")['free']) > 10 and side == "BUY":
    #         order()
    #     else:
    #         if order_response:
    #             return {
    #                 "code": "success",
    #                 "message": "order executed"
    #             }
    #         else:
    #             return {
    #                 "code": "error",
    #                 "message": "not enought funds"
    #             }
    
    # #Kraken Trades
    # elif data['exchange'].upper() == 'KRAKEN':

    #     # Buy case
    #     if side == "BUY":
    #         allowence = 0
    #         for i in trading_bots_kraken:
    #             if i['exchange_pair'] == data['ticker']:
    #                 allowence += i['hold']
    #                 i['holds'] = True
                
    #             esp = kraken_request('/0/private/Balance', {
    #                 "nonce": str(int(1000*time.time()))
    #             }, kraken_api_key, kraken_api_sec).json()

    #             assets = esp[data['ticker']]
    #             price = requests.get('https://api.kraken.com/0/public/Ticker?pair=' + data['ticker']).json()
    #             quantity = float(((float(assets)*(allowence/100)) / float(price[data['ticker']]['a'][0]))*0.9995)

    #     # Sell case
    #     elif side == "SELL":
    #         for i in trading_bots_kraken:
    #             if i['exchange_pair'] == data['ticker']:
    #                 i['holds'] = False
            
    #         esp = kraken_request('/0/private/Balance', {
    #             "nonce": str(int(1000*time.time()))
    #         }, kraken_api_key, kraken_api_sec).json()
    #         assets = esp[data['ticker']]
    #         quantity = float(assets)
        
    #     resp = kraken_request('/0/private/AddOrder', {
    #         "nonce": str(int(1000*time.time())),
    #         "ordertype": order_type_kraken,
    #         "type": side.lower(),
    #         "volume": quantity,
    #         "pair": data['ticker']
    #     }, kraken_api_key, kraken_api_sec)
        
    #     return(resp.json())

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

    #If Kraken trade
    if data['exchange'].upper() == 'KRAKEN':
        pass

    #If Binance trade
    elif data['exchange'].upper() == 'BINANCE':
        for i in trading_bots_binance:
            if i['exchange_pair'] == data['coinMain'] + data['coinSecondary']:
                order_type = i['order_type']

        # Buy case
        if side == "BUY":
            allowence = 0
            for i in trading_bots_binance:
                if i['exchange_pair'] == data['coinMain'] + data['coinSecondary']:
                    allowence += i['hold']
                    i['holds'] = True
                assets = client.get_asset_balance(asset=data['coinSecondary'])
                price = requests.get("https://api.binance.com/api/v3/ticker/price?symbol=" + data['coinMain'] + data['coinSecondary']).json()
                quantity = float(((float(assets['free'])*(allowence/100)) / float(price['price']))*0.9995)

        # Sell case
        elif side == "SELL":
            for i in trading_bots_binance:
                if i['exchange_pair'] == data['coinMain'] + data['coinSecondary']:
                    i['holds'] = False
            assets = client.get_asset_balance(asset=data['coinMain'])
            quantity = float(assets['free'])

        exchange = data['coinMain'] + data['coinSecondary']
        if data['coinMain'] + data['coinSecondary'] == 'CAKEBUSD':
            if quantity > 0:
                order_response = order_function(side, round(quantity - 0.001, 3), exchange, order_type)
            else:
                order_response = True
        # elif data['coinMain'] + data['coinSecondary'] == 'BTCBUSD':
        #     if quantity > 0:
        #         order_response = order_function(side, round(quantity - 0.000001, 6), exchange, order_type)
        #     else:
        #         order_response = True
        # elif data['coinMain'] + data['coinSecondary'] == 'BNBBUSD':
        #     if quantity > 0:
        #         order_response = order_function(side, round(quantity - 0.0001, 4), exchange, order_type)
        #     else:
        #         order_response = True


        if float(client.get_asset_balance(asset=data['coinSecondary'])['free']) > 10 and side == "BUY":
            testing()
            return {
                    "code": "success",
                    "message": "order executed"
                }
        else:
            if order_response:
                return {
                    "code": "success",
                    "message": "order executed"
                }
            else:
                return {
                    "code": "error",
                    "message": "not enought funds"
                }
        

@app.route('/ordertest', methods=['POST'])
def ordertest():
    # Load data from post
    data = json.loads(request.data)

    order_type = ORDER_TYPE_MARKET
    
    # Check for security phrase
    if data['passphrase'] != config.WEBHOOK_PHRASE:
        return {
            "code": "error",
            "message": "Nice try, invalid passphrase"
        }

    # Check for buy or for sell
    side = data['strategy']['order_action'].upper()

    
    # Buy case
    if side == "BUY":
        allowence = 0
        for i in trading_bots_binance:
            if i['exchange_pair'] == data['ticker'] and i['holds'] == False:
                allowence += i['hold']
                i['holds'] = True
            assets = client.get_asset_balance(asset="BUSD")
            price = requests.get("https://api.binance.com/api/v3/ticker/price?symbol=" + data['ticker']).json()
            quantity = float(((float(assets['free'])*(allowence/100)) / float(price['price']))*0.9995)


    # Sell case
    elif side == "SELL":
        for i in trading_bots_binance:
            if i['exchange_pair'] == data['ticker']:
                i['holds'] = False
        assets = client.get_asset_balance(asset=data['crypto'])
        quantity = float(assets['free'])


    exchange = data['ticker']
    if data['ticker'] == 'CAKEBUSD':
        if quantity > 0:
            order_response = test_order_function(side, round(quantity - 0.001, 3), exchange, order_type)
        else:
            order_response = True
    elif data['ticker'] == 'BTCBUSD':
        if quantity > 0:
            order_response = test_order_function(side, round(quantity - 0.000001, 6), exchange, order_type)
        else:
            order_response = True
    elif data['ticker'] == 'BNBBUSD':
        if quantity > 0:
            order_response = test_order_function(side, round(quantity - 0.0001, 4), exchange, order_type)
        else:
            order_response = True


    if order_response == {}:
        return {
            "code": "success",
            "message": "order executed"
        }
    elif order_response:
        return {
            "code": "error",
            "message": "Bot already traded in"
        }


# Parallax page
@app.route('/parallax')
def parallax():
    return render_template('parallax.html')


@app.route('/managebot', methods=['POST'])
def manage_bot():
    # Load data from post
    data = json.loads(request.data)


    # Check request
    if data['task'] == 'update':
        allowance = 100
        for i in trading_bots_binance:
            if i['name'] == data['name']:
                i['hold'] = data['hold']
                allowance -= data['hold']

        for i in trading_bots_binance:
            if i['name'] != data['name']:
                i['hold'] = int(allowance / (len(trading_bots_binance) - 1))


    elif data['task'] == 'create':
        name = data['name']
        exchange_pair = data['exchange_pair']
        hold = data['hold']

        new_bot = {
            'name': name,
            'exchange_pair': exchange_pair,
            'hold': hold,
            'holds': False
        }

        add_bot(new_bot)


    return({
        'Message': "success",
        'Bots': trading_bots_binance
    })


@app.route('/stoploss', methods=['POST'])
def stoploss():
    
    data = client.get_symbol_info('CAKEBUSD')



    return (data)

@app.route('/ordertesting', methods=['POST'])
def testing():

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

    #If Kraken trade
    if data['exchange'].upper() == 'KRAKEN':
        pass

    #If Binance trade
    elif data['exchange'].upper() == 'BINANCE':
        for i in trading_bots_binance:
            if i['exchange_pair'] == data['coinMain'] + data['coinSecondary']:
                order_type = i['order_type']

        # Buy case
        if side == "BUY":
            allowence = 0
            for i in trading_bots_binance:
                if i['exchange_pair'] == data['coinMain'] + data['coinSecondary']:
                    allowence += i['hold']
                    i['holds'] = True
                assets = client.get_asset_balance(asset=data['coinSecondary'])
                price = requests.get("https://api.binance.com/api/v3/ticker/price?symbol=" + data['coinMain'] + data['coinSecondary']).json()
                quantity = float(((float(assets['free'])*(allowence/100)) / float(price['price']))*0.9995)

        # Sell case
        elif side == "SELL":
            for i in trading_bots_binance:
                if i['exchange_pair'] == data['coinMain'] + data['coinSecondary']:
                    i['holds'] = False
            assets = client.get_asset_balance(asset=data['coinMain'])
            quantity = float(assets['free'])

        exchange = data['coinMain'] + data['coinSecondary']
        if data['coinMain'] + data['coinSecondary'] == 'CAKEBUSD':
            if quantity > 0:
                order_response = order_function(side, round(quantity - 0.001, 3), exchange, order_type)
            else:
                order_response = True
        # elif data['coinMain'] + data['coinSecondary'] == 'BTCBUSD':
        #     if quantity > 0:
        #         order_response = order_function(side, round(quantity - 0.000001, 6), exchange, order_type)
        #     else:
        #         order_response = True
        # elif data['coinMain'] + data['coinSecondary'] == 'BNBBUSD':
        #     if quantity > 0:
        #         order_response = order_function(side, round(quantity - 0.0001, 4), exchange, order_type)
        #     else:
        #         order_response = True


        if float(client.get_asset_balance(asset=data['coinSecondary'])['free']) > 10 and side == "BUY":
            testing()
            return {
                    "code": "success",
                    "message": "order executed"
                }
        else:
            if order_response:
                return {
                    "code": "success",
                    "message": "order executed"
                }
            else:
                return {
                    "code": "error",
                    "message": "not enought funds"
                }