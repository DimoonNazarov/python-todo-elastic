#!/bin/sh

sleep 10

celery -A app.core.celery_app beat --loglevel=info