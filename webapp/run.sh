#!/bin/sh
uwsgi -s /tmp/uwsgi.sock --chmod-socket=666 --plugin python --py-autoreload 3 -w app:app
