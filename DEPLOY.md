# Deploying Bambu Lab Monitor on a Raspberry Pi

This guide covers everything needed to run the Bambu Lab Monitor on a Raspberry Pi as a
permanent local server. The entire stack runs in Docker, so setup is mostly automated.

---

## Recommended Hardware

### Primary recommendation — Raspberry Pi 5 (4 GB)

The Pi 5 runs the full stack (FastAPI backend, nginx frontend, go2rtc RTSP/WebRTC proxy)
comfortably, with headroom for multiple simultaneous camera streams.

| | |
|---|---|
| **Board** | Raspberry Pi 5 4 GB |
| **Kit (board + case + active cooler + PSU)** | [Raspberry Pi 5 4GB Development Board Kit on Amazon](https://www.amazon.com/Kit-Official-Case-Pi5-4GB-Charger/dp/B0CSLXMGX3) |
| **MicroSD card** | 32 GB+ Class 10 / A1 (any reputable brand) |

> **Budget option:** A Raspberry Pi 4 (4 GB) also works. The Pi 4 is slower to build images
> but handles runtime just fine.

### What you need

- Raspberry Pi 5 (or Pi 4) with case, active cooler, and official PSU
- 32 GB+ microSD card
- Ethernet cable (recommended) or Wi-Fi
- A computer to flash the SD card

---

## What Gets Installed

The installer (`install.sh`) takes care of everything:

| Component | Purpose |
|---|---|
| **Docker Engine** | Runs all containers |
| **Docker Compose plugin** | Orchestrates the multi-container stack |
| **Git** | Clones and updates the repo |
| **systemd service** | Auto-starts the stack on every boot |

No Python, Node.js, or build tools are needed on the host — all of that lives inside
the Docker images.

---

## Step-by-Step Setup

### 1. Flash Raspberry Pi OS Lite (64-bit)

1. Download [Raspberry Pi Imager](https://www.raspberrypi.com/software/)
2. Choose **Raspberry Pi OS Lite (64-bit)** — the "Lite" version has no desktop, which
   saves RAM and CPU for the monitor stack
3. In the Imager settings (gear icon ⚙) before flashing:
   - Set a hostname, e.g. `bambu-pi`
   - Enable SSH
   - Set your username and password
   - Configure Wi-Fi if you are not using ethernet
4. Flash to the SD card, insert into the Pi, and power on

### 2. SSH into the Pi

```bash
ssh pi@bambu-pi.local
# or use the IP address shown in your router's DHCP table
```

### 3. Run the installer

```bash
curl -fsSL https://raw.githubusercontent.com/mdomingo2/bambu-lab-monitor/main/install.sh | bash
```

That's it. The script will:
- Install Docker and Git
- Clone this repo to `~/bambu-lab-monitor`
- Build all Docker images (takes 5–10 min on first run)
- Start the stack
- Install and enable the systemd service so it restarts on every boot

### 4. Open the dashboard

```
http://bambu-pi.local
```

Or substitute the Pi's IP address if mDNS doesn't resolve.

---

## Giving the Pi a Fixed IP (Recommended)

Assign a static DHCP lease for the Pi in your router settings so its address never
changes. The exact steps vary by router brand — look for "DHCP reservation" or
"static lease" and assign the IP to the Pi's MAC address.

---

## Useful Commands

```bash
# View live logs from all containers
docker compose -C ~/bambu-lab-monitor logs -f

# Restart the stack
sudo systemctl restart bambu-monitor

# Stop the stack
sudo systemctl stop bambu-monitor

# Update to the latest version
bash ~/bambu-lab-monitor/install.sh

# Check service status
sudo systemctl status bambu-monitor
```

---

## ARM64 Compatibility

All base images used by this project publish official ARM64 builds, so everything
compiles and runs natively on the Pi — no emulation layer:

| Image | ARM64 |
|---|---|
| `python:3.12-slim` | ✅ |
| `node:20-alpine` | ✅ |
| `nginx:alpine` | ✅ |
| `alexxit/go2rtc` | ✅ |

---

## Troubleshooting

**Dashboard not loading after install**

The backend health check must pass before nginx starts. Wait ~60 seconds and reload.
Check logs with `docker compose -C ~/bambu-lab-monitor logs backend`.

**Camera streams not working**

Make sure port `8555` (WebRTC media) is reachable from your browser's machine.
If you are on the same LAN this should work automatically.

**One camera says "stream not found"**

That error comes from go2rtc and means no stream is registered for that printer.
The backend registers every printer's camera on startup and whenever a printer is
added or edited, so restarting the backend usually fixes it:

```bash
docker compose -C ~/bambu-lab-monitor restart backend
```

Confirm the stream exists — there should be one `bambu_<printer id>` entry per
printer:

```bash
curl -s http://localhost:1984/api/streams | python3 -m json.tool
```

If a printer is missing, check `docker compose logs backend | grep go2rtc` for a
`could not register` warning.

`go2rtc/go2rtc.yaml` holds host-specific addresses, which is why it is gitignored
and generated from `go2rtc.yaml.example`. Its `streams:` block is **intentionally
empty** — the database is the source of truth. The backend registers every printer
at startup and re-checks once a minute, so go2rtc is repopulated within a minute of
any restart. Add printers in the web UI, never in that file.

**"Camera unavailable — WebRTC connection failed"**

Almost always a wrong address in `.env`, not a broken printer. The page itself
loads over HTTP, but the *video* is a direct browser→Pi connection to port 8555,
and go2rtc has to advertise an address the browser can actually reach.

`HOST_IP` and `TS_IP` are DHCP/tailnet leases. When the Pi's address moves, go2rtc
keeps offering the old one and every camera fails at once — while the UI keeps
working, which makes it look like a printer problem. Check them against reality:

```bash
ip route get 1.1.1.1 | head -1     # actual LAN IP
tailscale ip -4                    # actual tailnet IP
grep -E '^(HOST_IP|TS_IP)=' ~/bambu-lab-monitor/.env
```

Fix `.env` if they disagree, then `docker compose restart go2rtc`. Confirm what
go2rtc now offers — you should see one `typ host` candidate per address:

```bash
docker compose logs go2rtc | grep -i candidate
```

If every camera fails, suspect the addresses. If only one fails, suspect that
printer (powered off, or LAN Mode disabled on its screen).

`deploy/sync-host-ip.sh` guards against this automatically. Run from cron every
five minutes, it compares the Pi's real LAN and tailnet addresses against `.env`
and, on a mismatch, updates it, recreates go2rtc, and restarts the backend so
streams re-register immediately:

```bash
*/5 * * * * /home/mike/bambu-lab-monitor/deploy/sync-host-ip.sh >> /home/mike/bambu-lab-monitor/deploy/sync-host-ip.log 2>&1
```

It is silent unless it acts; `deploy/sync-host-ip.log` is the record of every
address change. With a static DHCP reservation it should never fire — it exists
for the case where the reservation is lost or the Pi moves networks. It updates
`CERT_HOSTS` but deliberately does **not** reissue the certificate: doing so
unattended would invalidate the cert every device has already trusted.

Note that containers read `.env` only when they are **created**. `docker compose
restart` reuses the old environment — use `up -d` after changing `.env`, or the
change appears to be ignored.

**`could not register ... 400 Bad Request` on every backend start**

Expected on go2rtc 1.9.14, and harmless — logged at INFO as `applied … write-back
skipped`. go2rtc cannot patch a stream key it loaded from its own config file: the
PUT returns `400 yaml: line N: did not find expected key`. The stream is still
applied in memory, so cameras work.

Keeping `streams:` empty means that write path is barely exercised, which is
deliberate. **Never populate the file and never work around this with
DELETE-then-PUT.** go2rtc's append-after-delete writes malformed YAML: it appends
the new URL to the *preceding* stream's producer list and writes the new key at the
wrong indentation. That gives one printer a second producer pointing at another
printer's camera — you get the wrong printer's video — and the broken indentation
makes every later write-back fail silently.

If the file ever does acquire a `streams:` block, reset it rather than repairing
it, and let the backend repopulate:

```bash
# set `streams: {}` in go2rtc/go2rtc.yaml, then:
docker compose restart go2rtc backend
curl -s http://localhost:1984/api/streams | python3 -m json.tool
```

Each stream must have exactly one producer. Two is the cross-wiring bug above.

**Out of disk space**

The SD card fills up if old Docker images accumulate. Clean up with:
```bash
docker system prune -f
```

**Pi gets warm**

The active cooler is essential — do not run without it. The Pi 5 throttles under
sustained CPU load without cooling.
