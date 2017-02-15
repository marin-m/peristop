#!/usr/bin/python3
#-*- encoding: Utf-8 -*-
from mysql.connector.errors import IntegrityError
from datetime import datetime, timezone
from threading import Thread, Timer
from mysql.connector import connect
from dateutil.parser import parse
from time import sleep, time
from subprocess import Popen
from io import BytesIO
from PIL import Image

from chat import ChatEngine, tofilter
from replay import downloadReplay
from api import *

from os.path import abspath, dirname
from os import chdir
chdir(dirname(abspath(__file__)) + '/..')
from config import USER, PASSWORD, COUNTRY

popular_running_ids = {}

cnx = connect(database='periscope', user=USER, password=PASSWORD, charset='utf8mb4', collation='utf8mb4_unicode_ci')
db = cnx.cursor()

db.execute('DELETE FROM peri WHERE running=TRUE')
cnx.commit()

min_viewers_for_popular = 9999999

while True:
    print('----- Check') # \n
    
    debut = datetime.now()
    
    db.execute('SELECT COUNT(*) FROM peri WHERE startDate > (NOW() - INTERVAL 1 DAY) AND (filter is NULL OR NOT filter)')
    count_fillable = 30 - min(30, db.fetchone()[0])
    
    if not count_fillable:
        db.execute('SELECT maxViewers FROM peri WHERE startDate > (NOW() - INTERVAL 1 DAY) AND (filter is NULL OR NOT filter) ORDER BY maxViewers DESC LIMIT 29, 1')
        min_viewers_for_popular = db.fetchone()[0]

    # 1. Get periscope top for FR
    
    resp = call('rankedBroadcastFeed', {'languages': [COUNTRY.lower()]})
    bcsts = {i['id'] for i in resp[:100 - len(popular_running_ids)]}

    # 2. Get viewer count for each one

    resp = call('getBroadcasts', {'broadcast_ids': list(bcsts | popular_running_ids.keys())})
    try:
        bcsts2 = {i['id'] for i in resp}
    except:
        print('\n\n!!!', repr(resp), '\n\n')
        continue
    
    # 3. Check for dis/appeared popular broadcasts
    
    for i in set(popular_running_ids):
        if i not in bcsts2:
            print('=> "%s" has been deleted! He had %d' % (i, popular_running_ids[i]))
            del popular_running_ids[i]
            db.execute('UPDATE peri SET running=FALSE WHERE id=%s', (i,))
    
    seekNew = len(popular_running_ids) < 10
    
    for i in sorted(resp, key=lambda x: -(x['n_watching'] + x.get('n_web_watching', 0))):
        nwatch = i['n_watching'] + i.get('n_web_watching', 0)
        
        if i['state'] != 'RUNNING' and i['id'] in popular_running_ids:
            print('=> "%s" (@%s) has stopped running' % (i['status'], i['username']))
            
            endTime = parse(i.get('timedout') or i['end'])
            endTimeTs = endTime.timestamp()
            endTime = endTime.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
            db.execute('UPDATE peri SET running=FALSE, endDate=%s WHERE id=%s', (endTime, i['id']))
            
            if not i['available_for_replay']:
                if time() - endTimeTs < 120:
                    print('==> Unavailable for replay. Waiting...')
                
                else:
                    print('==> Unavailable for replay!')
                    del popular_running_ids[i['id']]
            
            else:
                print('==> Starting retrieval of replay...')
                del popular_running_ids[i['id']]
                Thread(target=downloadReplay, args=(i['id'], i)).start()
        
        elif i['state'] == 'RUNNING' and (count_fillable or nwatch > min_viewers_for_popular) and i['language'] == COUNTRY.lower():
            if i['id'] not in popular_running_ids:
                if not seekNew:
                    continue
                
                if count_fillable:
                    min_viewers_for_popular = min(nwatch, min_viewers_for_popular)
                    count_fillable -= 1
                
                resp = call('getAccessPublic', {'broadcast_id': i['id']})
                if 'hls_url' in resp:
                    assert i['id'] == resp['room_id'] and '/' not in i['id']
                    print('[[D]] Recording %s...' % i['id'])
                    Popen(['ffmpeg', '-y', '-v', 'fatal', '-i', resp['hls_url'], '-bsf:a', 'aac_adtstoasc', '-c', 'copy', 'storage/live/' + i['id'] + '.mp4'])
                    Thread(target=ChatEngine, args=(i['id'], i, resp['endpoint'], resp['access_token'])).start()
                    
                    # Download thumbnail
                    if 'image_url' in i:
                        try:
                            im = Image.open(BytesIO(get(i['image_url']).content))
                            im = im.crop((0, 98, 320, 296)).resize((105, 65), Image.ANTIALIAS)
                            im.save('storage/thumb/' + i['id'] + '.jpg')
                            im.close()
                            del im
                        except:
                            pass
                
                try:
                    db.execute('INSERT INTO peri (id, title, country, lang, username, running, startDate, maxViewers, city, latitude, longitude) VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)', (i['id'], decodeUnk(i['status']), i['iso_code'] or None, i['language'] if i['language'] != 'other' else None, i['username'], True, parse(i['start']).astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S'), nwatch, decodeUnk(i['city']), i.get('ip_lat'), i.get('ip_lng')))
                except IntegrityError: # duplicate from restart
                    pass
                popular_running_ids[i['id']] = nwatch
                
                seekNew = len(popular_running_ids) < 10
            
            elif nwatch > popular_running_ids[i['id']]:
                db.execute('UPDATE peri SET maxViewers=%s WHERE id=%s', (nwatch, i['id']))
                popular_running_ids[i['id']] = nwatch
    
    for i in list(tofilter):
        db.execute('UPDATE peri SET filter=%s WHERE id=%s', (tofilter[i], i))
        del tofilter[i]
    
    cnx.commit()
    
    sleep(max(1, 30 - (datetime.now().timestamp() - debut.timestamp())))
