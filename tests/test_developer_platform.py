from almond_ai import platform


def test_platform_branding_is_safe_off_windows(monkeypatch):
    monkeypatch.setattr(platform.sys, "platform", "linux")
    assert platform.apply_windows_console_branding() is False
