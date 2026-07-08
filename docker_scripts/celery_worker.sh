#!/bin/sh

sleep 10

celery -A app.core.celery_app worker --loglevel=info