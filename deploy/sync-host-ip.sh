#!/usr/bin/env bash
#
# Keep go2rtc's WebRTC ICE candidates pointing at addresses this Pi actually
# has.
#
# go2rtc tells the browser where to open the direct video connection, using
# the HOST_IP / TS_IP values baked into its container environment.  Those come
# from .env and are DHCP/tailnet leases.  When an address moves and .env is not
# updated, go2rtc keeps advertising the old one and *every* camera fails with
# "WebRTC connection failed" — while the UI keeps working, because only the
# video is a direct browser→Pi connection.  That combination reads as a printer
# fault and is easy to misdiagnose.
#
# This script compares reality against .env and repairs it when they diverge.
# It is a safety net: with a static DHCP reservation it should never fire.
#
# Install (runs every 5 minutes as the user owning the compose project):
#   */5 * * * * /home/mike/bambu-lab-monitor/deploy/sync-host-ip.sh >> /home/mike/bambu-lab-monitor/deploy/sync-host-ip.log 2>&1
#
# Note: containers read .env only when they are *created*.  `docker compose
# restart` reuses the old environment, so this deliberately uses `up -d` to
# recreate go2rtc after a change.

set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${APP_DIR}/.env"
COMPOSE_FILE="${APP_DIR}/docker-compose.yml"
LOCK_FILE="/tmp/bambu-sync-host-ip.lock"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

# Never let a slow container restart overlap with the next cron tick.
exec 9>"${LOCK_FILE}"
flock -n 9 || exit 0

[[ -f "${ENV_FILE}" ]] || { log "ERROR: ${ENV_FILE} not found"; exit 1; }

# ── Detect reality ───────────────────────────────────────────────────────────

# Source address of the default route — the address other LAN hosts reach us on.
lan_ip="$(ip route get 1.1.1.1 2>/dev/null | grep -oP 'src \K[0-9.]+' | head -1 || true)"
ts_ip="$(tailscale ip -4 2>/dev/null | head -1 || true)"

# No tailnet is fine; fall back to the LAN address so the candidate list stays
# valid (a harmless duplicate) rather than expanding to an empty string.
[[ -z "${ts_ip}" ]] && ts_ip="${lan_ip}"

if [[ -z "${lan_ip}" ]]; then
    log "WARN: could not determine LAN IP — network down? leaving .env alone"
    exit 0
fi

# ── Compare against configuration ────────────────────────────────────────────

env_get() { grep -E "^$1=" "${ENV_FILE}" 2>/dev/null | head -1 | cut -d= -f2- || true; }

cfg_lan="$(env_get HOST_IP)"
cfg_ts="$(env_get TS_IP)"

[[ "${cfg_lan}" == "${lan_ip}" && "${cfg_ts}" == "${ts_ip}" ]] && exit 0

log "address change detected:"
[[ "${cfg_lan}" != "${lan_ip}" ]] && log "  HOST_IP ${cfg_lan:-<unset>} -> ${lan_ip}"
[[ "${cfg_ts}"  != "${ts_ip}"  ]] && log "  TS_IP   ${cfg_ts:-<unset>} -> ${ts_ip}"

# ── Repair ───────────────────────────────────────────────────────────────────

upsert() {   # upsert KEY VALUE
    if grep -qE "^$1=" "${ENV_FILE}"; then
        sed -i "s|^$1=.*|$1=$2|" "${ENV_FILE}"
    else
        printf '%s=%s\n' "$1" "$2" >> "${ENV_FILE}"
    fi
}

cp -p "${ENV_FILE}" "${ENV_FILE}.bak"
upsert HOST_IP "${lan_ip}"
upsert TS_IP   "${ts_ip}"

# Keep the cert's SAN list accurate for whenever it is next regenerated.  The
# certificate is deliberately NOT regenerated here: that would invalidate the
# one every device has already trusted, turning a silent camera outage into a
# browser warning on every device with no one present to explain it.
cert_hosts="$(env_get CERT_HOSTS)"
if [[ -n "${cert_hosts}" ]]; then
    rest="$(printf '%s' "${cert_hosts}" | cut -d, -f3-)"
    new_cert_hosts="${lan_ip},${ts_ip}${rest:+,${rest}}"
    if [[ "${new_cert_hosts}" != "${cert_hosts}" ]]; then
        upsert CERT_HOSTS "${new_cert_hosts}"
        log "  CERT_HOSTS updated (cert not reissued — see DEPLOY.md)"
    fi
fi

# Recreate go2rtc so it picks up the new environment, then restart the backend
# so streams are re-registered immediately rather than waiting for the next
# reconcile pass.
log "recreating go2rtc with the new candidates…"
docker compose -f "${COMPOSE_FILE}" up -d --force-recreate go2rtc
docker compose -f "${COMPOSE_FILE}" restart backend

log "done — cameras should recover within a few seconds"
