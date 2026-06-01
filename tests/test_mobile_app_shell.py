from pathlib import Path


def test_mobile_shell_defaults_to_web_app_tabs_and_live_metrics() -> None:
    app_tsx = Path("mobile/App.tsx").read_text(encoding="utf-8")
    app_shell = app_tsx[
        app_tsx.index("export default function App") : app_tsx.index("function FeaturePanel")
    ]

    assert 'useState<WebFeatureId>("clips")' in app_shell
    assert "Steampunk Compass" not in app_shell
    assert "Elliott Bay VHF" in app_shell
    assert "/api/clips/recent?limit=1" in app_shell
    assert 'Metric label="Clips"' in app_shell
    assert 'Metric label="Channels"' in app_shell
    assert 'Metric label="Latest"' in app_shell
    assert 'Metric label="Feed"' in app_shell


def test_mobile_feature_tabs_match_the_web_app() -> None:
    app_tsx = Path("mobile/App.tsx").read_text(encoding="utf-8")
    feature_items = app_tsx[
        app_tsx.index("const FEATURE_NAV_ITEMS") : app_tsx.index("const COMPASS_VIEWBOX")
    ]

    assert 'label: "Clip Review"' in feature_items
    assert 'label: "Live Monitor"' in feature_items
    assert 'label: "Map"' in feature_items
    assert 'label: "Analysis"' in feature_items
    assert 'label: "Performance"' in feature_items
    assert "Google federated login" not in feature_items
    assert 'label: "Compass"' not in feature_items


def test_mobile_clip_review_polls_like_the_web_header_metric() -> None:
    app_tsx = Path("mobile/App.tsx").read_text(encoding="utf-8")

    assert (
        'useJsonData<ClipsPayload>(`${MOBILE_API_BASE_URL}/api/clips/recent?limit=6`, 10000)'
        in app_tsx
    )
    assert "setTimeout(load, refreshMs)" in app_tsx
