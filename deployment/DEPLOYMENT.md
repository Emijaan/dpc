# AK DeviceLock Ubuntu Production Deployment

## Target Server
- **Host / IP**: `3.106.214.246`
- **Domain**: `dpc.apinfotechandcybersolution.com`
- **OS**: Ubuntu 26.04 LTS
- **Application Directory**: `/opt/akdevicelock`
- **Configuration & Secrets**: `/etc/akdl/` (`akdl.env`, `command_signing_key.pem`, `akdevicelock.apk`, `tls/`)

## Stack
- **Database**: PostgreSQL (`akdl` database, `akdl` role)
- **WSGI Server**: Gunicorn (`deployment/akdl.service`, systemd service `akdl.service` on `127.0.0.1:8000`)
- **Reverse Proxy**: Nginx (`deployment/nginx-akdl.conf`, ports 80 and 443)
- **QR Provisioning**: `/panel/qr/` generates the Device Owner enrollment QR code with `PROVISIONING_DEVICE_ADMIN_SIGNATURE_CHECKSUM` and `PROVISIONING_ADMIN_EXTRAS_BUNDLE`, serving the signed release APK at `/download/akdevicelock.apk`.

## Enabling Let's Encrypt HTTPS Certificate (Once DNS A Record Resolves)
When `dpc.apinfotechandcybersolution.com` resolves to `3.106.214.246` in public DNS:
```bash
sudo ~/.acme.sh/acme.sh --issue -d dpc.apinfotechandcybersolution.com -w /var/www/html
sudo ~/.acme.sh/acme.sh --install-cert -d dpc.apinfotechandcybersolution.com \
  --key-file /etc/akdl/tls/privkey.pem \
  --fullchain-file /etc/akdl/tls/fullchain.pem \
  --reloadcmd "sudo systemctl reload nginx"
```

