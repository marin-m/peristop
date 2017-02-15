# Peristop - Simple Periscope archiver

This application will retrieve or record the most popular Periscope broadcasts on a regular basis, and make these accessible through a handy Flask web interface.

Popular records are recorded live as soon as they reach a viewer thresold for the last 24h, and fully retrieved if replay is available. Chat is recorded too. Video chunk concatenation and thumbnail generation is done using ffmpeg.

Dependencies: Python ≥ 3.5, Flask, Python-Requests, AIOHTTP, PIL, Python-Websocket, Nginx, ffmpeg.

## Usage

You need a MySQL server running. Database schema is created through `crawler/scheme.sql`.

    mysql -u username -p password < crawler/scheme.sql

Fill in a `config.py` file, based on `config.sample.py`.

Run those two scripts in different terminal tabs:

```
$ cd crawler
$ ./peristopd.py
```

```
$ cd webapp
$ ./run.sh
```

Then, launch nginx using the `nginx.conf` script.

```
$ sudo nginx -c nginx.conf
```

You will then access the Periscope interface on [http://localhost:80/](http://localhost:80/) (if you didn't change the port).
