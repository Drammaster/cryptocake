import json, config
import time
import requests
from flask import Flask, request, render_template
from binance.client import Client
from binance.enums import *
from binance.websockets import BinanceSocketManager

bot1_file = open('bot1.json', 'r')
bot1 = json.load(bot1_file)

bot2_file = open('bot2.json', 'r')
bot2 = json.load(bot2_file)

app = Flask(__name__)


trading_bots = [
    bot1,
    bot2
]


#Binance
client = Client(config.API_KEY, config.API_SECRET)


def process_message_trade_long(msg):
    socket_variable = float(msg['p'])
    # print(msg['p'])
    if socket_variable >= float(trading_bots[0]['price']) * trading_bots[0]['take_profit']['target_profit'] or trading_bots[0]['mark'] == True:
        trading_bots[0]['mark'] = True
        if socket_variable > trading_bots[0]['highest']:
            trading_bots[0]['highest'] = socket_variable
        if socket_variable <= float(trading_bots[0]['price']) * trading_bots[0]['take_profit']['target_profit'] or trading_bots[0]['highest'] * trading_bots[0]['take_profit']['trailing_deviation'] >= socket_variable:
            binance_socket_close_long()
            print('Entry price: ', str(trading_bots[0]['price']))
            print('Exit price: ', str(socket_variable))

    if socket_variable < trading_bots[0]['highest']:
        print('Mark reached: ', trading_bots[0]['mark'], 'Highest point: ',trading_bots[0]['highest'])


def process_message_trade_short(msg):
    socket_variable = float(msg['p'])
    # print(msg['p'])
    if socket_variable <= float(trading_bots[1]['price']) / trading_bots[1]['take_profit']['target_profit']:
        trading_bots[1]['mark'] = True
        if socket_variable < trading_bots[1]['highest']:
            trading_bots[1]['highest'] = socket_variable
        if socket_variable >= float(trading_bots[1]['price']) / trading_bots[1]['take_profit']['target_profit'] or trading_bots[1]['highest'] / trading_bots[1]['take_profit']['trailing_deviation'] <= socket_variable:
            binance_socket_close_short()
            print('Entry price: ', str(trading_bots[1]['price']))
            print('Exit price: ', str(socket_variable))
    
    if socket_variable < trading_bots[1]['highest']:
        print('Mark reached: ', trading_bots[1]['mark'], 'Highest point: ',trading_bots[1]['highest'])


# Live trading function
def order_function(side, quantity, symbol, order_type):
    try:
        print(f"sending order {order_type} - {side} {quantity} {symbol}")
        order = client.create_order(symbol=symbol, side=side, type=order_type, quantity=quantity)
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

    order_type = ""

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
        for i in trading_bots_binance:
            if i['exchange_pair'] == data['coinMain'] + data['coinSecondary']:
                order_type = i['order_type']

        # Buy case
        if side == "BUY":
            allowence = 0
            for i in trading_bots_kraken:
                if i['exchange_pair'] == data['ticker']:
                    allowence += i['hold']
                    i['holds'] = True
                
                esp = kraken_request('/0/private/Balance', {
                    "nonce": str(int(1000*time.time()))
                }, kraken_api_key, kraken_api_sec).json()

                assets = esp[data['ticker']]
                price = requests.get('https://api.kraken.com/0/public/Ticker?pair=' + data['ticker']).json()
                quantity = float(((float(assets)*(allowence/100)) / float(price[data['ticker']]['a'][0]))*0.9995)

        # Sell case
        elif side == "SELL":
            for i in trading_bots_kraken:
                if i['exchange_pair'] == data['ticker']:
                    i['holds'] = False
            
            esp = kraken_request('/0/private/Balance', {
                "nonce": str(int(1000*time.time()))
            }, kraken_api_key, kraken_api_sec).json()
            assets = esp[data['ticker']]
            quantity = float(assets)
        
        resp = kraken_request('/0/private/AddOrder', {
            "nonce": str(int(1000*time.time())),
            "ordertype": order_type,
            "type": side.lower(),
            "volume": quantity,
            "pair": data['coinMain'] + data['coinSecondary']
        }, kraken_api_key, kraken_api_sec)
        
        return(resp.json())

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
            time.sleep(2)

        exchange = data['coinMain'] + data['coinSecondary']
        
        step = client.get_symbol_info(exchange)
        stepMin = step['filters'][2]['stepSize']
        # stepMinSize = stepMin[::-1].find('.')
        stepMinSize = 8 - stepMin[::-1].find('1')
        print(stepMinSize)

        if quantity > 0:
            if order_type != "":
                order_response = order_function(side, round(quantity - float(stepMin), stepMinSize), exchange, order_type)
            else:
                order_response = "This bot doesn't exist"
        else:
            order_response = "No allowance"


        if float(client.get_asset_balance(asset=data['coinSecondary'])['free']) > 10 and side == "BUY":
            order()
            return {
                    "code": "success",
                    "message": "order executed"
                }
        else:
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
                binance_socket_start_long()
        
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
                binance_socket_start_short()
        
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
    time.sleep(6)
    binance_socket_close_long()
    return("Socket Closed")

@app.route('/binance_close_short', methods=['POST'])
def binance_socket_short_closer():
    time.sleep(6)
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
@app.route('/bots1', methods=['GET'])
def bots1():
    return(trading_bots[0])

# Return Bots
@app.route('/bots2', methods=['GET'])
def bots2():
    return(trading_bots[1])


# Home page
@app.route('/')
def welcome():
    balances = client.get_account()['balances']

    return render_template('index.html', balances=balances)


@app.route('/moon')
def moon():
    return render_template('moon.html')

@app.route('/product_card')
def product_card():
    return render_template('product_card.html')

@app.route('/svg_animate')
def svg_animate():
    return render_template('svg_animate.html')