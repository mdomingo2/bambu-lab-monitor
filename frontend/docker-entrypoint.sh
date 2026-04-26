#!/bin/sh
# Bambu Farm Monitor — Nginx entrypoint
#
# On every container start we check whether a TLS certificate already exists
# in the shared certs volume.  If not, we generate a self-signed one.
# The cert is valid for 10 years so it won't expire unexpectedly in the field.
#
# Customising the certificate SAN (strongly recommended for LAN access):
#   Add CERT_HOSTS to your .env file — a comma-separated list of IP addresses
#   and/or hostnames that your browser will use to reach the Pi.
#
#   Example .env:
#     CERT_HOSTS=192.168.1.50,bambu.local
#
#   Mixed IPs and hostnames are both supported; the script detects which is
#   which automatically.  Without CERT_HOSTS browsers will still accept the
#   cert after a one-time "proceed anyway" click, but you'll need to click it
#   again after each cert regeneration.
#
# Providing your own certificate:
#   Mount your own cert/key pair into the container:
#     volumes:
#       - /path/to/your/cert.pem:/etc/nginx/certs/cert.pem:ro
#       - /path/to/your/key.pem:/etc/nginx/certs/key.pem:ro
#   The script detects existing files and skips generation entirely.

set -e

CERT_DIR=/etc/nginx/certs
CERT_FILE="$CERT_DIR/cert.pem"
KEY_FILE="$CERT_DIR/key.pem"

mkdir -p "$CERT_DIR"

if [ ! -f "$CERT_FILE" ] || [ ! -f "$KEY_FILE" ]; then
    echo "[bambu] TLS certificate not found — generating self-signed cert..."

    # Build the Subject Alternative Name list.
    # Always include localhost/127.0.0.1 as a baseline.
    SAN="DNS:localhost,IP:127.0.0.1"

    if [ -n "$CERT_HOSTS" ]; then
        for host in $(echo "$CERT_HOSTS" | tr ',' ' '); do
            # Distinguish IP addresses from hostnames by checking for all-digit
            # quad-octet format.
            if echo "$host" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$'; then
                SAN="$SAN,IP:$host"
            else
                SAN="$SAN,DNS:$host"
            fi
        done
    fi

    openssl req -x509 \
        -newkey rsa:2048 \
        -keyout "$KEY_FILE" \
        -out  "$CERT_FILE" \
        -days 3650 \
        -nodes \
        -subj "/CN=bambu-farm/O=Bambu Farm Monitor" \
        -addext "subjectAltName=$SAN" \
        2>/dev/null

    echo "[bambu] Certificate generated (SAN: $SAN)"
    echo "[bambu] Tip: set CERT_HOSTS=<pi-ip> in your .env to include your Pi's LAN IP."
    echo "[bambu] Tip: import $CERT_FILE into your browser/OS trust store to silence warnings."
else
    echo "[bambu] Using existing TLS certificate from $CERT_DIR"
fi

exec nginx -g "daemon off;"
