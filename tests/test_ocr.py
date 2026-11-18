from pathlib import Path

import pytest

from PIL import Image
from rapidocr.utils.output import RapidOCROutput

from backend.app.modules.readings import ocr


def test_local_ocr_reads_each_page_separately_and_reports_confidence(tmp_path, monkeypatch):
    image_path = Path(tmp_path) / "spread.jpg"
    Image.new("RGB", (1200, 700), "white").save(image_path)
    outputs = iter(
        [
            RapidOCROutput(txts=("Left page line one", "Left page line two"), scores=(0.95, 0.85)),
            RapidOCROutput(txts=("Right page line one",), scores=(0.9,)),
        ]
    )

    class FakeEngine:
        def __call__(self, _image: Image.Image) -> RapidOCROutput:
            return next(outputs)

    monkeypatch.setattr(ocr, "engine", lambda: FakeEngine())
    result = ocr.extract_pages(image_path)

    assert result.left == "Left page line one\nLeft page line two"
    assert result.right == "Right page line one"
    assert result.readable and result.confidence == pytest.approx(0.9)
    assert result.warnings == []


def test_local_ocr_marks_missing_page_unreadable(tmp_path, monkeypatch):
    image_path = Path(tmp_path) / "spread.jpg"
    Image.new("RGB", (1200, 700), "white").save(image_path)
    outputs = iter(
        [RapidOCROutput(txts=("Only one page",), scores=(0.95,)), RapidOCROutput()]
    )

    class FakeEngine:
        def __call__(self, _image: Image.Image) -> RapidOCROutput:
            return next(outputs)

    monkeypatch.setattr(ocr, "engine", lambda: FakeEngine())
    result = ocr.extract_pages(image_path)

    assert not result.readable
    assert any("both pages" in warning for warning in result.warnings)
