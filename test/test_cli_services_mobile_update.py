from __future__ import annotations

import json
import subprocess

import pytest

from cli.services import mobile_update


def test_detect_tailscale_reports_not_installed() -> None:
    status = mobile_update.detect_tailscale(which_fn=lambda _name: None)

    assert status.installed is False
    assert status.logged_in is False


def test_detect_tailscale_reports_installed_not_logged_in() -> None:
    def _run(command, **_kwargs):
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="Logged out")

    status = mobile_update.detect_tailscale(
        which_fn=lambda _name: "/usr/bin/tailscale",
        run_fn=_run,
    )

    assert status.installed is True
    assert status.path == "/usr/bin/tailscale"
    assert status.logged_in is False
    assert status.detail == "Logged out"


def test_detect_tailscale_reports_logged_in_tailnet_identity() -> None:
    payload = {
        "BackendState": "Running",
        "Self": {"DNSName": "desktop.tailnet.ts.net.", "HostName": "desktop"},
        "CurrentTailnet": {"Name": "example.ts.net"},
    }

    def _run(command, **_kwargs):
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps(payload), stderr="")

    status = mobile_update.detect_tailscale(
        which_fn=lambda _name: "/usr/bin/tailscale",
        run_fn=_run,
    )

    assert status.installed is True
    assert status.logged_in is True
    assert status.hostname == "desktop.tailnet.ts.net"
    assert status.tailnet == "example.ts.net"


def test_build_tailnet_commands_keep_gateway_loopback_and_no_funnel() -> None:
    commands = mobile_update.build_tailnet_onboarding_commands(
        status=mobile_update.TailscaleStatus(
            installed=True,
            path="/usr/bin/tailscale",
            logged_in=True,
            hostname="desktop.tailnet.ts.net",
        ),
    )

    assert commands.mobile_serve == (
        "ccb",
        "mobile",
        "serve",
        "--listen",
        "127.0.0.1:8787",
        "--public-url",
        "https://desktop.tailnet.ts.net:8787",
        "--route-provider",
        "tailnet",
    )
    assert commands.tailscale_serve == (
        "tailscale",
        "serve",
        "--bg",
        "--https=8787",
        "http://127.0.0.1:8787",
    )
    public_port = commands.mobile_serve[commands.mobile_serve.index("--public-url") + 1].rsplit(":", 1)[1]
    serve_https_port = commands.tailscale_serve[commands.tailscale_serve.index("--https=8787")].split("=", 1)[1]
    assert serve_https_port == public_port
    for command in (
        commands.mobile_serve,
        commands.tailscale_serve,
        commands.health_smoke,
        commands.route_diagnostics_smoke,
        commands.terminal_websocket_smoke,
    ):
        joined = " ".join(command)
        assert "0.0.0.0" not in joined
        assert "funnel" not in joined.lower()


def test_build_tailnet_commands_reject_public_listen() -> None:
    with pytest.raises(ValueError, match="loopback-only"):
        mobile_update.build_tailnet_onboarding_commands(
            status=mobile_update.TailscaleStatus(installed=True, logged_in=True),
            listen="0.0.0.0:8787",
        )


def test_onboarding_not_installed_prints_install_and_phone_steps() -> None:
    output: list[str] = []
    install_calls = 0

    def _install() -> int:
        nonlocal install_calls
        install_calls += 1
        return 0

    code = mobile_update.run_mobile_update_onboarding(
        detect_tailscale_fn=lambda: mobile_update.TailscaleStatus(installed=False),
        install_tailscale_fn=_install,
        print_fn=output.append,
    )

    text = "\n".join(output)
    assert code == 0
    assert install_calls == 0
    assert "Tailscale was not found" in text
    assert mobile_update.TAILSCALE_DOWNLOAD_URL in text
    assert "Skipping automatic install" in text
    assert "Install Tailscale on the phone" in text
    assert f"Download APK: {mobile_update.DEFAULT_CCB_MOBILE_APP_DOWNLOAD_URL}" in text
    assert "adb install -r build/app/outputs/flutter-apk/app-debug.apk" not in text
    assert mobile_update.CCB_MOBILE_APP_DOWNLOAD_URL_ENV in text
    assert "Funnel and 0.0.0.0 listeners are not used" in text


def test_onboarding_not_installed_can_install_after_prompt() -> None:
    output: list[str] = []
    prompts: list[str] = []
    install_calls = 0

    def _install() -> int:
        nonlocal install_calls
        install_calls += 1
        return 0

    code = mobile_update.run_mobile_update_onboarding(
        detect_tailscale_fn=lambda: mobile_update.TailscaleStatus(installed=False),
        install_tailscale_fn=_install,
        prompt_fn=lambda prompt: prompts.append(prompt) or "y",
        print_fn=output.append,
    )

    text = "\n".join(output)
    assert code == 0
    assert prompts == ["Install Tailscale now? [y/N] "]
    assert install_calls == 1
    assert "curl -fsSL https://tailscale.com/install.sh | sh" in text
    assert "official Tailscale install script" in text
    assert "Tailscale install command completed" in text
    assert "Then run `tailscale up`" in text


def test_onboarding_not_installed_can_install_from_explicit_env() -> None:
    output: list[str] = []
    install_calls = 0

    def _install() -> int:
        nonlocal install_calls
        install_calls += 1
        return 0

    code = mobile_update.run_mobile_update_onboarding(
        detect_tailscale_fn=lambda: mobile_update.TailscaleStatus(installed=False),
        install_tailscale_fn=_install,
        environ={"CCB_UPDATE_MOBILE_INSTALL_TAILSCALE": "1"},
        print_fn=output.append,
    )

    text = "\n".join(output)
    assert code == 0
    assert install_calls == 1
    assert "Installing because CCB_UPDATE_MOBILE_INSTALL_TAILSCALE=1 is set" in text
    assert "Tailscale install command completed" in text


def test_onboarding_not_installed_returns_install_failure() -> None:
    output: list[str] = []

    code = mobile_update.run_mobile_update_onboarding(
        detect_tailscale_fn=lambda: mobile_update.TailscaleStatus(installed=False),
        install_tailscale_fn=lambda: 17,
        prompt_fn=lambda _prompt: "yes",
        print_fn=output.append,
    )

    assert code == 17
    assert "Tailscale install command failed with exit code 17" in "\n".join(output)


def test_onboarding_logged_out_prints_login_and_can_open_url() -> None:
    output: list[str] = []
    opened: list[str] = []

    code = mobile_update.run_mobile_update_onboarding(
        detect_tailscale_fn=lambda: mobile_update.TailscaleStatus(
            installed=True,
            path="/usr/bin/tailscale",
            logged_in=False,
        ),
        environ={"CCB_UPDATE_MOBILE_OPEN_LOGIN": "1"},
        open_url_fn=opened.append,
        print_fn=output.append,
    )

    text = "\n".join(output)
    assert code == 0
    assert opened == [mobile_update.TAILSCALE_LOGIN_URL]
    assert "tailscale up" in text
    assert "Login/register" in text
    assert "After login completes, re-run: ccb update mobile" in text
    assert "mobile gateway, Tailscale Serve, and pairing QR steps" in text
    assert "Open CCB Mobile and scan the pairing QR" in text


def test_onboarding_prints_configured_mobile_app_download_url() -> None:
    output: list[str] = []

    code = mobile_update.run_mobile_update_onboarding(
        detect_tailscale_fn=lambda: mobile_update.TailscaleStatus(
            installed=True,
            path="/usr/bin/tailscale",
            logged_in=True,
            hostname="desktop.tailnet.ts.net.",
        ),
        environ={mobile_update.CCB_MOBILE_APP_DOWNLOAD_URL_ENV: "https://example.test/ccb-mobile.apk"},
        print_fn=output.append,
    )

    text = "\n".join(output)
    assert code == 0
    assert "Download APK: https://example.test/ccb-mobile.apk" in text
    assert mobile_update.DEFAULT_CCB_MOBILE_APP_DOWNLOAD_URL not in text
    assert "adb install -r build/app/outputs/flutter-apk/app-debug.apk" not in text
    assert "Open CCB Mobile and scan the pairing QR" in text


def test_onboarding_logged_in_prints_serve_qr_and_smoke_shapes() -> None:
    output: list[str] = []

    code = mobile_update.run_mobile_update_onboarding(
        detect_tailscale_fn=lambda: mobile_update.TailscaleStatus(
            installed=True,
            path="/usr/bin/tailscale",
            logged_in=True,
            hostname="desktop.tailnet.ts.net.",
        ),
        print_fn=output.append,
    )

    text = "\n".join(output)
    assert code == 0
    assert "ccb mobile serve --listen 127.0.0.1:8787" in text
    assert "--route-provider tailnet" in text
    assert "tailscale serve --bg --https=8787 http://127.0.0.1:8787" in text
    assert "pairing QR" in text
    assert "health:" in text
    assert "diagnostics:" in text
    assert "terminal WS:" in text
    assert "revoke gate:" in text
    assert "Funnel and 0.0.0.0 listeners are not used" in text
    command_lines = [line for line in output if line.startswith("   ccb ") or line.startswith("   tailscale ")]
    assert all("0.0.0.0" not in line for line in command_lines)
