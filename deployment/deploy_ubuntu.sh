#!/usr/bin/env bash
set -euo pipefail

sudo mkdir -p /opt/akdevicelock /etc/akdl/tls
sudo chown -R ubuntu:www-data /opt/akdevicelock
tar -xzf /tmp/akdl_app.tar.gz -C /opt/akdevicelock

sudo mv -f /tmp/command_signing_key.pem /etc/akdl/command_signing_key.pem
sudo mv -f /tmp/akdevicelock.apk /etc/akdl/akdevicelock.apk
CERT_SHA256="$(tr -d '\r\n' < /tmp/apk_cert_sha256.txt)"
sudo chown ubuntu:www-data /etc/akdl/command_signing_key.pem /etc/akdl/akdevicelock.apk
sudo chmod 600 /etc/akdl/command_signing_key.pem
sudo chmod 644 /etc/akdl/akdevicelock.apk

if [ ! -f /etc/akdl/tls/fullchain.pem ]; then
  sudo openssl req -x509 -nodes -newkey rsa:2048 -days 3650 \
    -keyout /etc/akdl/tls/privkey.pem \
    -out /etc/akdl/tls/fullchain.pem \
    -subj "/CN=dpc.apinfotechandcybersolution.com" \
    -addext "subjectAltName=DNS:dpc.apinfotechandcybersolution.com,IP:3.106.214.246" 2>/dev/null
  sudo chmod 600 /etc/akdl/tls/privkey.pem
fi

DB_PASS="$(openssl rand -hex 18)"
SECRET_KEY="$(openssl rand -hex 32)"
ENROLL_KEY="akdl-prod-enroll-2026"

sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='akdl'" | grep -q 1 \
  || sudo -u postgres psql -c "CREATE USER akdl WITH PASSWORD '$DB_PASS';"
sudo -u postgres psql -c "ALTER USER akdl WITH PASSWORD '$DB_PASS';"
sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='akdl'" | grep -q 1 \
  || sudo -u postgres psql -c "CREATE DATABASE akdl OWNER akdl;"

sudo tee /etc/akdl/akdl.env >/dev/null <<EOF
AKDL_DEBUG=0
AKDL_SECRET_KEY=$SECRET_KEY
AKDL_ALLOWED_HOSTS=dpc.apinfotechandcybersolution.com,3.106.214.246,127.0.0.1,localhost
AKDL_CSRF_ORIGINS=https://dpc.apinfotechandcybersolution.com,http://dpc.apinfotechandcybersolution.com,https://3.106.214.246,http://3.106.214.246
AKDL_ENROLLMENT_KEY=$ENROLL_KEY
AKDL_SIGNING_KEY_PATH=/etc/akdl/command_signing_key.pem
AKDL_APK_PATH=/etc/akdl/akdevicelock.apk
AKDL_APK_CERT_SHA256=$CERT_SHA256
AKDL_PUBLIC_BASE_URL=auto
AKDL_DB_NAME=akdl
AKDL_DB_USER=akdl
AKDL_DB_PASSWORD=$DB_PASS
AKDL_DB_HOST=127.0.0.1
AKDL_DB_PORT=5432
EOF
sudo chown ubuntu:www-data /etc/akdl/akdl.env
sudo chmod 600 /etc/akdl/akdl.env

cd /opt/akdevicelock/backend
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt

set -a
source /etc/akdl/akdl.env
set +a

.venv/bin/python manage.py migrate --noinput
.venv/bin/python manage.py collectstatic --noinput -v 0
.venv/bin/python manage.py shell -c "
from django.contrib.auth import get_user_model
U = get_user_model()
u, _ = U.objects.get_or_create(username='operator', defaults={'email': 'op@example.com', 'is_staff': True, 'is_superuser': True})
u.is_staff = True
u.is_superuser = True
u.set_password('VflFxu2imw8evX')
u.save()
print('OPERATOR_READY')
"

sudo cp /opt/akdevicelock/deployment/akdl.service /etc/systemd/system/akdl.service
sudo systemctl daemon-reload
sudo systemctl enable akdl.service
sudo systemctl restart akdl.service

sudo cp /opt/akdevicelock/deployment/nginx-akdl.conf /etc/nginx/sites-available/akdl
sudo ln -sf /etc/nginx/sites-available/akdl /etc/nginx/sites-enabled/akdl
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx

echo "DEPLOY_SUCCESS"
