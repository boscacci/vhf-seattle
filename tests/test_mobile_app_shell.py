from pathlib import Path


def test_mobile_access_panel_puts_sign_in_before_provider_cards() -> None:
    app_tsx = Path("mobile/App.tsx").read_text(encoding="utf-8")
    auth_panel_start = app_tsx.index("function AuthPanel")
    auth_panel_end = app_tsx.index("function Metric")
    auth_panel = app_tsx[auth_panel_start:auth_panel_end]
    app_shell = app_tsx[app_tsx.index("export default function App"):app_tsx.index("function AuthPanel")]

    assert "styles.authGrid" not in auth_panel
    assert 'accessibilityLabel={session ? "Sign out of Cognito" : "Sign in with Cognito"}' in auth_panel
    assert app_shell.index("<AuthPanel") < app_shell.index("<FeaturePanel")


def test_mobile_landing_removes_starter_copy_and_button_game() -> None:
    app_tsx = Path("mobile/App.tsx").read_text(encoding="utf-8")

    for removed_copy in (
        "Hello world",
        "Dev shell",
        "Tap the bridge",
        "pulses",
        "Motion fusion",
    ):
        assert removed_copy not in app_tsx

    assert "signalRow" not in app_tsx
    assert "signalPulse" not in app_tsx
    assert "FeaturePanel" in app_tsx
