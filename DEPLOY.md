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

## Trusting the HTTPS Certificate

The app generates a **self-signed certificate** on first boot and stores it in the
`bambu_certs` Docker volume on your Pi. Browsers don't trust self-signed certs by
default, so every device that accesses the dashboard needs to import the cert once.

### Step 1 — Export the certificate from the Pi

```bash
# SSH into the Pi, then copy the cert to your home directory
docker compose -C ~/bambu-lab-monitor cp frontend:/etc/nginx/certs/cert.pem ~/bambu-cert.pem
```

Then transfer it to your computer (e.g. via `scp` or a USB drive):

```bash
# Run this on your local machine
scp pi@bambu-pi.local:~/bambu-cert.pem ~/Downloads/bambu-cert.pem
```

### Step 2 — Install the certificate

**macOS**
1. Double-click `bambu-cert.pem` — Keychain Access opens.
2. Drag it into the **System** keychain.
3. Double-click the imported cert → expand **Trust** → set *"When using this certificate"* to **Always Trust**.
4. Close and enter your password when prompted.

**Windows**
1. Double-click `bambu-cert.pem` → click **Install Certificate**.
2. Choose **Local Machine** → click Next.
3. Select **Place all certificates in the following store** → browse to **Trusted Root Certification Authorities** → Finish.
4. Restart your browser.

**Linux (Chrome / Chromium)**
1. Open `chrome://settings/certificates` → **Authorities** tab → **Import**.
2. Select `bambu-cert.pem` → check *"Trust this certificate for identifying websites"* → OK.

**Linux (Firefox)**
Firefox manages its own trust store regardless of OS:
1. Open `about:preferences#privacy` → scroll to **Certificates** → **View Certificates**.
2. **Authorities** tab → **Import** → select `bambu-cert.pem` → check *"Trust this CA to identify websites"*.

**Android**
1. Copy `bambu-cert.pem` to the device.
2. Go to **Settings → Security → Install a certificate → CA certificate** (exact path varies by manufacturer).
3. Select the file.

**iOS / iPadOS**
1. AirDrop or email `bambu-cert.pem` to the device and open it — iOS prompts you to download a profile.
2. Go to **Settings → General → VPN & Device Management** → tap the profile → **Install**.
3. Then go to **Settings → General → About → Certificate Trust Settings** and enable full trust for the cert.

> **Note:** You only need to do this once per device. The cert is valid for 10 years
> and lives in the Docker volume, so it survives container rebuilds.

---

## Troubleshooting

**Dashboard not loading after install**

The backend health check must pass before nginx starts. Wait ~60 seconds and reload.
Check logs with `docker compose -C ~/bambu-lab-monitor logs backend`.

**Camera streams not working**

Make sure port `8555` (WebRTC media) is reachable from your browser's machine.
If you are on the same LAN this should work automatically.

**Out of disk space**

The SD card fills up if old Docker images accumulate. Clean up with:
```bash
docker system prune -f
```

**Pi gets warm**

The active cooler is essential — do not run without it. The Pi 5 throttles under
sustained CPU load without cooling.
