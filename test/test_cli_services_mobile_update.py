from __future__ import annotations

import json
import subprocess
from types import SimpleNamespace

import pytest

from cli.services import mobile_update


class _FakeGatewayHandle:
    def __init__(self) -> None:
        self.closed = False
        self.served = False
        self.summary = {
            "mobile_status": "serving",
            "listen": "127.0.0.1:8787",
            "gateway_url": "https://desktop.tailnet.ts.net:8787",
            "route_provider": "tailnet",
            "mode": "loopback_server_registry",
            "project_count": 2,
            "projects": [
                {"id": "proj-one", "display_name": "test_ccb2", "health": "healthy"},
                {"id": "proj-two", "display_name": "ccb_mobile", "health": "healthy"},
            ],
            "pairing": {
                "pairing_code": "pair-code",
                "claim_endpoint": "https://desktop.tailnet.ts.net:8787/v1/pairing/claim",
                "route_provider": "tailnet",
                "gateway_url": "https://desktop.tailnet.ts.net:8787",
                "scopes": ["project:view", "agent:message"],
            },
        }

    def serve_forever(self) -> None:
        self.served = True

    def close(self) -> None:
        self.closed = True


def _force_linux_tailscale_install(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        mobile_update,
        "_tailscale_install_command",
        lambda: mobile_update.TAILSCALE_LINUX_INSTALL_COMMAND,
    )


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
        return subprocess.CompletedProcess(
            command, 0, stdout=json.dumps(payload), stderr=""
        )

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
    public_port = commands.mobile_serve[
        commands.mobile_serve.index("--public-url") + 1
    ].rsplit(":", 1)[1]
    serve_https_port = commands.tailscale_serve[
        commands.tailscale_serve.index("--https=8787")
    ].split("=", 1)[1]
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
    assert "Step 1/3: install Tailscale on this computer" in text
    assert mobile_update.TAILSCALE_DOWNLOAD_URL in text
    assert "Skipping automatic install" in text
    assert "Install Tailscale and sign in to the same tailnet" in text
    assert f"Download APK: {mobile_update.DEFAULT_CCB_MOBILE_APP_DOWNLOAD_URL}" in text
    assert "adb install -r build/app/outputs/flutter-apk/app-debug.apk" not in text
    assert mobile_update.CCB_MOBILE_APP_DOWNLOAD_URL_ENV in text
    assert "no Funnel, tokens, ACLs, or grants" in text


def test_onboarding_not_installed_can_install_after_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _force_linux_tailscale_install(monkeypatch)
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
    assert "Next: run `tailscale up`" in text
    assert "The QR appears after this computer is signed in to Tailscale" in text


def test_onboarding_not_installed_can_install_from_explicit_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _force_linux_tailscale_install(monkeypatch)
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


def test_onboarding_not_installed_returns_install_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _force_linux_tailscale_install(monkeypatch)
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
    assert "Next: run `ccb update mobile` again" in text
    assert "starts the gateway and prints the QR" in text
    assert "After the next `ccb update mobile` prints a QR" in text


def test_onboarding_prints_configured_mobile_app_download_url() -> None:
    output: list[str] = []
    handle = _FakeGatewayHandle()

    code = mobile_update.run_mobile_update_onboarding(
        detect_tailscale_fn=lambda: mobile_update.TailscaleStatus(
            installed=True,
            path="/usr/bin/tailscale",
            logged_in=True,
            hostname="desktop.tailnet.ts.net.",
        ),
        prepare_gateway_fn=lambda _command: handle,
        run_fn=lambda command, **_kwargs: subprocess.CompletedProcess(
            command, 0, stdout="", stderr=""
        ),
        environ={
            mobile_update.CCB_MOBILE_APP_DOWNLOAD_URL_ENV: "https://example.test/ccb-mobile.apk"
        },
        print_fn=output.append,
        serve_forever=False,
        qr_ansi=False,
    )

    text = "\n".join(output)
    assert code == 0
    assert "Download APK: https://example.test/ccb-mobile.apk" in text
    assert mobile_update.DEFAULT_CCB_MOBILE_APP_DOWNLOAD_URL not in text
    assert "adb install -r build/app/outputs/flutter-apk/app-debug.apk" not in text
    assert "Open CCB Mobile, tap Scan computer QR" in text


def test_onboarding_logged_in_starts_gateway_serve_and_prints_qr() -> None:
    output: list[str] = []
    prepared: list[SimpleNamespace] = []
    run_commands: list[tuple[str, ...]] = []
    handle = _FakeGatewayHandle()

    code = mobile_update.run_mobile_update_onboarding(
        detect_tailscale_fn=lambda: mobile_update.TailscaleStatus(
            installed=True,
            path="/usr/bin/tailscale",
            logged_in=True,
            hostname="desktop.tailnet.ts.net.",
        ),
        prepare_gateway_fn=lambda command: prepared.append(command) or handle,
        run_fn=lambda command, **_kwargs: run_commands.append(tuple(command))
        or subprocess.CompletedProcess(command, 0, stdout="", stderr=""),
        print_fn=output.append,
        serve_forever=False,
        qr_ansi=False,
    )

    text = "\n".join(output)
    assert code == 0
    assert prepared == [
        SimpleNamespace(
            listen="127.0.0.1:8787",
            public_url="https://desktop.tailnet.ts.net:8787",
            route_provider="tailnet",
        )
    ]
    assert run_commands == [
        (
            "tailscale",
            "serve",
            "status",
            "--json",
        ),
        (
            "tailscale",
            "serve",
            "--bg",
            "--https=8787",
            "http://127.0.0.1:8787",
        )
    ]
    assert handle.closed is True
    assert "CCB Mobile is ready" in text
    assert "Computer gateway: https://desktop.tailnet.ts.net:8787" in text
    assert "Mounted projects available in the app: 2" in text
    assert "test_ccb2 (healthy)" not in text
    assert "ccb_mobile (healthy)" not in text
    assert "Scan this QR in CCB Mobile" in text
    assert "██" in text
    assert "Gateway URL: https://desktop.tailnet.ts.net:8787" in text
    assert "Pairing Code: pair-code" in text
    assert "no Funnel, tokens, ACLs, or grants" in text
    assert "ccb mobile serve" not in text
    assert "terminal WS:" not in text


def test_onboarding_logged_in_reuses_existing_tailscale_serve_config() -> None:
    output: list[str] = []
    run_commands: list[tuple[str, ...]] = []
    handle = _FakeGatewayHandle()
    serve_status = {
        "TCP": {"8787": {"HTTPS": True}},
        "Web": {
            "desktop.tailnet.ts.net:8787": {
                "Handlers": {"/": {"Proxy": "http://127.0.0.1:8787"}}
            }
        },
    }

    def _run(command, **_kwargs):
        run_commands.append(tuple(command))
        if tuple(command) == ("tailscale", "serve", "status", "--json"):
            return subprocess.CompletedProcess(
                command, 0, stdout=json.dumps(serve_status), stderr=""
            )
        raise AssertionError(f"unexpected command: {command!r}")

    code = mobile_update.run_mobile_update_onboarding(
        detect_tailscale_fn=lambda: mobile_update.TailscaleStatus(
            installed=True,
            path="/usr/bin/tailscale",
            logged_in=True,
            hostname="desktop.tailnet.ts.net.",
        ),
        prepare_gateway_fn=lambda _command: handle,
        run_fn=_run,
        print_fn=output.append,
        serve_forever=False,
        qr_ansi=False,
    )

    text = "\n".join(output)
    assert code == 0
    assert run_commands == [("tailscale", "serve", "status", "--json")]
    assert handle.closed is True
    assert "CCB Mobile is ready" in text
    assert "Scan this QR in CCB Mobile" in text
    assert "Could not start Tailscale Serve" not in text


def test_onboarding_logged_in_requires_pairing_qr_payload() -> None:
    output: list[str] = []
    handle = _FakeGatewayHandle()
    handle.summary = dict(handle.summary)
    handle.summary["pairing"] = {}

    code = mobile_update.run_mobile_update_onboarding(
        detect_tailscale_fn=lambda: mobile_update.TailscaleStatus(
            installed=True,
            path="/usr/bin/tailscale",
            logged_in=True,
            hostname="desktop.tailnet.ts.net.",
        ),
        prepare_gateway_fn=lambda _command: handle,
        run_fn=lambda command, **_kwargs: subprocess.CompletedProcess(
            command, 0, stdout="", stderr=""
        ),
        print_fn=output.append,
        serve_forever=False,
        qr_ansi=False,
    )

    text = "\n".join(output)
    assert code == 1
    assert handle.closed is True
    assert "Could not generate CCB Mobile pairing QR" in text
    assert "CCB Mobile is ready" not in text
    assert "Scan this QR in CCB Mobile" not in text


def test_onboarding_logged_in_serve_failure_closes_gateway() -> None:
    output: list[str] = []
    handle = _FakeGatewayHandle()

    code = mobile_update.run_mobile_update_onboarding(
        detect_tailscale_fn=lambda: mobile_update.TailscaleStatus(
            installed=True,
            path="/usr/bin/tailscale",
            logged_in=True,
            hostname="desktop.tailnet.ts.net.",
        ),
        prepare_gateway_fn=lambda _command: handle,
        run_fn=lambda command, **_kwargs: subprocess.CompletedProcess(
            command, 23, stdout="", stderr="serve failed"
        ),
        print_fn=output.append,
        serve_forever=False,
        qr_ansi=False,
    )

    assert code == 23
    assert handle.closed is True
    assert "Could not start Tailscale Serve: exit 23: serve failed" in "\n".join(output)


def test_onboarding_logged_in_serve_enable_prompt_is_actionable() -> None:
    output: list[str] = []
    opened: list[str] = []
    handle = _FakeGatewayHandle()
    enable_url = "https://login.tailscale.com/f/serve?node=node123"

    def _run(command, **_kwargs):
        raise subprocess.TimeoutExpired(
            command,
            timeout=15,
            output=(
                "Serve is not enabled on your tailnet.\n"
                "To enable, visit:\n\n"
                f"         {enable_url}\n"
            ),
        )

    code = mobile_update.run_mobile_update_onboarding(
        detect_tailscale_fn=lambda: mobile_update.TailscaleStatus(
            installed=True,
            path="/usr/bin/tailscale",
            logged_in=True,
            hostname="desktop.tailnet.ts.net.",
        ),
        prepare_gateway_fn=lambda _command: handle,
        run_fn=_run,
        open_url_fn=lambda url: opened.append(url) or True,
        print_fn=output.append,
        serve_forever=False,
        qr_ansi=False,
    )

    text = "\n".join(output)
    assert code == 0
    assert handle.closed is True
    assert opened == [enable_url]
    assert "Step 2/3: enable Tailscale Serve for this computer" in text
    assert "Tailscale requires one-time approval" in text
    assert f"Open: {enable_url}" in text
    assert "After approving, run `ccb update mobile` again" in text
    assert "Download APK:" in text
    assert "Could not start Tailscale Serve" not in text
    assert "TimeoutExpired" not in text
    assert "Scan this QR in CCB Mobile" not in text
