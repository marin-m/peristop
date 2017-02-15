#!/usr/bin/python3
#-*- encoding: Utf-8 -*-
from asyncio import set_event_loop, new_event_loop, get_event_loop, wait
from aiohttp import TCPConnector, ClientSession
from json import loads, load, JSONDecodeError
from tempfile import NamedTemporaryFile
from requests import post, Session
from subprocess import run, Popen
from time import sleep
from re import sub

from chat import ChatEngine, postProcessChat
from api import *

from resource import getrlimit, setrlimit, RLIMIT_NOFILE
soft, hard = getrlimit(RLIMIT_NOFILE)
setrlimit(RLIMIT_NOFILE, (hard, hard))

async def replayCoro(url, resps, i, client):
    async with client.get(url) as resp:
        if resp.status == 200:
            resps[i] = await resp.read()

def downloadReplay(bcst, info):
    resp = call('getAccessPublic', {'broadcast_id': bcst})
    
    # 1. Download replay info
    
    if 'cookies' not in resp:
        print('==> "%s" (@%s) has been deleted!' % (info['status'], info['username']))
        return
    cookies = {i['Name']: i['Value'] for i in resp['cookies']}
    baseUrl = '/'.join(resp['replay_url'].split('/')[:-1]) + '/chunk_%d.ts'
    
    m3u8 = get(resp['replay_url'], cookies=cookies).text
    nbChunks = int(m3u8.split('chunk_')[-1].split('.')[0]) + 1
    
    # 2. Download parallelly TS chunks and save into mp4
    
    set_event_loop(new_event_loop())
    
    connector = TCPConnector(conn_timeout=10, limit=6)
    resps = [None] * nbChunks
    with ClientSession(connector=connector, cookies=cookies, headers=headers2) as client:
        get_event_loop().run_until_complete(wait([replayCoro(baseUrl % i, resps, i, client) for i in range(nbChunks)]))
    connector.close()
    
    if None in resps:
        print('==> "%s" (@%s) has been deleted!' % (info['status'], info['username']))
        return
    
    with NamedTemporaryFile(suffix='.ts') as tmp:
        for chunk in resps:
            tmp.write(chunk)
        
        tmp.flush()
        run(['ffmpeg', '-y', '-v', 'fatal', '-i', tmp.name, '-bsf:a', 'aac_adtstoasc', '-c', 'copy', 'storage/live/' + bcst + '.mp4'], check=True)
    
    del resps
    
    Popen(['ffmpeg', '-y', '-v', '-8', '-i', 'storage/live/' + bcst + '.mp4', '-vframes', '1', '-ss', '5', '-vf', 'crop=in_w:1/PHI*in_w, scale=-1:65', 'storage/thumb/' + bcst + '.jpg'])
    postProcessChat(bcst)
    
    # 4. Download chat info (other thread?)
    
    cursor = None
    retries = 0
    chat = ChatEngine(bcst, info)
    
    while cursor != '':
        hist = post(resp['endpoint'] + '/chatapi/v1/history', json={
            'access_token': resp['access_token'],
            'cursor': cursor,
            'duration': 9999999,
            'since': 0
        })
        hist.encoding = 'utf-8'
        
        if hist.text.strip() == 'list room events in progress' and retries < 20:
            sleep(5)
            retries += 1
            continue
        retries = 0
        
        try:
            hist = loads(hist.text)
        except JSONDecodeError:
            try:
                hist = loads(sub(r'([\u007f-\uffff])\\*("\}?,)(\\+)', r'\1\3\2\3', hist.text))
            except JSONDecodeError:
                print('=> Retrieval of "%s" (@%s) failed with: %s (%d)' % (info['status'], info['username'], repr(hist.text), hist.status_code))
                return
        
        for msg in hist['messages']:
            chat.parse(msg=msg)
        
        cursor = hist['cursor']
    
    chat.save()
    print('=> Ended up downloading: "%s" (@%s)' % (info['status'], info['username']))
