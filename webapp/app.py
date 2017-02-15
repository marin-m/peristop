#!/usr/bin/python3
#-*- encoding: Utf-8 -*-
from flask import Flask, render_template
app = Flask(__name__)

from datetime import timezone, date, timedelta
from mysql.connector import connect
from unidecode import unidecode
from json import load, dumps
from os.path import exists
from struct import unpack
from html import escape
from io import BytesIO
from os import stat
from re import sub

from locale import setlocale, LC_ALL
setlocale(LC_ALL, 'fr_FR.UTF8')

from os.path import dirname, realpath
__import__('sys').path.append(dirname(realpath(__file__)) + '/..')
from config import USER, PASSWORD, COUNTRY

def formatDate(startDate):
    startDate = startDate.replace(tzinfo=timezone.utc).astimezone()
    if startDate.date() == date.today():
        startDate = startDate.strftime('%H:%M')
    elif startDate.date() == date.today() - timedelta(1):
        startDate = 'hier ' + startDate.strftime('%H:%M')
    elif startDate.year != date.today().year:
        startDate = startDate.strftime('%-d %b %Y, %H:%M')
    else:
        startDate = startDate.strftime('%-d %b, %H:%M')
    return startDate

@app.route('/')
@app.route('/top/<duration>/<int:page>')
@app.route('/top/<duration>/<int:page>/<unfilter>')
def top(duration='day', page=1, unfilter='no'):
    unfilter = unfilter in ('yes', '1')
    duration = duration if duration in ['week', 'month', 'day'] else 'day'
    page = max(1, page)
    
    cnx = connect(database='periscope', user=USER, password=PASSWORD, charset='utf8mb4', collation='utf8mb4_unicode_ci')
    db = cnx.cursor()
    
    db.execute('SELECT id, title, country, username, running, startDate, maxViewers, city FROM peri WHERE lang=%s AND startDate > (NOW() - INTERVAL 1 DUR) _FILTER_ ORDER BY maxViewers DESC LIMIT %s,31'.replace('DUR', duration).replace(' _FILTER_', '' if unfilter else ' AND (filter is NULL OR NOT filter)'), (COUNTRY.lower(), (page - 1) * 30))
    
    peris = []
    for bcst, title, country, username, running, startDate, maxViewers, city in db:
        slug = sub(r'\W+', '-', unidecode(title).lower()).strip('-')
        slug = slug or sub(r'\W+', '-', unidecode(username).lower()).strip('-')
        
        city = geo[bcst] if not city and bcst in geo else city
        #if country and country != 'FR':
        #    city += ', %s' % country
        #.replace(' (', ', ').replace(')', '')
        
        peris.append({
            'url': 'https://www.periscope.tv/w/' + bcst if running else '/%s/%s' % (bcst, slug),
            'title': title or None,
            'user': username,
            'running': running,
            'thumb': '/%s.jpg' % bcst,
            'flag': '/flags/24/%s.png' % country.lower() if (country and country != COUNTRY) else None,
            #'flag': None,
            'startdate': formatDate(startDate), # Todo: javascriptify
            'viewers': maxViewers,
            'city': city#.replace(', Suisse', '').replace(', Royaume du Maroc', '')
        })
    
    db.close()
    cnx.close()
    
    return render_template('top.html', duration=duration, page=page, peris=peris, unfilter=unfilter,
                                       stylets=int(stat('static/style.css').st_mtime))

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

strings = {CHAT: '<%s> %s',
JOIN: "* %s joined the chat",
INVITE_FOLLOWERS: '* %s invited followers',
LOCAL_PROMPT_TO_FOLLOW_BROADCASTER: '* %s prompted followers to follow',
LOCAL_PROMPT_TO_SHARE_BROADCAST: '* %s prompted followers to share',
BROADCASTER_BLOCKED_VIEWER: '* %s blocked %s for this message: "%s"',
SUBSCRIBER_SHARED_ON_TWITTER: '* %s shared broadcast on Twitter',
SUBSCRIBER_SHARED_ON_FACEBOOK: '* %s shared broadcast on Facebook',
SCREENSHOT: "* %s took a screenshot"}

def decodeUnk(str_):
    if str_:
        for enc in ['iso-8859-2', 'cp1252', 'sjis_2004']:
            try:
                str_ = str_.encode(enc).decode('utf8')
                break
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass
    return str_

def getChatLog(chat):
    rawlog = ''
    for i in range(len(chat['users'])):
        chat['users'][i][1] = decodeUnk(chat['users'][i][1]) if chat['users'][i][1] else ('@' + chat['users'][i][0] if chat['users'][i][0] else None)
        chat['users'][i][4] = sum(j[0] == HEART and j[1] == i for j in chat['chat'])
    for evt in chat['chat']:
        evtype, sender, ts = evt[:3]
        if not chat['users'][sender][0]:
            sender = '??'
        else:
            sender = '@' + chat['users'][sender][0]
            #sender = chat['users'][sender][1]
        
        if evtype in strings:
            if evtype == JOIN:
                continue
            if evtype == INVITE_FOLLOWERS:
                evt = evt[:-1]
            if evtype == BROADCASTER_BLOCKED_VIEWER:
                if not chat['users'][evt[3]][0]:
                    evt[3] = '??'
                else:
                    evt[3] = '@' + chat['users'][evt[3]][0]
                    #evt[3] = chat['users'][evt[3]][1]
            if evtype in (CHAT, BROADCASTER_BLOCKED_VIEWER):
                pos = 3 + (evtype == BROADCASTER_BLOCKED_VIEWER)
                if not evt[pos]:
                    evt[pos] = ''
                evt[pos] = decodeUnk(evt[pos])
            fmdata = [escape(str(i)) for i in [sender] + evt[3:]]
            fmdata[0] = '<a href="https://www.periscope.tv/%s">%s</a>' % (fmdata[0][1:], fmdata[0])
            rawlog += '<div class="%s">%s</div>\n' % (ts, escape(strings[evtype]) % tuple(fmdata))
        
        elif evtype == LOCATION:
            rawlog += '<div class="%s location %s %s"></div>\n' % (ts, evt[3], evt[4])
        
        elif evtype == HEART:
            #rawlog += '<div class="%s heart %s"></div>\n' % (ts, sender.strip('@'))
            pass
    return rawlog

@app.route('/<bcst>/<slug>')
def view(bcst, slug):
    cnx = connect(database='periscope', user=USER, password=PASSWORD, charset='utf8mb4', collation='utf8mb4_unicode_ci')
    db = cnx.cursor()
    
    db.execute('SELECT title, country, username, startDate, city, latitude, longitude FROM peri WHERE id=%s', (bcst,))
    meta = db.fetchone()
    
    db.close()
    cnx.close()
    if not meta:
        return 'wesh', 404
    
    title, country, username, startDate, city, lat, lng = meta
    displayname, tweetname, profimg, log, chat = None, None, None, None, None
    
    if exists('../storage/chat/%s.json' % bcst):
        with open('../storage/chat/%s.json' % bcst) as fd:
            chat = load(fd)
        displayname, tweetname, profimg = chat['users'][0][1:-1]
        log = getChatLog(chat)
    
    viewers = None

    peri = {
        'title': title,
        'username': username,
        'displayname': decodeUnk(displayname),
        'tweetname': tweetname,
        'profimg': sub('-\d+\.jpg', '-128.jpg', profimg) if profimg else None,
        'flag': '/flags/24/%s.png' % country.lower() if (country and country != COUNTRY) else None,
        'startdate': formatDate(startDate),
        'city': geo[bcst] if not city and bcst in geo else city,
        'timestamps': dumps((chat.get('timestamps') or [[0, chat['chat'][0][2]]]) if chat else None, separators=(',', ':')),
        'orientations': dumps((chat.get('orientations') or [[0, 0]]) if chat else None, separators=(',', ':')),
        'lat': lat,
        'lng': lng,
        'viewers': [{'user': user[0] or '??', 'display': user[1] or '??', 'hearts': user[4]} for user in sorted(chat['users'][1:], key=lambda x: -int(x[4]))] if chat else None
    }
    
    return render_template('view.html', bcst=bcst, peri=peri, chat=log,
                                       stylets=int(stat('static/style.css').st_mtime),
                                       chatts=int(stat('static/chat.js').st_mtime))
