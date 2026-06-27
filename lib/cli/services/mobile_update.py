from __future__ import annotations

from dataclasses import dataclass
import json
import os
import platform
import shutil
import subprocess
import sys
import webbrowser
from collections.abc import Callable, Mapping, Sequence


TAILSCALE_DOWNLOAD_URL = "https://tailscale.com/download"
TAILSCALE_LOGIN_URL = "https://login.tailscale.com/start"
DEFAULT_MOBILE_GATEWAY_LISTEN = "127.0.0.1:8787"
CCB_MOBILE_APP_DOWNLOAD_URL_ENV = "CCB_MOBILE_APP_DOWNLOAD_URL"
DEFAULT_CCB_MOBILE_APP_DOWNLOAD_URL = (
    "https://github.com/SeemSeam/claude_codex_bridge/releases/download/"
    "v8.0.0/ccb-mobile-v8.0.0.apk"
)
TAILSCALE_LINUX_INSTALL_COMMAND = ("sh", "-c", "curl -fsSL https://tailscale.com/install.sh | sh")


@dataclass(frozen=True)
class TailscaleStatus:
    installed: bool
    path: str | None = None
    logged_in: bool = False
    hostname: str | None = None
    tailnet: str | None = None
    detail: str | None = None


@dataclass(frozen=True)
class TailnetOnboardingCommands:
    mobile_serve: tuple[str, ...]
    tailscale_serve: tuple[str, ...]
    health_smoke: tuple[str, ...]
    route_diagnostics_smoke: tuple[str, ...]
    terminal_websocket_smoke: tuple[str, ...]
    revoke_gate_smoke: tuple[str, ...]


def run_mobile_update_onboarding(
    *,
    detect_tailscale_fn: Callable[[], TailscaleStatus] | None = None,
    install_tailscale_fn: Callable[[], int] | None = None,
    open_url_fn: Callable[[str], object] | None = None,
    prompt_fn: Callable[[str], str] | None = None,
    environ: Mapping[str, str] | None = None,
    print_fn: Callable[[str], None] = print,
) -> int:
    detect_tailscale_fn = detect_tailscale_fn or detect_tailscale
    install_tailscale_fn = install_tailscale_fn or install_tailscale
    env = os.environ if environ is None else environ
    open_url_fn = open_url_fn or webbrowser.open
    status = detect_tailscale_fn()

    print_fn("🔧 CCB Mobile Tailnet onboarding")
    print_fn("   This updates local mobile setup guidance only; it does not update the CCB release.")
    print_fn("   Safety: gateway stays loopback-only; Tailscale Funnel and 0.0.0.0 listeners are not used.")
    print_fn("   No Tailscale passwords, OAuth tokens, admin API tokens, ACLs, or grants are stored or changed.")
    print_fn("")

    if not status.installed:
        print_fn("❌ Tailscale was not found on PATH.")
        print_fn(f"   Install Tailscale: {TAILSCALE_DOWNLOAD_URL}")
        print_fn(f"   Suggested install: {_tailscale_install_hint()}")
        install_result = _maybe_install_tailscale(
            environ=env,
            install_tailscale_fn=install_tailscale_fn,
            open_url_fn=open_url_fn,
            prompt_fn=prompt_fn,
            print_fn=print_fn,
        )
        if install_result is not None and install_result != 0:
            return install_result
        print_fn("   Then run `tailscale up` and re-run `ccb update mobile`.")
        print_fn("")
        _print_mobile_app_steps(print_fn, environ=env)
        return 0

    print_fn(f"✅ Tailscale detected: {status.path or 'tailscale'}")
    if not status.logged_in:
        print_fn("⚠️  Tailscale is installed but not logged in.")
        print_fn("   Run: tailscale up")
        print_fn(f"   Login/register: {TAILSCALE_LOGIN_URL}")
        print_fn("   After login completes, re-run: ccb update mobile")
        print_fn("   The next run will print the mobile gateway, Tailscale Serve, and pairing QR steps.")
        if _should_open_login(env):
            open_url_fn(TAILSCALE_LOGIN_URL)
            print_fn("   Opened the Tailscale login/register page.")
        print_fn("")
        _print_mobile_app_steps(print_fn, environ=env)
        return 0

    print_fn("✅ Tailscale is logged in.")
    commands = build_tailnet_onboarding_commands(status=status)
    print_fn("")
    print_fn("Start the loopback-only CCB Mobile gateway in one terminal:")
    print_fn(f"   {_shell_join(commands.mobile_serve)}")
    print_fn("")
    print_fn("Expose that loopback gateway to your tailnet in another terminal:")
    print_fn(f"   {_shell_join(commands.tailscale_serve)}")
    print_fn("   This uses Tailscale Serve only; it does not enable Funnel.")
    print_fn("")
    _print_mobile_app_steps(print_fn, environ=env)
    print_fn("")
    print_fn("After `ccb mobile serve` prints the pairing QR, scan it from CCB Mobile.")
    print_fn("")
    print_fn("Dry-run/simulated smoke command shapes:")
    print_fn(f"   health:       {_shell_join(commands.health_smoke)}")
    print_fn(f"   diagnostics:  {_shell_join(commands.route_diagnostics_smoke)}")
    print_fn(f"   terminal WS:  {_shell_join(commands.terminal_websocket_smoke)}")
    print_fn(f"   revoke gate:  {_shell_join(commands.revoke_gate_smoke)}")
    return 0


def detect_tailscale(
    *,
    which_fn: Callable[[str], str | None] = shutil.which,
    run_fn: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> TailscaleStatus:
    path = which_fn("tailscale")
    if not path:
        return TailscaleStatus(installed=False)
    try:
        result = run_fn(
            [path, "status", "--json"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception as exc:
        return TailscaleStatus(
            installed=True,
            path=path,
            detail=f"{type(exc).__name__}: {exc}",
        )
    if result.returncode != 0:
        detail = (
            (result.stderr or result.stdout or "").strip()
            or f"tailscale status exited {result.returncode}"
        )
        return TailscaleStatus(installed=True, path=path, logged_in=False, detail=detail)
    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError as exc:
        return TailscaleStatus(
            installed=True,
            path=path,
            logged_in=False,
            detail=f"invalid status json: {exc}",
        )
    backend_state = str(payload.get("BackendState") or "").strip().lower()
    self_node = payload.get("Self") if isinstance(payload.get("Self"), dict) else {}
    hostname = _clean_dns_name(self_node.get("DNSName")) or _clean_text(self_node.get("HostName"))
    tailnet_record = payload.get("CurrentTailnet") if isinstance(payload.get("CurrentTailnet"), dict) else {}
    tailnet = _clean_text(tailnet_record.get("Name")) or _clean_text(tailnet_record.get("MagicDNSSuffix"))
    logged_in = backend_state == "running" and bool(self_node)
    return TailscaleStatus(
        installed=True,
        path=path,
        logged_in=logged_in,
        hostname=hostname,
        tailnet=tailnet,
        detail=backend_state or None,
    )


def install_tailscale(
    *,
    run_fn: Callable[..., subprocess.CompletedProcess[object]] = subprocess.run,
) -> int:
    command = _tailscale_install_command()
    if command is None:
        return 2
    return run_fn(command).returncode


def build_tailnet_onboarding_commands(
    *,
    status: TailscaleStatus,
    listen: str = DEFAULT_MOBILE_GATEWAY_LISTEN,
) -> TailnetOnboardingCommands:
    host, port = _split_loopback_listen(listen)
    public_url = _tailnet_public_url(status, port=port)
    mobile_serve = (
        "ccb",
        "mobile",
        "serve",
        "--listen",
        f"{host}:{port}",
        "--public-url",
        public_url,
        "--route-provider",
        "tailnet",
    )
    tailscale_serve = (
        "tailscale",
        "serve",
        "--bg",
        f"--https={port}",
        f"http://{host}:{port}",
    )
    return TailnetOnboardingCommands(
        mobile_serve=mobile_serve,
        tailscale_serve=tailscale_serve,
        health_smoke=("curl", "-fsS", f"http://{host}:{port}/v1/health"),
        route_diagnostics_smoke=("tailscale", "serve", "status"),
        terminal_websocket_smoke=(
            "python",
            "-m",
            "websockets",
            f"ws://{host}:{port}/v1/terminals/<terminal_id>",
        ),
        revoke_gate_smoke=("ccb", "mobile", "revoke", "<device_id>"),
    )


def _tailnet_public_url(status: TailscaleStatus, *, port: str) -> str:
    hostname = _clean_dns_name(status.hostname) or "your-device.tailnet.ts.net"
    return f"https://{hostname}:{port}"


def _split_loopback_listen(value: str) -> tuple[str, str]:
    text = str(value or "").strip()
    if ":" not in text:
        raise ValueError("listen must be host:port")
    host, port = text.rsplit(":", 1)
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("mobile tailnet onboarding keeps the gateway loopback-only")
    if not port.isdigit() or int(port) <= 0:
        raise ValueError("listen port must be a positive integer")
    return host, port


def _tailscale_install_hint() -> str:
    system = platform.system()
    if system == "Darwin":
        return "brew install --cask tailscale  # or install from tailscale.com/download"
    if system == "Linux":
        return _shell_join(TAILSCALE_LINUX_INSTALL_COMMAND)
    return "install Tailscale from tailscale.com/download"


def _tailscale_install_command() -> tuple[str, ...] | None:
    if platform.system() == "Linux":
        return TAILSCALE_LINUX_INSTALL_COMMAND
    return None


def _maybe_install_tailscale(
    *,
    environ: Mapping[str, str],
    install_tailscale_fn: Callable[[], int],
    open_url_fn: Callable[[str], object],
    prompt_fn: Callable[[str], str] | None,
    print_fn: Callable[[str], None],
) -> int | None:
    command = _tailscale_install_command()
    if command is None:
        if _confirm_tailscale_install(environ=environ, prompt_fn=prompt_fn):
            open_url_fn(TAILSCALE_DOWNLOAD_URL)
            print_fn("   Opened the Tailscale download page.")
        else:
            _print_install_confirmation_hint(print_fn)
        return None

    print_fn("   You can install Tailscale now from this command.")
    print_fn("   This runs the official Tailscale install script and may ask for sudo.")
    print_fn(f"   Command: {_shell_join(command)}")
    if not _confirm_tailscale_install(environ=environ, prompt_fn=prompt_fn):
        _print_install_confirmation_hint(print_fn)
        return None

    if _install_forced_by_env(environ):
        print_fn("   Installing because CCB_UPDATE_MOBILE_INSTALL_TAILSCALE=1 is set.")
    print_fn("   Installing Tailscale...")
    result = install_tailscale_fn()
    if result == 0:
        print_fn("✅ Tailscale install command completed.")
    else:
        print_fn(f"❌ Tailscale install command failed with exit code {result}.")
    return result


def _confirm_tailscale_install(
    *,
    environ: Mapping[str, str],
    prompt_fn: Callable[[str], str] | None,
) -> bool:
    if _install_forced_by_env(environ):
        return True
    force_value = _clean_text(environ.get("CCB_UPDATE_MOBILE_INSTALL_TAILSCALE"))
    if force_value and force_value.lower() in {"0", "false", "no", "off"}:
        return False
    if prompt_fn is None and not sys.stdin.isatty():
        return False
    answer = prompt_fn("Install Tailscale now? [y/N] ") if prompt_fn else input("Install Tailscale now? [y/N] ")
    return str(answer or "").strip().lower() in {"y", "yes"}


def _install_forced_by_env(environ: Mapping[str, str]) -> bool:
    return str(environ.get("CCB_UPDATE_MOBILE_INSTALL_TAILSCALE") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _print_install_confirmation_hint(print_fn: Callable[[str], None]) -> None:
    print_fn("   Skipping automatic install.")
    print_fn("   Re-run in an interactive terminal, or set CCB_UPDATE_MOBILE_INSTALL_TAILSCALE=1 to install.")


def _print_mobile_app_steps(print_fn: Callable[[str], None], *, environ: Mapping[str, str]) -> None:
    app_download_url = (
        _clean_text(environ.get(CCB_MOBILE_APP_DOWNLOAD_URL_ENV))
        or DEFAULT_CCB_MOBILE_APP_DOWNLOAD_URL
    )
    print_fn("Phone setup:")
    print_fn("   1. Install Tailscale on the phone and sign in to the same tailnet.")
    print_fn("   2. Install CCB Mobile on the phone:")
    print_fn(f"      Download APK: {app_download_url}")
    print_fn(f"      Override this link with {CCB_MOBILE_APP_DOWNLOAD_URL_ENV} if your team mirrors the APK.")
    print_fn("   3. Enable the Tailscale VPN on the phone.")
    print_fn("   4. Open CCB Mobile and scan the pairing QR.")


def _should_open_login(environ: Mapping[str, str]) -> bool:
    return str(environ.get("CCB_UPDATE_MOBILE_OPEN_LOGIN") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _clean_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _clean_dns_name(value: object) -> str | None:
    text = _clean_text(value)
    if text:
        return text.rstrip(".")
    return None


def _shell_join(command: Sequence[str]) -> str:
    return " ".join(_quote_shell_part(part) for part in command)


def _quote_shell_part(value: object) -> str:
    text = str(value)
    if not text:
        return "''"
    safe = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_+-=.,/:@%"
    if all(ch in safe for ch in text):
        return text
    return "'" + text.replace("'", "'\"'\"'") + "'"


__all__ = [
    "DEFAULT_MOBILE_GATEWAY_LISTEN",
    "CCB_MOBILE_APP_DOWNLOAD_URL_ENV",
    "DEFAULT_CCB_MOBILE_APP_DOWNLOAD_URL",
    "TAILSCALE_LINUX_INSTALL_COMMAND",
    "TAILSCALE_DOWNLOAD_URL",
    "TAILSCALE_LOGIN_URL",
    "TailnetOnboardingCommands",
    "TailscaleStatus",
    "build_tailnet_onboarding_commands",
    "detect_tailscale",
    "install_tailscale",
    "run_mobile_update_onboarding",
]
