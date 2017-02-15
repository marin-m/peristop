#!/usr/bin/python3
#-*- encoding: Utf-8 -*-
from traceback import format_exc
from requests import get, post
from json import loads
from time import sleep

from os.path import dirname, realpath
__import__('sys').path.append(dirname(realpath(__file__)) + '/..')
from config import COOKIE

headers = {"User-Agent": "tv.periscope.android/1.3.5 (1900208)",
"package": "tv.periscope.android",
"build": "37aaa50",
"locale": "fr",
"install_id": "1915a41ecaa5f41c-tv.periscope.android",
"os": "5.1.1/22/LMY48T"}

headers2 = {'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/49.0.2623.112 Safari/537.36'}

cookie = 'WGkGYTFQWEVkd1JCeXJqZXZo5aBR3R3o_PzVqgZs7niLEeb_6jYo0XjaOhe-D9Fhag==' # 1PXEdwRByrjevh

def call(endpoint, params={}):
    delay_429 = 2

    while True:
        try:
            if 'Public' not in endpoint:
                resp = post('https://api.periscope.tv/api/v2/' + endpoint, json={
                    **params,
                    'cookie': COOKIE
                }, headers=headers, timeout=20)
            else:
                resp = get('https://api.periscope.tv/api/v2/' + endpoint, params,
                           timeout=20, headers=headers2)
            
            resp.encoding = 'utf-8'
            if not resp.text or resp.text[0] not in '[{':
                if resp.text.lower().strip() == 'not found':
                    return {}
                
                print('[!] %s: Failed with "%s" (%d), retrying in %d...' % (endpoint, repr(resp.text), resp.status_code, delay_429))
                sleep(delay_429)
                
                delay_429 = min(delay_429 * 2, 30)
            else:
                break
        
        except OSError: # name or service not known?
            print(format_exc())
            sleep(5)
    
    return loads(resp.text)

def decodeUnk(str_):
    if str_:
        for enc in ['iso-8859-2', 'cp1252', 'sjis_2004']:
            try:
                str_ = str_.encode(enc).decode('utf8')
                break
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass
    return str_
