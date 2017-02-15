document.addEventListener('DOMContentLoaded', function() {
    var chat = document.getElementsByClassName('chat');
    var descr = document.getElementsByClassName('tbltitle')[0];
    var viewers = document.getElementById('viewers');
    
    if(chat.length) {
        chat = chat[0];
        chat.innerHTML = minEmoji(chat.innerHTML);
    }
    descr.innerHTML = minEmoji(descr.innerHTML);
    if(viewers) {
        viewers.innerHTML = minEmoji(viewers.innerHTML);
    }
    
    var map = null;
    if(typeof lat !== 'undefined') {
        map = L.map('viewmap').setView([lat, lng], 15);
        map.attributionControl.setPrefix('<a href="https://www.google.com/maps?q=' + lat + ',' + lng + '&t=k" target="blank" style="font-size: 16px">Voir sur Google Maps</a>');
        
        L.tileLayer('https://api.tiles.mapbox.com/v4/{id}/{z}/{x}/{y}.png?access_token={accessToken}', {
            attribution: '',
            //maxZoom: 18,
            id: 'mapbox.streets',
            accessToken: 'pk.eyJ1IjoibWFwYm94IiwiYSI6ImNpandmbXliNDBjZWd2M2x6bDk3c2ZtOTkifQ._QA7i5Mpkd_m30IGElHziw'
        }).addTo(map);
        
        var precision = function(nb) {
            return Math.pow(10, -((nb + '').split('.')[1] || []).length) / 2;
        }
        var getBounds = function(lat, lng) {
            var latMgn = precision(lat);
            var lngMgn = precision(lng);
            var mgn = Math.min(latMgn, lngMgn);
            
            return [[lat - mgn, lng - mgn], [lat + mgn, lng + mgn]];
        };
        
        var marker = null;
        if(precision(lat) <= 0.0001) {
            marker = L.marker([lat, lng], {
                color: 'red',
                fillColor: '#f03',
                fillOpacity: 0.5
            }).addTo(map);
        }
        else {
            var rect = L.rectangle(getBounds(lat, lng), {
                color: 'red',
                fillColor: '#f03',
                fillOpacity: 0.5
            }).addTo(map);
        }
    }
    
    var onvideo = document.getElementById('onvideo');
    var video = document.getElementsByTagName('video')[0];
    chat = document.getElementsByClassName('chat')[0];
    var evts = chat.children;
    
    var scrolling = false;
    var goal = null;
    var scrollDelay = 100; // ms
    
    var goScroll = function(offst) {
        var oldOffst = chat.scrollTop;
        
        var localGoal = Math.random();
        goal = localGoal;
        
        var debut = performance.now();
        var cb = function() {
            if(goal !== localGoal) {
                return;
            }
            if(performance.now() < debut + 50) {
                chat.scrollTop = oldOffst + (offst - oldOffst) * (performance.now() - debut) / scrollDelay;
                window.requestAnimationFrame(cb);
            }
            else {
                chat.scrollTop = offst;
            }
        };
        window.requestAnimationFrame(cb);
    };
    
    var ts_i = 0;
    var curTs = timestamps[ts_i][1];
    
    var orient_i = -1;

    var i = 0;
    video.ontimeupdate = function() {
        // -> Go through timestamps array
        
        if(timestamps[ts_i] && timestamps[ts_i][0] > video.currentTime) {
            ts_i = 0;
        }
        
        while(timestamps[ts_i + 1] && timestamps[ts_i + 1][0] <= video.currentTime) {
            ts_i++;
        }
        curTs = timestamps[ts_i][1];
        
        // -> Go through orientations array
        
        var origOrient = orient_i;
        
        if(!orientations[orient_i] || orientations[orient_i] && orientations[orient_i][0] > video.currentTime) {
            orient_i = 0;
        }
        
        while(orientations[orient_i + 1] && orientations[orient_i + 1][0] <= video.currentTime) {
            orient_i++;
        }
        if(origOrient !== orient_i) {
            onvideo.className = 'vid' + (orientations[orient_i][1]+'').replace('-','_');
        }
        
        // -> Go through events array
        
        var origI = i;
        
        if(evts[i] && parseFloat(evts[i].className.split(' ')[0]) > video.currentTime + curTs) {
            i = 0;
        }
        
        while(evts[i + 1] && parseFloat(evts[i + 1].className.split(' ')[0]) <= video.currentTime + curTs) {
            i++;
            
            if(evts[i].className.indexOf(' ') !== -1) {
                switch(evts[i].className.split(' ')[1]) {
                    case 'location':
                        lat = parseFloat(evts[i].className.split(' ')[2]);
                        lng = parseFloat(evts[i].className.split(' ')[3]);
                        map.setView([lat, lng]);
                        if(marker) {
                            marker.setLatLng([lat, lng]);
                        }
                        else {
                            rect.setBounds(getBounds(lat, lng));
                        }
                        map.attributionControl.setPrefix('<a href="https://www.google.com/maps?q=' + lat + ',' + lng + '&t=k" target="blank" style="font-size: 16px">Voir sur Google Maps</a>');
                        break;
                    
                    case 'heart':
                        break;
                }
            }
        }
        
        if(i !== origI) {
            goScroll(evts[i].offsetTop - 200 + evts[i].scrollHeight);
        }
    };
});
