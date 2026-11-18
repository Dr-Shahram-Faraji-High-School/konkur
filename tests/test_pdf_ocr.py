from __future__ import annotations

import io
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import pdf_ocr


class FakePage:
    def __init__(self, text: str):
        self.text = text

    def get_text(self, _kind: str, sort: bool = False) -> str:
        return self.text


class FakeDocument:
    needs_pass = False

    def __init__(self, pages: list[FakePage]):
        self.pages = pages
        self.closed = False

    def __len__(self) -> int:
        return len(self.pages)

    def __getitem__(self, index: int) -> FakePage:
        return self.pages[index]

    def close(self) -> None:
        self.closed = True


class FakeOCR:
    def __init__(self):
        self.calls = 0

    def extract(self, _page: FakePage) -> str:
        self.calls += 1
        return "متن OCR"


class PDFOCRTests(unittest.TestCase):
    def test_natural_sort_orders_numbers_and_ignores_case(self):
        names = ["page10.pdf", "Page2.PDF", "page1.pdf"]
        self.assertEqual(
            sorted(names, key=pdf_ocr.natural_sort_key),
            ["page1.pdf", "Page2.PDF", "page10.pdf"],
        )

    def test_find_pdfs_accepts_single_pdf_and_sorts_folder(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("page10.pdf", "page2.PDF", "notes.txt"):
                (root / name).touch()

            self.assertEqual(
                [p.name for p in pdf_ocr.find_pdfs(root)],
                ["page2.PDF", "page10.pdf"],
            )
            self.assertEqual(
                pdf_ocr.find_pdfs(root / "page10.pdf"),
                [root / "page10.pdf"],
            )

    def test_find_pdfs_can_search_recursively(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "nested").mkdir()
            (root / "nested" / "scan.pdf").touch()

            with self.assertRaises(pdf_ocr.ToolError):
                pdf_ocr.find_pdfs(root)
            self.assertEqual(
                [p.name for p in pdf_ocr.find_pdfs(root, recursive=True)],
                ["scan.pdf"],
            )

    def test_default_output_path_is_next_to_the_input(self):
        self.assertEqual(
            pdf_ocr.default_output_path("/tmp/exam.pdf"),
            Path("/tmp/exam_ocr.txt"),
        )

    def test_clean_text_normalizes_line_endings_without_reordering_text(self):
        self.assertEqual(
            pdf_ocr.clean_text("  فارسی\r\n\r\n\r\nEnglish\x0c  "),
            "فارسی\n\nEnglish",
        )

    def test_embedded_text_is_kept_and_empty_page_uses_ocr(self):
        document = FakeDocument([FakePage("This page has native text."), FakePage("")])
        fake_pymupdf = types.ModuleType("pymupdf")
        fake_pymupdf.open = lambda _path: document
        ocr = FakeOCR()
        output = io.StringIO()

        with patch.dict("sys.modules", {"pymupdf": fake_pymupdf}):
            stats = pdf_ocr.extract_pdf(
                Path("sample.pdf"),
                "sample.pdf",
                output,
                ocr,
                min_native_chars=5,
            )

        self.assertEqual(stats.pages, 2)
        self.assertEqual(stats.text_pages, 1)
        self.assertEqual(stats.ocr_pages, 1)
        self.assertEqual(stats.failed_pages, 0)
        self.assertEqual(ocr.calls, 1)
        self.assertIn("This page has native text.", output.getvalue())
        self.assertIn("متن OCR", output.getvalue())
        self.assertTrue(document.closed)

    def test_force_ocr_uses_ocr_even_when_text_is_embedded(self):
        document = FakeDocument([FakePage("Embedded text")])
        fake_pymupdf = types.ModuleType("pymupdf")
        fake_pymupdf.open = lambda _path: document
        ocr = FakeOCR()

        with patch.dict("sys.modules", {"pymupdf": fake_pymupdf}):
            stats = pdf_ocr.extract_pdf(
                Path("sample.pdf"),
                "sample.pdf",
                io.StringIO(),
                ocr,
                force_ocr=True,
            )

        self.assertEqual(stats.ocr_pages, 1)
        self.assertEqual(stats.text_pages, 0)
        self.assertEqual(ocr.calls, 1)


if __name__ == "__main__":
    unittest.main()
