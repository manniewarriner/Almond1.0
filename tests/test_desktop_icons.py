"""Standalone SVG-rendering regressions for desktop brand and nut marks."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication

from almond_ai.desktop.icons import _OVERSAMPLE, brand_mark_pixmap, nut_pixmap


@pytest.fixture(scope="module", autouse=True)
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _alpha_margins(pixmap: QPixmap) -> tuple[int, int, int, int]:
    image = pixmap.toImage()
    opaque = [
        (x, y)
        for y in range(image.height())
        for x in range(image.width())
        if image.pixelColor(x, y).alpha()
    ]
    assert opaque
    xs, ys = zip(*opaque, strict=True)
    return (
        min(xs),
        image.width() - 1 - max(xs),
        min(ys),
        image.height() - 1 - max(ys),
    )


def _assert_balanced_and_unclipped(pixmap: QPixmap) -> None:
    left, right, top, bottom = _alpha_margins(pixmap)
    assert min(left, right, top, bottom) >= _OVERSAMPLE
    assert abs(left - right) <= _OVERSAMPLE
    assert abs(top - bottom) <= _OVERSAMPLE


@pytest.mark.parametrize("size", [46, 128])
def test_brand_mark_has_balanced_standalone_margins(size: int):
    _assert_balanced_and_unclipped(
        brand_mark_pixmap("#E26F46", size, line_color="#FFFFFF")
    )


@pytest.mark.parametrize("nut", ["general", "walnut", "hazelnut", "almond", "pistachio"])
@pytest.mark.parametrize("size", [28, 44])
def test_nut_marks_have_balanced_standalone_margins(nut: str, size: int):
    # 44px covers quick-action cards; 28px covers sidebar bot rows.
    _assert_balanced_and_unclipped(nut_pixmap(nut, "#E26F46", size))
