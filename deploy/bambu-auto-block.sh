#!/bin/bash
# bambu-auto-block.sh
#
# Two-pass IP blocking for the bambu-lab-monitor nginx container:
#
#   Pass 1 — FAST attackers:  >= 30 requests in the last 10 minutes
#   Pass 2 — SLOW scanners:   >= 60 requests in the last 24 hours
#
# Blocked IPs are added to ufw and recorded in BLOCKED_FILE so they
# aren't re-added on subsequent runs.
#
# IMPORTANT — why ufw alone is not enough:
#   The web app is published by Docker (ports 80/8443/8555).  That traffic is
#   DNAT'd in nat/PREROUTING and traverses FORWARD -> DOCKER; it never reaches
#   the INPUT chain where ufw's rules live.  A plain "ufw deny from <ip>"
#   therefore does NOT stop an attacker from reaching nginx.  (Observed: an IP
#   blocked 2026-05-02 was still served by nginx on 2026-07-31.)
#   Blocks must additionally be inserted into the DOCKER-USER chain, which
#   Docker evaluates first for container-bound traffic.
#
#   Docker recreates DOCKER-USER empty whenever the daemon restarts, so every
#   run reconciles the chain against BLOCKED_FILE rather than assuming the
#   rules survived.  The ufw rules are kept as well — they still cover traffic
#   aimed at host services (e.g. SSH) rather than containers.
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

# Insert a DROP for $1 at the top of DOCKER-USER unless it is already there.
# Returns 0 if a rule was added, 1 if it was already present.
ensure_docker_block() {
    local ip="$1"
    if iptables -C DOCKER-USER -s "$ip" -j DROP 2>/dev/null; then
        return 1
    fi
    iptables -I DOCKER-USER 1 -s "$ip" -j DROP
    return 0
}

# Re-apply every known block to DOCKER-USER.  Docker flushes this chain on
# daemon restart, so without this the blocks silently disappear after a reboot.
reconcile_docker_blocks() {
    [[ -f "$BLOCKED_FILE" ]] || return 0
    local ip restored=0
    while read -r ip; do
        [[ -z "$ip" ]] && continue
        is_whitelisted "$ip" && continue
        if ensure_docker_block "$ip"; then
            restored=$(( restored + 1 ))
        fi
    done < "$BLOCKED_FILE"
    (( restored > 0 )) && log "RECONCILE restored $restored DOCKER-USER rule(s) from $BLOCKED_FILE"
    return 0
}

block_ip() {
    local ip="$1" reason="$2"
    # Host-bound traffic (SSH and friends).
    ufw insert 1 deny from "$ip" to any comment "auto-block:bambu" >/dev/null 2>&1 || true
    # Container-bound traffic (the web app) — this is the one that matters.
    ensure_docker_block "$ip" || true
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

reconcile_docker_blocks
scan_window "$FAST_WINDOW" "$FAST_THRESHOLD" "fast-attack"
scan_window "$SLOW_WINDOW" "$SLOW_THRESHOLD" "slow-scan"
