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

`go2rtc/go2rtc.yaml` is runtime state, not configuration you edit by hand — go2rtc
rewrites it as streams are registered, which is why it is gitignored and generated
from `go2rtc.yaml.example`. Printer streams belong in the web UI, not in that file.

**`could not register ... 400 Bad Request` on every backend start**

Expected on go2rtc 1.9.14, and harmless. go2rtc cannot patch a stream key it
loaded from its own config file: the PUT returns
`400 yaml: line N: did not find expected key`, pointing at the `streams:` node.
The stream is still applied in memory, so cameras work — only the write-back to
disk is skipped. Registrations for *new* printers (keys not yet in the file)
return 200 and do persist.

The practical consequence: if you change a printer's IP or access code, go2rtc's
memory updates but `go2rtc.yaml` keeps the old value. Restarting the backend
re-applies the correct value, so cameras recover on their own. It only bites if
go2rtc restarts *without* the backend — it then loads the stale URL from disk.
Restart the backend to fix it:

```bash
docker compose -C ~/bambu-lab-monitor restart backend
```

**Do not work around this with DELETE-then-PUT.** go2rtc's append-after-delete
writes malformed YAML: it appends the new URL to the *preceding* stream's
producer list and writes the new key at the wrong indentation. That gives one
printer a second producer pointing at another printer's camera, and the broken
indentation then makes every later write-back fail — which is how a config ends
up silently stale in the first place.

To rebuild the file from the database as the source of truth, regenerate the
`streams:` block, keeping one two-space-indented `- rtsps://…` line per printer,
then restart go2rtc and the backend and confirm each stream has exactly one
producer:

```bash
curl -s http://localhost:1984/api/streams | python3 -m json.tool
```

**Out of disk space**

The SD card fills up if old Docker images accumulate. Clean up with:
```bash
docker system prune -f
```

**Pi gets warm**

The active cooler is essential — do not run without it. The Pi 5 throttles under
sustained CPU load without cooling.
