#!/usr/bin/env bash
# WASP — installer
set -Eeuo pipefail

# ── Defaults ───────────────────────────────────────────────────────────
INSTALL_DIR="${WASP_INSTALL_DIR:-/opt/wasp}"
INSTALL_URL="${WASP_INSTALL_URL:-https://agentwasp.com/install.sh}"
TARBALL_URL="${WASP_TARBALL_URL:-https://agentwasp.com/wasp-release.tar.gz}"
REPO_URL="${WASP_REPO_URL:-https://github.com/agentwasp/agentwasp.git}"
REPO_BRANCH="${WASP_BRANCH:-main}"
LOCAL_SOURCE="${WASP_LOCAL_SOURCE:-}"
INSTALL_METHOD="auto"
DOCKER_ONLY=false
NO_START=false
NON_INTERACTIVE="${WASP_NON_INTERACTIVE:-false}"

# ── Inlined UI helpers ─────────────────────────────────────────────────
if [[ -t 1 ]] && [[ "${NO_COLOR:-}" == "" ]]; then
    C_RESET=$'\033[0m'; C_BOLD=$'\033[1m'; C_DIM=$'\033[2m'
    C_RED=$'\033[31m'; C_GREEN=$'\033[32m'; C_YELLOW=$'\033[33m'
    C_BLUE=$'\033[34m'; C_CYAN=$'\033[36m'
    C_GOLD=$'\033[38;5;220m'; C_AMBER=$'\033[38;5;214m'
    UI_TTY=true
else
    C_RESET=''; C_BOLD=''; C_DIM=''
    C_RED=''; C_GREEN=''; C_YELLOW=''; C_BLUE=''; C_CYAN=''
    C_GOLD=''; C_AMBER=''
    UI_TTY=false
fi

log()  { printf "%b\n" "$*"; }
info() { printf "${C_BLUE}${C_BOLD}▸${C_RESET} %s\n" "$*"; }
ok()   { printf "${C_GREEN}${C_BOLD}✓${C_RESET} %s\n" "$*"; }
warn() { printf "${C_YELLOW}${C_BOLD}!${C_RESET} %s\n" "$*"; }
err()  { printf "${C_RED}${C_BOLD}✗${C_RESET} %s\n" "$*" >&2; }
hr()   { printf "${C_DIM}────────────────────────────────────────────────────────────${C_RESET}\n"; }
die()  { err "$1"; exit "${2:-1}"; }

UI_STEP_TOTAL=10
UI_STEP_CURRENT=0
step() {
    UI_STEP_CURRENT=$(( UI_STEP_CURRENT + 1 ))
    printf "\n${C_CYAN}${C_BOLD}[%d/%d]${C_RESET} ${C_BOLD}%s${C_RESET}\n" \
        "$UI_STEP_CURRENT" "$UI_STEP_TOTAL" "$*"
}

run_spin() {
    local label="$1"; shift
    local logfile; logfile="$(mktemp)"
    local spin='⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏'
    local i=0
    if [[ "$UI_TTY" == "true" ]]; then
        ( "$@" >"$logfile" 2>&1 ) &
        local pid=$!
        printf '\033[?25l'
        while kill -0 "$pid" 2>/dev/null; do
            printf "\r${C_BLUE}%s${C_RESET} %s" "${spin:i:1}" "$label"
            i=$(( (i + 1) % ${#spin} ))
            sleep 0.1
        done
        # CRITICAL: wait may return non-zero. Do NOT let set -e abort here
        # — we need to capture the exit code and show the user the log.
        local rc=0
        wait "$pid" || rc=$?
        printf '\033[?25h\r\033[K'
        if [[ $rc -eq 0 ]]; then
            ok "$label"
            rm -f "$logfile"
            return 0
        fi
        err "$label — failed (exit $rc)"
        printf "${C_DIM}── last 40 lines of output ──${C_RESET}\n"
        tail -40 "$logfile"
        rm -f "$logfile"
        return $rc
    else
        info "$label"
        local rc=0
        "$@" || rc=$?
        return $rc
    fi
}

trap 'err "Install failed at line $LINENO. Re-run install.sh — it is idempotent."' ERR

# ── Argument parsing ───────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --install-method=*) INSTALL_METHOD="${1#*=}"; shift ;;
        --install-method)   INSTALL_METHOD="$2"; shift 2 ;;
        --local-source=*)   LOCAL_SOURCE="${1#*=}"; INSTALL_METHOD="local"; shift ;;
        --local-source)     LOCAL_SOURCE="$2"; INSTALL_METHOD="local"; shift 2 ;;
        --install-dir=*)    INSTALL_DIR="${1#*=}"; shift ;;
        --install-dir)      INSTALL_DIR="$2"; shift 2 ;;
        --branch=*)         REPO_BRANCH="${1#*=}"; shift ;;
        --branch)           REPO_BRANCH="$2"; shift 2 ;;
        --docker-only)      DOCKER_ONLY=true; shift ;;
        --no-start)         NO_START=true; shift ;;
        --yes|-y|--non-interactive) NON_INTERACTIVE=true; shift ;;
        --help|-h)
            cat <<EOF
WASP installer

Usage:
  install.sh [options]

Options:
  --install-method tarball|git|local   How to fetch source (default: auto = tarball)
  --local-source <DIR>         Copy from local DIR (sets method=local)
  --install-dir <DIR>          Where to install (default: /opt/wasp)
  --branch <NAME>              Git branch (default: main, used by method=git)
  --docker-only                Stop after Docker is installed
  --no-start                   Set up files / .env but do not build or start
  --yes / -y                   Skip prompts (use defaults / env vars)
  --help / -h                  Show this message
EOF
            exit 0
            ;;
        *) die "Unknown argument: $1 (try --help)" ;;
    esac
done

if [[ "$INSTALL_METHOD" == "auto" ]]; then
    if [[ -n "$LOCAL_SOURCE" && -d "$LOCAL_SOURCE" ]]; then
        INSTALL_METHOD="local"
    else
        # Default: download the published release tarball. This makes the
        # one-line install command work standalone:
        #   sudo bash -c "$(curl -fsSL https://agentwasp.com/install.sh)"
        # `git` remains available via --install-method=git for dev installs.
        INSTALL_METHOD="tarball"
    fi
fi

# ── Banner ────────────────────────────────────────────────────────────
if [[ "${WASP_LOGO_SHOWN:-}" != "true" ]]; then
    export WASP_LOGO_SHOWN=true
    printf "\n%b" "${C_GOLD}${C_BOLD}"
    cat <<'LOGO'
       ██╗    ██╗  █████╗  ███████╗ ██████╗
       ██║    ██║ ██╔══██╗ ██╔════╝ ██╔══██╗
       ██║ █╗ ██║ ███████║ ███████╗ ██████╔╝
       ██║███╗██║ ██╔══██║ ╚════██║ ██╔═══╝
       ╚███╔███╔╝ ██║  ██║ ███████║ ██║
        ╚══╝╚══╝  ╚═╝  ╚═╝ ╚══════╝ ╚═╝
LOGO
    printf "%b" "${C_RESET}"
    printf "${C_DIM}       🐝  autonomous agent · self-hosted${C_RESET}\n"
    printf "${C_DIM}       🌐  ${C_BOLD}agentwasp.com${C_RESET}\n\n"
fi

log "${C_DIM}install dir: ${INSTALL_DIR}  ·  method: ${INSTALL_METHOD}${C_RESET}"

# ── Sudo helper ────────────────────────────────────────────────────────
if [[ "$EUID" -eq 0 ]]; then
    SUDO=""
else
    if command -v sudo >/dev/null 2>&1; then
        SUDO="sudo"
    else
        die "This installer needs root or sudo. Install sudo and re-run."
    fi
fi

# ── [1/10] Pre-flight ──────────────────────────────────────────────────
step "Pre-flight checks"
OS_ID="$( . /etc/os-release 2>/dev/null && echo "${ID:-unknown}" )"
OS_LIKE="$( . /etc/os-release 2>/dev/null && echo "${ID_LIKE:-}" )"

# Pick the right package manager family up-front. Everything downstream goes
# through pkg_update / pkg_install so we never hard-code apt-get (which
# silently fails on RHEL/AlmaLinux/Rocky/Fedora, Arch, openSUSE, etc).
PKG_FAMILY="unknown"
case "$(uname -s)" in
    Darwin)
        PKG_FAMILY="macos"
        OS_ID="macos"
        ;;
    MINGW*|MSYS*|CYGWIN*)
        # Git Bash / MSYS / Cygwin on Windows — bash works but Docker, volume
        # mounts and the dashboard wizard's raw-tty handling do not. Hand off
        # to the proper Windows path.
        printf "\n${C_YELLOW}${C_BOLD}!${C_RESET}  Windows native shell detected (%s).\n" "$(uname -s)"
        printf "   WASP runs cleanly via WSL2. Two equally good options:\n\n"
        printf "   ${C_BOLD}1.${C_RESET} Use the PowerShell installer (does WSL2 + Docker checks for you):\n"
        printf "      ${C_CYAN}powershell -Command \"iwr -useb https://agentwasp.com/install.ps1 | iex\"${C_RESET}\n\n"
        printf "   ${C_BOLD}2.${C_RESET} Open WSL2 (Ubuntu) and run the standard one-liner there:\n"
        printf "      ${C_CYAN}wsl${C_RESET}  ${C_DIM}# then inside Ubuntu:${C_RESET}\n"
        printf "      ${C_CYAN}sudo bash -c \"\$(curl -fsSL https://agentwasp.com/install.sh)\"${C_RESET}\n\n"
        exit 1
        ;;
    Linux)
        case "$OS_ID" in
            ubuntu|debian|raspbian|linuxmint|pop|kali|elementary|deepin) PKG_FAMILY="debian" ;;
            rhel|centos|almalinux|rocky|ol|amzn)                          PKG_FAMILY="rhel" ;;
            fedora)                                                        PKG_FAMILY="fedora" ;;
            arch|manjaro|endeavouros|garuda)                              PKG_FAMILY="arch" ;;
            opensuse*|sles|suse)                                          PKG_FAMILY="suse" ;;
            alpine)                                                        PKG_FAMILY="alpine" ;;
            *)
                if   [[ "$OS_LIKE" == *"debian"* || "$OS_LIKE" == *"ubuntu"* ]]; then PKG_FAMILY="debian"
                elif [[ "$OS_LIKE" == *"rhel"*   || "$OS_LIKE" == *"centos"* ]]; then PKG_FAMILY="rhel"
                elif [[ "$OS_LIKE" == *"fedora"* ]];                              then PKG_FAMILY="fedora"
                elif [[ "$OS_LIKE" == *"arch"*   ]];                              then PKG_FAMILY="arch"
                elif [[ "$OS_LIKE" == *"suse"*   ]];                              then PKG_FAMILY="suse"
                fi
                ;;
        esac
        ;;
esac

if [[ "$PKG_FAMILY" == "unknown" ]]; then
    warn "Untested OS: $OS_ID (ID_LIKE: $OS_LIKE). Proceeding with best-effort fallbacks — manual package install may be needed."
fi
ok "OS: ${OS_ID} (family: ${PKG_FAMILY})"

# Hard requirement: anything other than Linux needs Docker Desktop, which we
# can't install non-interactively. macOS users still get the rest of the setup
# (CLI, .env, onboarding) once Docker is reachable.
if [[ "$PKG_FAMILY" == "macos" ]]; then
    if ! command -v docker >/dev/null 2>&1; then
        warn "macOS detected. Install Docker Desktop first: https://www.docker.com/products/docker-desktop"
        die "Docker is not installed. Install Docker Desktop, start it, then re-run this script."
    fi
fi

# ── Package manager abstractions ─────────────────────────────────────
# These wrap apt-get / dnf / yum / pacman / zypper / apk / brew so the rest of
# the installer doesn't care which distro we're on. Each exits non-zero on
# failure (caught by run_spin).
pkg_update() {
    case "$PKG_FAMILY" in
        debian)       $SUDO bash -c "DEBIAN_FRONTEND=noninteractive apt-get update -qq" ;;
        rhel|fedora)  if command -v dnf >/dev/null 2>&1; then
                          $SUDO dnf -y -q makecache
                      else
                          $SUDO yum -y -q makecache
                      fi ;;
        arch)         $SUDO pacman -Sy --noconfirm >/dev/null ;;
        suse)         $SUDO zypper --non-interactive refresh >/dev/null ;;
        alpine)       $SUDO apk update -q ;;
        macos)        command -v brew >/dev/null 2>&1 && brew update >/dev/null || true ;;
        *)            warn "Unknown package manager — skipping repo refresh." ;;
    esac
}
pkg_install() {
    case "$PKG_FAMILY" in
        debian)       $SUDO bash -c "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq $*" ;;
        rhel|fedora)  # `--allowerasing` lets dnf swap the minimal variants
                      # (curl-minimal, coreutils-single) for the full packages
                      # that ship with WASP's expected feature set. Without
                      # this, AlmaLinux/Rocky base images abort at this step.
                      if command -v dnf >/dev/null 2>&1; then
                          $SUDO dnf install -y -q --allowerasing "$@"
                      else
                          $SUDO yum install -y -q "$@"
                      fi ;;
        arch)         $SUDO pacman -S --needed --noconfirm "$@" >/dev/null ;;
        suse)         $SUDO zypper --non-interactive install --no-recommends "$@" >/dev/null ;;
        alpine)       $SUDO apk add --quiet --no-progress "$@" ;;
        macos)        if command -v brew >/dev/null 2>&1; then
                          brew install "$@" >/dev/null 2>&1 || true
                      fi ;;
        *)            warn "Cannot install on unknown OS: $*. Install manually and re-run." ; return 1 ;;
    esac
}
# Memory check — /proc/meminfo is Linux-only. macOS exposes total memory
# via sysctl hw.memsize (bytes). Default to 0 on detection failure so the
# downstream warning surfaces something actionable instead of crashing.
if [[ "$PKG_FAMILY" == "macos" ]]; then
    mem_bytes="$(sysctl -n hw.memsize 2>/dev/null || echo 0)"
    mem_gb=$(( mem_bytes / 1024 / 1024 / 1024 ))
else
    mem_kb="$(awk '/MemTotal/ {print $2}' /proc/meminfo 2>/dev/null || echo 0)"
    mem_gb=$(( mem_kb / 1024 / 1024 ))
fi
if (( mem_gb < 2 )); then
    warn "Only ${mem_gb}GB RAM detected. WASP needs ≥4GB for comfortable operation."
elif (( mem_gb < 4 )); then
    warn "${mem_gb}GB RAM detected. Below recommended 4GB."
else
    ok  "RAM: ${mem_gb}GB"
fi

cpus="$(nproc 2>/dev/null || echo 1)"
ok "CPU cores: ${cpus}"

# Resolve the parent dir for the df check. ${INSTALL_DIR%/*} strips the last
# component, but for a top-level path like /wasp that yields the empty string,
# which df rejects. Fall back to "/" in that case.
_parent_dir="${INSTALL_DIR%/*}"
[[ -z "$_parent_dir" ]] && _parent_dir="/"
# GNU df supports -BG (force GB block size); macOS/BSD df uses -g instead.
if [[ "$PKG_FAMILY" == "macos" ]]; then
    disk_avail_gb=$(df -g "$_parent_dir" 2>/dev/null | awk 'NR==2 {print $4}')
else
    disk_avail_gb=$(df -BG "$_parent_dir" 2>/dev/null | awk 'NR==2 {gsub("G",""); print $4}')
fi
# Strip anything non-numeric (e.g. df on busybox may report "1.5G")
disk_avail_gb="${disk_avail_gb%%[!0-9]*}"
disk_avail_gb=${disk_avail_gb:-0}
if (( disk_avail_gb < 5 )); then
    warn "Only ${disk_avail_gb}GB free at ${_parent_dir}. Recommend ≥10GB."
else
    ok  "Disk: ${disk_avail_gb}GB free"
fi

# Port check — `ss` is Linux-only. macOS ships `lsof` by default; use it
# there. Any failure to detect is non-fatal (just a warning), so the
# 2>/dev/null fallbacks are intentional.
for p in 8080 5432 6379; do
    in_use=false
    if [[ "$PKG_FAMILY" == "macos" ]]; then
        if lsof -nP -iTCP:${p} -sTCP:LISTEN 2>/dev/null | grep -q LISTEN; then
            in_use=true
        fi
    else
        if ss -ltn 2>/dev/null | awk '{print $4}' | grep -qE "[:.]${p}\$"; then
            in_use=true
        fi
    fi
    if $in_use; then
        warn "Port ${p} is in use — WASP service may conflict."
    fi
done

# ── [2/10] System packages ─────────────────────────────────────────────
step "System packages"
run_spin "Refreshing package index" pkg_update
# Base requirements. Some distros split tzdata into a different package — best
# effort, missing pieces will be re-installed via the Docker step or skipped.
run_spin "Installing curl git ca-certificates jq openssl tzdata rsync tar" \
    pkg_install curl git ca-certificates jq openssl tzdata rsync tar

# ── [3/10] Docker ──────────────────────────────────────────────────────
step "Docker"
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    ok "Docker + compose plugin already present"
elif [[ "$PKG_FAMILY" == "macos" ]]; then
    # macOS users get Docker Desktop, which provides docker + compose plugin.
    # We already validated docker exists above (otherwise we died); just verify
    # compose plugin works.
    if ! docker compose version >/dev/null 2>&1; then
        die "Docker is installed but 'docker compose' plugin is not. Update Docker Desktop and re-run."
    fi
    ok "Docker Desktop detected"
else
    info "Installing Docker Engine + compose plugin"
    case "$PKG_FAMILY" in
        debian)
            # get.docker.com handles Ubuntu/Debian/Raspbian/Mint/Kali/Pop/Elementary
            # cleanly — keeps install.sh small and uses Docker's official path.
            docker_script="$(mktemp)"
            curl -fsSL https://get.docker.com -o "$docker_script" || \
                die "Could not download get.docker.com. Check network and re-run."
            run_spin "Running Docker install script (~2 min)" $SUDO sh "$docker_script"
            rm -f "$docker_script"
            ;;
        rhel)
            # AlmaLinux, Rocky, CentOS Stream, RHEL, Oracle, Amazon Linux — all
            # use Docker's CentOS repo (binary-compatible). get.docker.com
            # explicitly rejects AlmaLinux, so we wire the repo ourselves.
            run_spin "Installing dnf-plugins-core" pkg_install dnf-plugins-core
            run_spin "Adding Docker CE repository (centos)" \
                $SUDO bash -c "if command -v dnf >/dev/null; then dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo; else yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo; fi"
            # Amazon Linux 2 needs the centos-7 repo path; AL2023+ uses centos-9
            run_spin "Installing docker-ce + plugins" \
                pkg_install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
            ;;
        fedora)
            run_spin "Installing dnf-plugins-core" pkg_install dnf-plugins-core
            run_spin "Adding Docker CE repository (fedora)" \
                $SUDO dnf config-manager --add-repo https://download.docker.com/linux/fedora/docker-ce.repo
            run_spin "Installing docker-ce + plugins" \
                pkg_install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
            ;;
        arch)
            run_spin "Installing docker + docker-compose" \
                pkg_install docker docker-compose docker-buildx
            ;;
        suse)
            run_spin "Installing docker + docker-compose" \
                pkg_install docker docker-compose
            ;;
        alpine)
            run_spin "Installing docker + docker-cli-compose" \
                pkg_install docker docker-cli-compose
            $SUDO rc-update add docker boot >/dev/null 2>&1 || true
            ;;
        *)
            die "Cannot install Docker on family '$PKG_FAMILY' automatically. Install Docker Engine + compose plugin manually, then re-run with --docker-only skipped."
            ;;
    esac

    # Enable + start the daemon (systemd on most distros)
    if command -v systemctl >/dev/null 2>&1; then
        $SUDO systemctl enable --now docker >/dev/null 2>&1 || true
    elif command -v rc-service >/dev/null 2>&1; then  # Alpine / OpenRC
        $SUDO rc-service docker start >/dev/null 2>&1 || true
    fi

    # Final verification
    if ! command -v docker >/dev/null 2>&1; then
        die "Docker CLI not found after install — see logs above for what failed."
    fi
    if ! docker compose version >/dev/null 2>&1; then
        die "Docker installed but 'docker compose' is missing. Install docker-compose-plugin manually and re-run."
    fi
    ok "Docker installed"
fi

# usermod is Linux-only and irrelevant on macOS — Docker Desktop manages
# the docker group automatically via its VM/host bridge.
if [[ "$PKG_FAMILY" != "macos" && "$EUID" -ne 0 ]] && id -nG "$USER" 2>/dev/null | grep -qvw docker; then
    $SUDO usermod -aG docker "$USER" 2>/dev/null || true
    warn "Added $USER to docker group — log out and back in (or 'newgrp docker') to apply."
fi

if $DOCKER_ONLY; then
    ok "Docker installed. --docker-only set; stopping here."
    exit 0
fi

# ── [4/10] Install destination ─────────────────────────────────────────
step "Install destination"
$SUDO mkdir -p "$INSTALL_DIR"
$SUDO chown -R "$(id -u):$(id -g)" "$INSTALL_DIR" 2>/dev/null || true
ok "Ready: $INSTALL_DIR"

# ── [5/10] Source ──────────────────────────────────────────────────────
step "Source"
if [[ "$INSTALL_METHOD" == "local" ]]; then
    [[ -n "$LOCAL_SOURCE" && -d "$LOCAL_SOURCE" ]] || \
        die "--install-method=local requires --local-source <existing dir>"
    run_spin "Copying source from $LOCAL_SOURCE" \
        rsync -a --delete \
        --exclude='.git/' --exclude='.env' --exclude='data/' \
        --exclude='__pycache__/' --exclude='node_modules/' \
        --exclude='release-prep/' \
        "${LOCAL_SOURCE}/" "${INSTALL_DIR}/"
elif [[ "$INSTALL_METHOD" == "tarball" ]]; then
    # Fetch the published release tarball, extract to a temp dir, then rsync.
    # This is the default when no local source is supplied — makes the install
    # command standalone (no separate bootstrap step needed).
    tmp="$(mktemp -d -t wasp-tarball-XXXXXX)"
    run_spin "Downloading WASP source" \
        curl -fsSL --retry 3 --retry-delay 2 "$TARBALL_URL" -o "${tmp}/wasp-release.tar.gz"
    run_spin "Extracting tarball" \
        tar -xzf "${tmp}/wasp-release.tar.gz" -C "$tmp"
    rm -f "${tmp}/wasp-release.tar.gz"
    run_spin "Copying source from tarball" \
        rsync -a --delete \
        --exclude='.git/' --exclude='.env' --exclude='data/' \
        --exclude='__pycache__/' --exclude='node_modules/' \
        --exclude='release-prep/' \
        "${tmp}/" "${INSTALL_DIR}/"
    rm -rf "$tmp"
else
    if [[ -d "${INSTALL_DIR}/.git" ]]; then
        info "Existing checkout — pulling latest on branch ${REPO_BRANCH}"
        git -C "$INSTALL_DIR" fetch --quiet origin "$REPO_BRANCH"
        git -C "$INSTALL_DIR" checkout --quiet "$REPO_BRANCH"
        git -C "$INSTALL_DIR" pull --quiet --ff-only origin "$REPO_BRANCH"
        ok "Source updated"
    else
        # Warn early if the user is using the default placeholder repo URL — this
        # is a recognizable org slug, not necessarily an existing public repo. If
        # the clone fails below, the user almost certainly needs WASP_REPO_URL.
        if [[ "$REPO_URL" == *"agentwasp/agentwasp"* ]]; then
            warn "Using default repo URL: $REPO_URL"
            warn "If you have your own fork, set WASP_REPO_URL to your fork's URL."
            warn "Example:  WASP_REPO_URL=https://github.com/you/wasp.git install.sh --install-method=git"
        fi
        tmp="$(mktemp -d)"
        run_spin "git clone $REPO_URL ($REPO_BRANCH)" \
            git clone --quiet --branch "$REPO_BRANCH" --single-branch "$REPO_URL" "$tmp"
        rsync -a "${tmp}/" "${INSTALL_DIR}/"
        rm -rf "$tmp"
        ok "Source ready"
    fi
fi

cd "$INSTALL_DIR"

# ── [6/10] CLI ────────────────────────────────────────────────────────
step "wasp CLI"
if [[ -f "${INSTALL_DIR}/bin/wasp" ]]; then
    chmod +x "${INSTALL_DIR}/bin/wasp"
    if [[ ! -L /usr/local/bin/wasp || "$(readlink /usr/local/bin/wasp)" != "${INSTALL_DIR}/bin/wasp" ]]; then
        $SUDO ln -sf "${INSTALL_DIR}/bin/wasp" /usr/local/bin/wasp
    fi
    ok "wasp → /usr/local/bin/wasp"
else
    warn "bin/wasp not found in source — CLI will not be available"
fi

# ── [7/10] .env ───────────────────────────────────────────────────────
step "Configuration"
ENV_FILE="${INSTALL_DIR}/.env"
ENV_EXAMPLE="${INSTALL_DIR}/.env.example"
if [[ ! -f "$ENV_FILE" ]]; then
    [[ -f "$ENV_EXAMPLE" ]] || die "Missing .env.example in source — cannot generate .env"
    cp "$ENV_EXAMPLE" "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    info "Generating secure secrets"
    pgpw="$(openssl rand -hex 24)"
    dashsec="$(openssl rand -hex 32)"
    mediasec="$(openssl rand -hex 32)"
    tmp="$(mktemp)"
    awk -v pg="$pgpw" -v ds="$dashsec" -v ms="$mediasec" '
        /^POSTGRES_PASSWORD=/      { print "POSTGRES_PASSWORD="     pg; next }
        /^DASHBOARD_SECRET=/       { print "DASHBOARD_SECRET="      ds; next }
        /^MEDIA_SIGNING_SECRET=/   { print "MEDIA_SIGNING_SECRET="  ms; next }
        { print }
    ' "$ENV_FILE" > "$tmp" && mv "$tmp" "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    ok ".env created with auto-generated secrets"
else
    ok ".env already exists — preserved"
fi

# ── [8/10] Onboarding ─────────────────────────────────────────────────
# stdin is the curl pipe when launched via `curl ... | bash`, so `-t 0`
# is false. Fall back to /dev/tty (readable on any real SSH session) so
# the wizard still runs in the most common install flow.
step "Onboarding"
ONBOARD_MARKER="${INSTALL_DIR}/.wasp-onboarded"
WIZARD_STDIN=""
if [[ -t 0 ]]; then
    WIZARD_STDIN="tty"
elif [[ -r /dev/tty ]]; then
    WIZARD_STDIN="/dev/tty"
fi

if [[ ! -f "$ONBOARD_MARKER" && "$NON_INTERACTIVE" != "true" && -n "$WIZARD_STDIN" ]]; then
    info "Launching onboarding wizard (re-run later: wasp onboard)"
    if [[ -x "${INSTALL_DIR}/bin/wasp" ]]; then
        if [[ "$WIZARD_STDIN" == "tty" ]]; then
            "${INSTALL_DIR}/bin/wasp" onboard --first-run || \
                warn "Onboarding incomplete — re-run with: wasp onboard"
        else
            "${INSTALL_DIR}/bin/wasp" onboard --first-run </dev/tty || \
                warn "Onboarding incomplete — re-run with: wasp onboard"
        fi
    fi
else
    ok "Onboarding skipped (non-interactive or already done)"
fi

# ── [9/10] Build & start (with UFW handling) ──────────────────────────
step "Build & start"
if $NO_START; then
    warn "--no-start set: skipping docker build and service start"
else
    # Open dashboard port in UFW only when the host binding is public.
    # The default bind is 127.0.0.1 (loopback only), in which case no
    # firewall rule is needed and opening 8080 would needlessly increase
    # the host's exposed-port surface.
    DASHBOARD_BIND_VAL="$(grep -E '^DASHBOARD_BIND=' "${INSTALL_DIR}/.env" 2>/dev/null | cut -d= -f2)"
    DASHBOARD_BIND_VAL="${DASHBOARD_BIND_VAL:-127.0.0.1}"
    if [[ "$DASHBOARD_BIND_VAL" == "0.0.0.0" ]] && \
       command -v ufw >/dev/null 2>&1 && \
       $SUDO ufw status 2>/dev/null | grep -q "Status: active"; then
        info "UFW firewall is active and DASHBOARD_BIND=0.0.0.0, opening port 8080"
        $SUDO ufw allow 8080/tcp >/dev/null 2>&1 || true
        ok "Port 8080 allowed in UFW"
    fi

    run_spin "Building containers (first time takes ~5 min)" \
        docker compose --project-directory "$INSTALL_DIR" build --pull

    # Init named-volume permissions so the non-root container user (UID 1000)
    # can write to /data subdirs. Docker creates named volumes owned by root
    # by default; without this, agent-core fails with PermissionError on first
    # run.  Use --no-start to provision volumes, then chown each via alpine.
    run_spin "Provisioning volumes" \
        docker compose --project-directory "$INSTALL_DIR" up --no-start
    project="$(basename "$INSTALL_DIR")"
    for vol in core-memory core-logs core-config core-backups core-shared core-screenshots core-uploads core-browser-sessions core-skills; do
        docker run --rm -v "${project}_${vol}:/data" alpine:latest chown -R 1000:1000 /data >/dev/null 2>&1 || true
    done
    ok "Volume permissions set (UID 1000)"

    run_spin "Starting services" \
        docker compose --project-directory "$INSTALL_DIR" up -d
fi

# ── [10/10] Health (with retry — agent-core takes ~30-60s to come up) ─
step "Health"
if $NO_START; then
    warn "Skipped (--no-start)"
else
    info "Waiting for dashboard to come up (up to 90s)..."
    dash_ok=false
    for attempt in $(seq 1 18); do
        if curl -fsS -o /dev/null -m 3 "http://127.0.0.1:8080" 2>/dev/null; then
            dash_ok=true
            break
        fi
        sleep 5
        printf "${C_DIM}  attempt %d/18 — still waiting...${C_RESET}\r" "$attempt"
    done
    printf "\033[K"
    if $dash_ok; then
        ok "Dashboard reachable on 127.0.0.1:8080"
    else
        warn "Dashboard not reachable yet — run: ${C_BOLD}wasp logs agent-core${C_RESET} to see why"
    fi
    # Run the full health check (non-quiet so user sees what failed)
    if [[ -x "${INSTALL_DIR}/bin/wasp" ]]; then
        "${INSTALL_DIR}/bin/wasp" health || true
    fi
fi

# ── Final summary ─────────────────────────────────────────────────────
hr
ok "${C_BOLD}🚀  WASP is installed${C_RESET}"
DASH_PORT=8080
# Read the host bind from .env to decide which URL to show. The default
# install binds the dashboard to 127.0.0.1 (loopback) for safety.
DASH_BIND="$(grep -E '^DASHBOARD_BIND=' "${INSTALL_DIR}/.env" 2>/dev/null | cut -d= -f2)"
DASH_BIND="${DASH_BIND:-127.0.0.1}"

if [[ "$DASH_BIND" == "0.0.0.0" ]]; then
    # Public bind. Compute a routable host IP for the summary line.
    HOST_IP=""
    if command -v hostname >/dev/null 2>&1; then
        HOST_IP="$(hostname -I 2>/dev/null | awk '{print $1}')" || HOST_IP=""
    fi
    if [[ -z "$HOST_IP" ]] && command -v ip >/dev/null 2>&1; then
        HOST_IP="$(ip -4 -o route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i==\"src\"){print $(i+1); exit}}')" || HOST_IP=""
    fi
    [[ -z "$HOST_IP" ]] && HOST_IP="localhost"
    DASH_URL="http://${HOST_IP}:${DASH_PORT}"
else
    # Loopback bind (default). The dashboard is reachable only from this host.
    DASH_URL="http://127.0.0.1:${DASH_PORT}"
fi

log ""
log "  ${C_BOLD}📊  Dashboard:${C_RESET}    ${C_CYAN}${DASH_URL}${C_RESET}"
log "  ${C_BOLD}📁  Install dir:${C_RESET}  ${INSTALL_DIR}"
log "  ${C_BOLD}⚙   Edit config:${C_RESET}  ${INSTALL_DIR}/.env"
log "  ${C_BOLD}🛠   CLI:${C_RESET}          wasp status | wasp logs | wasp health"
log ""
hr
log "Next steps:"
log "  1. Open the dashboard: ${C_CYAN}${DASH_URL}${C_RESET}"
log "  2. ${C_BOLD}wasp status${C_RESET}    see container states"
log "  3. ${C_BOLD}wasp logs${C_RESET}      stream live logs"
log "  4. ${C_BOLD}wasp health${C_RESET}    re-run health probes"
if [[ "$DASH_BIND" != "0.0.0.0" ]]; then
    log ""
    log "${C_DIM}Accessing the dashboard remotely:${C_RESET}"
    log "  The dashboard is bound to 127.0.0.1 for safety. To reach it from"
    log "  another machine, either SSH-tunnel:"
    log "    ${C_BOLD}ssh -L ${DASH_PORT}:127.0.0.1:${DASH_PORT} user@this-host${C_RESET}"
    log "    then open http://localhost:${DASH_PORT} on your local machine,"
    log "  or put a TLS reverse proxy (nginx / Caddy / traefik) in front."
    log "  Only set DASHBOARD_BIND=0.0.0.0 in .env after that is in place."
fi
hr
