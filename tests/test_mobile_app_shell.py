from pathlib import Path


def test_mobile_access_panel_lives_inside_cognito_feature_tab() -> None:
    app_tsx = Path("mobile/App.tsx").read_text(encoding="utf-8")
    auth_panel_start = app_tsx.index("function AuthPanel")
    auth_panel_end = app_tsx.index("function Metric")
    auth_panel = app_tsx[auth_panel_start:auth_panel_end]
    app_shell = app_tsx[
        app_tsx.index("export default function App") : app_tsx.index("function AuthPanel")
    ]

    assert "styles.authGrid" not in auth_panel
    assert 'accessibilityLabel={session ? "Sign out" : "Sign in with Google"}' in auth_panel
    assert '"cognito"' in app_shell
    assert "{activeFeatureId === \"cognito\" && <AuthPanel adminAuth={adminAuth} />}" in app_shell
    assert "Google federated login" in app_tsx


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


def test_mobile_compass_has_steampunk_gimbaled_instrument_details() -> None:
    app_tsx = Path("mobile/App.tsx").read_text(encoding="utf-8")

    assert "compassBodyTransform" in app_tsx
    assert "rotateX" in app_tsx
    assert "rotateY" in app_tsx
    assert "fixedNorthNeedleLayer" in app_tsx
    assert "frameStuds" in app_tsx
    assert 'id="brass"' in app_tsx
    assert "brass" in app_tsx.lower()


def test_mobile_compass_keeps_north_needle_fixed_while_body_rotates() -> None:
    app_tsx = Path("mobile/App.tsx").read_text(encoding="utf-8")
    compass_dial = app_tsx[
        app_tsx.index("function CompassDial") : app_tsx.index("function compassSensorLabel")
    ]

    assert "compassBodyRotation" in app_tsx
    assert "compassBodyTransform" in compass_dial
    assert "styles.fixedNorthNeedleLayer" in compass_dial
    assert "fixedNorthNeedleTransform" in compass_dial
    assert "needleRotation" not in app_tsx
