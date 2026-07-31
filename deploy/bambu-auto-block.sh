#!/bin/bash
# bambu-auto-block.sh
#
# Owns the DOCKER-USER firewall chain for the bambu-lab-monitor stack.
#
# Two jobs:
#
#   1. ACCESS POLICY — only the LAN, the Tailscale tailnet and Docker's own
#      bridges may reach the published web ports.  Everything else is dropped.
#      This is what makes the app private even if the router's 8443 port
#      forward is still in place.
#
#   2. ABUSE BLOCKING — scans nginx logs and blocks noisy IPs outright:
#        Pass 1 — FAST attackers:  >= 30 requests in the last 10 minutes
#        Pass 2 — SLOW scanners:   >= 60 requests in the last 24 hours
#
# IMPORTANT — why ufw is not enough:
#   The web app is published by Docker (ports 80/8443/8555).  That traffic is
#   DNAT'd in nat/PREROUTING and traverses FORWARD -> DOCKER; it never reaches
#   the INPUT chain where ufw's rules live.  A plain "ufw deny from <ip>"
#   therefore does NOT stop an attacker from reaching nginx.  (Observed: an IP
#   blocked 2026-05-02 was still served by nginx on 2026-07-31.)
#   Rules must go in DOCKER-USER, which Docker evaluates first via FORWARD.
#
#   Docker recreates DOCKER-USER empty whenever the daemon restarts, so the
#   whole chain is rebuilt deterministically on every run rather than assuming
#   previous rules survived.  ufw rules are still added for blocked IPs because
#   those do cover host services (e.g. SSH) that Docker does not publish.
#
# State:  /etc/bambu-monitor/blocked.txt
# Log:    /var/log/bambu-auto-block.log

set -euo pipefail

# ── Config ────────────────────────────────────────────────────────────────────

CONTAINER="bambu-lab-monitor-frontend-1"
BLOCKED_FILE="/etc/bambu-monitor/blocked.txt"
LOG_FILE="/var/log/bambu-auto-block.log"

FAST_THRESHOLD=30       # requests in FAST_WINDOW to trigger block
FAST_WINDOW="10m"

SLOW_THRESHOLD=60       # requests in SLOW_WINDOW to trigger block
SLOW_WINDOW="24h"

# Sources allowed to reach the published web ports.
#   192.168.1.0/24 — home LAN
#   100.64.0.0/10  — Tailscale tailnet (CGNAT range)
#   172.16.0.0/12  — Docker bridge networks (inter-container traffic)
TRUSTED_SOURCES=(
    "192.168.1.0/24"
    "100.64.0.0/10"
    "172.16.0.0/12"
    "127.0.0.0/8"
)

# Ports published by docker-compose that should be private.
TCP_PORTS="80,443,8443,8555"
UDP_PORTS="8555"

# Never block these (local network, Docker bridge, loopback)
WHITELIST=(
    "127."
    "192.168."
    "10."
    "172.16."
    "172.17."
    "172.18."
    "::1"
)

# ── Helpers ───────────────────────────────────────────────────────────────────

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"; }

is_whitelisted() {
    local ip="$1"
    for prefix in "${WHITELIST[@]}"; do
        [[ "$ip" == "$prefix"* ]] && return 0
    done
    return 1
}

is_already_blocked() { grep -qxF "$1" "$BLOCKED_FILE" 2>/dev/null; }

# Rebuild DOCKER-USER from scratch, in a deterministic order:
#   established -> blocked IPs -> trusted sources -> drop the rest
# Rebuilding (rather than appending) keeps the chain correct after a Docker
# daemon restart, which recreates it empty.
apply_policy() {
    iptables -F DOCKER-USER

    # Replies to connections the containers themselves opened.
    iptables -A DOCKER-USER -m conntrack --ctstate RELATED,ESTABLISHED -j RETURN

    # Known-abusive sources, dropped outright.
    local ip
    if [[ -f "$BLOCKED_FILE" ]]; then
        while read -r ip; do
            [[ -z "$ip" ]] && continue
            is_whitelisted "$ip" && continue
            iptables -A DOCKER-USER -s "$ip" -j DROP
        done < "$BLOCKED_FILE"
    fi

    # Trusted networks pass through to the normal Docker chains.
    local net
    for net in "${TRUSTED_SOURCES[@]}"; do
        iptables -A DOCKER-USER -s "$net" -j RETURN
    done

    # Anything else reaching a published web port is dropped.  Non-web traffic
    # is left alone so container egress keeps working.
    iptables -A DOCKER-USER -p tcp -m multiport --dports "$TCP_PORTS" -j DROP
    iptables -A DOCKER-USER -p udp -m multiport --dports "$UDP_PORTS" -j DROP
}

block_ip() {
    local ip="$1" reason="$2"
    # Host-bound traffic (SSH and friends) — Docker does not route this.
    ufw insert 1 deny from "$ip" to any comment "auto-block:bambu" >/dev/null 2>&1 || true
    echo "$ip" >> "$BLOCKED_FILE"
    log "BLOCKED $ip — $reason"
}

scan_window() {
    local window="$1" threshold="$2" label="$3"
    docker logs "$CONTAINER" --since "$window" 2>/dev/null \
        | grep -oP '^\K\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}' \
        | sort | uniq -c | sort -rn \
        | while read -r count ip; do
            (( count < threshold )) && break
            is_whitelisted "$ip"     && continue
            is_already_blocked "$ip" && continue
            block_ip "$ip" "$count requests in last $window ($label)"
          done
}

# ── Run ───────────────────────────────────────────────────────────────────────

scan_window "$FAST_WINDOW" "$FAST_THRESHOLD" "fast-attack"
scan_window "$SLOW_WINDOW" "$SLOW_THRESHOLD" "slow-scan"

# Applied last so newly-blocked IPs are included in the rebuilt chain.
apply_policy
