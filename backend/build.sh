#!/usr/bin/env bash
# Render runs this on every deploy. Stop at the first failing command.
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate --no-input