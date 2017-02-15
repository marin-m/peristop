#!/usr/bin/python3
#-*- encoding: Utf-8 -*-
from websocket._exceptions import WebSocketConnectionClosedException
from collections import OrderedDict, Counter
from json import loads, load, dump, dumps
from websocket import WebSocketApp
from traceback import format_exc
from unidecode import unidecode
from subprocess import Popen
from threading import Timer
from h264 import H264Reader
from time import time
from re import sub
from api import *

from logging import getLogger, DEBUG
getLogger('websocket').setLevel(DEBUG)

import ssl
ssl_defaults = ssl.get_default_verify_paths()
sslopt_ca_certs = {'ca_certs': ssl_defaults.cafile}

tofilter = {}

CHAT = 1
CONTROL = 2
AUTH = 3

CHAT = 1
HEART = 2
JOIN = 3
LOCATION = 4
BROADCAST_ENDED = 5
INVITE_FOLLOWERS = 6
BROADCAST_STARTED_LOCALLY = 7
BROADCASTER_UPLOADED_REPLAY = 8
TIMESTAMP = 9
LOCAL_PROMPT_TO_FOLLOW_BROADCASTER = 10
LOCAL_PROMPT_TO_SHARE_BROADCAST = 11
BROADCASTER_BLOCKED_VIEWER = 12
SUBSCRIBER_SHARED_ON_TWITTER = 13
SUBSCRIBER_BLOCKED_VIEWER = 14
SUBSCRIBER_SHARED_ON_FACEBOOK = 15
SCREENSHOT = 16


class ChatEngine:
    def __init__(self, bcst, info, endpoint=None, token=None):
        self.bcst = bcst
        
        self.chat = []
        
        self.users = OrderedDict()
        self.users[info['user_id']] = (info['username'], info['user_display_name'], info.get('twitter_username'), info.get('profile_image_url'), 0)
        
        # Connect to websocket
        if endpoint:
            self.endpoint = endpoint
            self.token = token
            
            print('[[D]] Connecting %s...' % self.bcst)
            self.timeout = None
            self.connect()
            if self.timeout:
                self.timeout.cancel()
        
        else:
            print('[[D]] Init DL %s...' % self.bcst)
            self.getViewers()
        
        print('[[D]] Closed ChatEngine thread %s' % self.bcst)
    
    def getUser(self, userid):
        viewer = call('getUserPublic', {'user_id': userid})
        
        if 'user' in viewer:
            viewer = viewer['user']
            
            if viewer.get('profile_image_urls'):
                small_pic = min(viewer['profile_image_urls'], key=lambda i: i['width'])['ssl_url']
            else:
                small_pic = None
            
            self.users[viewer['id']] = (viewer['username'], viewer['display_name'], viewer['twitter_screen_name'], small_pic, 0)
            return True
        return False
    
    def getViewers(self):
        # Download viewers info
        
        viewers = call('getBroadcastViewers', {'broadcast_id': self.bcst})
        
        for viewer in viewers['live'] + viewers['replay']:
            if viewer.get('profile_image_urls'):
                small_pic = min(viewer['profile_image_urls'], key=lambda i: i['width'])['ssl_url']
            else:
                small_pic = None
            
            self.users[viewer['id']] = (viewer['username'], viewer['display_name'], viewer['twitter_screen_name'], small_pic, viewer['n_hearts_given'])
        
        if not viewers['replay']:
            self.nbViewersLive = len(viewers['live'])
    
    def ratamioche(self):
        print('[[D]] Asking close %s...' % self.bcst)
        self.ws.close()
        #self.close()
    
    def connect(self):
        self.ended = True
        self.hadCtrl = False
        self.reconnectTime = time()
        
        if self.timeout:
            self.timeout.cancel()
        
        ws = WebSocketApp(self.endpoint.replace('https:','wss:') + '/chatapi/v1/chatnow',
                          on_open = self.authentify,
                          on_message = self.parse,
                          on_error = self.error,
                          on_close = self.close, header={'User-Agent': 'ChatMan/1 (Android) '})
        
        self.timeout = Timer(80, self.ratamioche)
        self.timeout.daemon = True
        self.timeout.start()
        
        self.ws = ws
        ws.run_forever(sslopt=sslopt_ca_certs, ping_timeout=90)
    
    def authentify(self, ws):
        ws.send(dumps({'payload': dumps({'access_token': self.token}), 'kind': AUTH}))
        ws.send(dumps({'payload': dumps({'body': dumps({'room': self.bcst}), 'kind': CHAT}), 'kind': CONTROL}))
        
        if len(self.users) <= 1:
            self.getViewers()
        
        self.ended = False
        print('[[D]] Have logged %s...' % self.bcst)
    
    def parse(self, ws=None, msg=None):
        if type(msg) == str:
            msg = loads(msg)
        if msg['kind'] == CONTROL:
            self.hadCtrl = True
            return
        
        msg = loads(msg['payload'])
        body = loads(msg['body'])
        sender = msg['sender']
        
        if sender['user_id'] not in self.users:
            if sender.get('username') or not self.getUser(sender['user_id']):
                self.users[sender['user_id']] = (sender.get('username'), sender.get('display_name'), sender.get('twitter_username'), sender.get('profile_image_url'), 0)
        
        senderId = list(self.users).index(sender['user_id'])
        
        iOSorAndroid = bool(body['timestamp'] >> 33)
        
        tsServer = msg['timestamp'] / 1000000000
        tsClient = body['timestamp'] / 1000 if iOSorAndroid else body['timestamp']
        tsLive = (body['ntpForLiveFrame'] / 0x100000000 - 2208988800) if body.get('ntpForLiveFrame') else None
        tsBcster = (body['ntpForBroadcasterFrame'] / 0x100000000 - 2208988800) if body.get('ntpForBroadcasterFrame') else None
        tsOfDisplay = tsBcster or tsLive or tsClient
        
        evdata = []
        if body['type'] == CHAT:
            evdata = [body['body']]
        elif body['type'] == LOCATION:
            evdata = [body['lat'], body['lng'], body.get('heading')]
        elif body['type'] == INVITE_FOLLOWERS:
            evdata = [body['invited_count']]
        elif body['type'] == BROADCASTER_BLOCKED_VIEWER:
            if body['broadcasterBlockedRemoteID'] not in self.users:
                self.users[body['broadcasterBlockedRemoteID']] = (body['broadcasterBlockedUsername'], None, None, None, 0)
            
            evdata = [list(self.users).index(body['broadcasterBlockedRemoteID']), body.get('broadcasterBlockedMessageBody')]
        
        elif body['type'] == BROADCAST_ENDED and ws:
            self.ended = True
            self.ratamioche()
        
        self.chat.append([body['type'], senderId, tsOfDisplay] + evdata)

    def error(self, ws, error):
        if type(error) != WebSocketConnectionClosedException:
            print('[[D]] Errored %s...' % self.bcst)
            self.ended = True

    def close(self, ws=None):
        print('[[D]] Closed %s...' % self.bcst)
        if not self.ended and time() - 74 < self.reconnectTime < time() - 10 and self.hadCtrl:
            self.connect()
        elif len(self.users) > 1:
            print('[[D]] Saving %s...' % self.bcst)
            self.save()
    
    def save(self):
        with open('storage/chat/%s.json' % self.bcst, 'w') as fd:
            dump({
                'users': list(self.users.values()),
                'chat': sorted(self.chat, key=lambda i: i[2]),
                'nbViewersLive': getattr(self, 'nbViewersLive', len(self.users) - 1)
            }, fd, ensure_ascii=False, separators=(',', ':'))
        
        print('[[D]] Dumped %s' % self.bcst)
        
        tmr = Timer(30, postProcessChat, (self.bcst,))
        tmr.start()
        #postProcessChat(self.bcst)

def postProcessChat(bcst, retry=False):
    try:
        with open('storage/chat/%s.json' % bcst) as fd:
            chat = load(fd)
        
        meta = H264Reader(bcst).meta
        
        with open('storage/chat/%s.json' % bcst) as fd:
            chat = load(fd)
        chat['timestamps'] = meta['timestamps'].copy()
        chat['orientations'] = meta['orientations'].copy()
        
        with open('storage/chat/%s.json' % bcst, 'w') as fd:
            dump(chat, fd, ensure_ascii=False, separators=(',', ':'))
        
        # Badword filter
        bad = set('elppin pin ssa boob xes evelne toh luc krewt ennob elleb notet nies ertnom'[::-1].split(' '))
        common = list('me sa est toi ca pas on t les en ton ou c qui peri un une le elle ta des je vous a de la va tu se ce pour lui il t\'es c\'est et te tes t\'a t\'as'.split(' '))
        
        with open('storage/chat/%s.json' % bcst) as fd:
            chat = load(fd)
        
        words = []
        for msg in chat['chat']:
            if msg[0] == 1: # CHAT
                msg = decodeUnk(msg[3])
                for word in msg.split(' '):
                    word = sub('[.!?]', '', unidecode(word).lower()).rstrip('s')
                    if word and word[0] != '@':
                        words.append(word)
        words = dict(Counter(words))
        
        for j in common:
            if j in words:
                del words[j]
        
        words = sorted(words, key=lambda x: (words[x], x))
        letop = bad.intersection(words[-10:])

        global tofilter
        tofilter[bcst] = bool(letop)
    
    except Exception:
        if not retry:
            Timer(20 * 60, postProcessChat, (bcst, True)).start()
        
        print(format_exc())
