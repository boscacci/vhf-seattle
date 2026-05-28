from pathlib import Path


def test_mobile_access_panel_puts_sign_in_before_provider_cards() -> None:
    app_tsx = Path("mobile/App.tsx").read_text(encoding="utf-8")
    auth_panel_start = app_tsx.index("function AuthPanel")
    auth_panel_end = app_tsx.index("function Metric")
    auth_panel = app_tsx[auth_panel_start:auth_panel_end]

    assert auth_panel.index("styles.authAction") < auth_panel.index("styles.authGrid")
    assert 'accessibilityLabel={session ? "Sign out of Cognito" : "Sign in with Cognito"}' in auth_panel
