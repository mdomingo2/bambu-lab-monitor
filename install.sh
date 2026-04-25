#!/usr/bin/env bash
# ============================================================
#  Bambu Lab Monitor — Raspberry Pi / Debian installer
#  Tested on: Raspberry Pi OS Lite 64-bit (Debian Bookworm)
#  Run as a regular user with sudo access (not as root).
#
#  Usage:
#    curl -fsSL https://raw.githubusercontent.com/mdomingo2/bambu-lab-monitor/main/install.sh | bash
#  or, after cloning:
#    bash install.sh
# ============================================================
set -euo pipefail

APP_DIR="${HOME}/bambu-lab-monitor"
REPO_URL="https://github.com/mdomingo2/bambu-lab-monitor.git"
SERVICE_NAME="bambu-monitor"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# ── 1. Check we are NOT running as root ─────────────────────
if [[ "${EUID}" -eq 0 ]]; then
  error "Do not run this script as root. Run it as a regular user — sudo will be used where needed."
fi

# ── 2. System update ─────────────────────────────────────────
info "Updating package lists…"
sudo apt-get update -qq

# ── 3. Install Docker Engine + Compose plugin ────────────────
if command -v docker &>/dev/null; then
  info "Docker already installed: $(docker --version)"
else
  info "Installing Docker Engine…"
  sudo apt-get install -y ca-certificates curl gnupg lsb-release

  sudo install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/debian/gpg \
    | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  sudo chmod a+r /etc/apt/keyrings/docker.gpg

  echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
    https://download.docker.com/linux/debian \
    $(lsb_release -cs) stable" \
    | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

  sudo apt-get update -qq
  sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

  # Add current user to docker group so we don't need sudo for docker commands
  sudo usermod -aG docker "${USER}"
  warn "Added ${USER} to the docker group. You may need to log out and back in for this to take effect."
fi

# ── 4. Install git ───────────────────────────────────────────
if ! command -v git &>/dev/null; then
  info "Installing git…"
  sudo apt-get install -y git
fi

# ── 5. Clone or update the repo ─────────────────────────────
if [[ -d "${APP_DIR}/.git" ]]; then
  info "Repo already exists at ${APP_DIR} — pulling latest changes…"
  git -C "${APP_DIR}" pull --ff-only
else
  info "Cloning repo to ${APP_DIR}…"
  git clone "${REPO_URL}" "${APP_DIR}"
fi

# ── 6. Install systemd service ───────────────────────────────
SERVICE_SRC="${APP_DIR}/deploy/${SERVICE_NAME}.service"
SERVICE_DEST="/etc/systemd/system/${SERVICE_NAME}.service"

if [[ -f "${SERVICE_SRC}" ]]; then
  info "Installing systemd service…"
  # Patch the WorkingDirectory and user into the service file
  sed \
    -e "s|__APP_DIR__|${APP_DIR}|g" \
    -e "s|__USER__|${USER}|g" \
    "${SERVICE_SRC}" | sudo tee "${SERVICE_DEST}" > /dev/null

  sudo systemctl daemon-reload
  sudo systemctl enable "${SERVICE_NAME}"
  info "Service enabled — will start automatically on boot."
else
  warn "Service template not found at ${SERVICE_SRC}. Skipping systemd setup."
fi

# ── 7. Configure HOST_IP for WebRTC camera streams ──────────
LOCAL_IP=$(hostname -I | awk '{print $1}')
ENV_FILE="${APP_DIR}/.env"

if [[ -f "${ENV_FILE}" ]] && grep -q "^HOST_IP=" "${ENV_FILE}"; then
  EXISTING_IP=$(grep "^HOST_IP=" "${ENV_FILE}" | cut -d= -f2)
  if [[ "${EXISTING_IP}" == "${LOCAL_IP}" ]]; then
    info "HOST_IP already set to ${LOCAL_IP} in .env"
  else
    info "Updating HOST_IP in .env: ${EXISTING_IP} → ${LOCAL_IP}"
    sed -i "s|^HOST_IP=.*|HOST_IP=${LOCAL_IP}|" "${ENV_FILE}"
  fi
else
  info "Writing HOST_IP=${LOCAL_IP} to .env (needed for WebRTC camera streams)"
  echo "HOST_IP=${LOCAL_IP}" >> "${ENV_FILE}"
fi

# ── 8. Build and start the stack ────────────────────────────
info "Building Docker images (this takes a few minutes on first run)…"
# Use sg to run docker in the docker group without a full re-login
sg docker -c "docker compose -f '${APP_DIR}/docker-compose.yml' build"

info "Starting services…"
sg docker -c "docker compose -f '${APP_DIR}/docker-compose.yml' up -d"

# ── 9. Done ──────────────────────────────────────────────────
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║        Bambu Lab Monitor installed successfully!      ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  Dashboard:  ${YELLOW}http://${LOCAL_IP}${NC}"
echo -e "  go2rtc:     ${YELLOW}http://${LOCAL_IP}:1984${NC}"
echo ""
echo -e "  To check service status:  ${YELLOW}sudo systemctl status ${SERVICE_NAME}${NC}"
echo -e "  To view logs:             ${YELLOW}docker compose -C ${APP_DIR} logs -f${NC}"
echo -e "  To update:                ${YELLOW}bash ${APP_DIR}/install.sh${NC}"
echo ""
