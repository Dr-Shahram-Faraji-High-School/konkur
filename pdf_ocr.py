#!/usr/bin/env python3
"""Extract text from PDF files, using Tesseract OCR for scanned pages."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO


class ToolError(Exception):
    """An actionable error that can be shown directly to the user."""


class OCRSetupError(ToolError):
    """The local OCR engine or one of its language packs is unavailable."""


class PDFReadError(ToolError):
    """A PDF could not be opened or read."""


def natural_sort_key(value: str | Path) -> tuple[tuple[int, object], ...]:
    """Sort names like page2.pdf before page10.pdf, without case sensitivity."""
    parts = re.split(r"(\d+)", str(value))
    return tuple(
        (1, int(part)) if part.isdigit() else (0, part.casefold())
        for part in parts
    )


def find_pdfs(input_path: str | Path, recursive: bool = False) -> list[Path]:
    """Return one PDF or the PDFs in a directory in natural filename order."""
    target = Path(input_path).expanduser()
    if not target.exists():
        raise ToolError(f"مسیر پیدا نشد: {target}")

    if target.is_file():
        if target.suffix.lower() != ".pdf":
            raise ToolError(f"فایل ورودی PDF نیست: {target}")
        return [target]

    if not target.is_dir():
        raise ToolError(f"مسیر ورودی فایل یا پوشهٔ قابل‌خواندن نیست: {target}")

    candidates = target.rglob("*") if recursive else target.iterdir()
    pdfs = sorted(
        (path for path in candidates if path.is_file() and path.suffix.lower() == ".pdf"),
        key=lambda path: natural_sort_key(path.relative_to(target)),
    )
    if not pdfs:
        scope = "و زیرپوشه‌های آن" if recursive else ""
        raise ToolError(f"هیچ فایل PDF در این پوشه {scope} پیدا نشد: {target}")
    return pdfs


def default_output_path(input_path: str | Path) -> Path:
    """Choose a .txt file next to the selected PDF or folder."""
    target = Path(input_path).expanduser()
    if target.is_dir():
        resolved = target.resolve()
        folder_name = resolved.name or "pdfs"
        return resolved.parent / f"{folder_name}_ocr.txt"
    return target.with_name(f"{target.stem}_ocr.txt")


def clean_text(text: str | None) -> str:
    """Normalize line endings and excess whitespace without altering RTL text."""
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x0c", "")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def needs_ocr(native_text: str, force_ocr: bool, min_native_chars: int) -> bool:
    """OCR pages without a sufficiently long embedded text layer."""
    if force_ocr:
        return True
    visible_chars = sum(not char.isspace() for char in native_text)
    return visible_chars < min_native_chars


def import_pymupdf():
    try:
        import pymupdf
    except ImportError as exc:
        raise ToolError(
            "کتابخانهٔ PyMuPDF نصب نیست. ابتدا دستور «python -m pip install -r requirements.txt» را اجرا کنید."
        ) from exc
    return pymupdf


class OCRProcessor:
    """Lazy-loaded Tesseract OCR wrapper; no OCR setup is needed for text PDFs."""

    def __init__(
        self,
        language: str = "fas+eng",
        dpi: int = 300,
        psm: int = 3,
        tesseract_cmd: str | None = None,
    ) -> None:
        self.language = language
        self.dpi = dpi
        self.psm = psm
        self.tesseract_cmd = tesseract_cmd
        self._pytesseract = None
        self._image_class = None

    def _load(self) -> None:
        if self._pytesseract is not None:
            return

        try:
            from PIL import Image
            import pytesseract
        except ImportError as exc:
            raise OCRSetupError(
                "وابستگی‌های OCR نصب نیستند. دستور «python -m pip install -r requirements.txt» را اجرا کنید."
            ) from exc

        command = self.tesseract_cmd or os.environ.get("TESSERACT_CMD") or "tesseract"
        executable = shutil.which(command)
        if executable is None and Path(command).is_file():
            executable = str(Path(command).resolve())
        if executable is None:
            raise OCRSetupError(
                "برنامهٔ Tesseract پیدا نشد. آن را نصب کنید یا مسیر آن را با گزینهٔ --tesseract-cmd بدهید."
            )
        pytesseract.pytesseract.tesseract_cmd = executable

        try:
            installed_languages = set(pytesseract.get_languages(config=""))
        except Exception as exc:
            raise OCRSetupError(
                "اجرای Tesseract ناموفق بود؛ نصب آن و مسیر فایل‌های زبان را بررسی کنید. "
                f"جزئیات: {exc}"
            ) from exc

        requested_languages = [part.strip() for part in self.language.split("+") if part.strip()]
        missing_languages = [lang for lang in requested_languages if lang not in installed_languages]
        if not requested_languages:
            raise OCRSetupError("گزینهٔ زبان OCR خالی است. برای نمونه از --lang fas+eng استفاده کنید.")
        if missing_languages:
            missing = ", ".join(missing_languages)
            raise OCRSetupError(
                f"دادهٔ زبان OCR نصب نیست: {missing}. برای فارسی و انگلیسی، بسته‌های fas و eng را برای Tesseract نصب کنید."
            )

        self._pytesseract = pytesseract
        self._image_class = Image

    def extract(self, page) -> str:
        self._load()
        fitz = import_pymupdf()
        scale = self.dpi / 72.0
        pixmap = page.get_pixmap(
            matrix=fitz.Matrix(scale, scale),
            colorspace=fitz.csRGB,
            alpha=False,
        )
        image = self._image_class.frombytes(
            "RGB", (pixmap.width, pixmap.height), pixmap.samples
        )
        config = f"--oem 1 --psm {self.psm} -c preserve_interword_spaces=1"
        try:
            text = self._pytesseract.image_to_string(
                image,
                lang=self.language,
                config=config,
            )
        finally:
            image.close()
        return clean_text(text)


@dataclass
class PDFStats:
    pages: int = 0
    ocr_pages: int = 0
    text_pages: int = 0
    failed_pages: int = 0


def extract_pdf(
    pdf_path: Path,
    label: str,
    output: TextIO,
    ocr: OCRProcessor,
    *,
    force_ocr: bool = False,
    min_native_chars: int = 40,
) -> PDFStats:
    """Write one PDF's pages to output and return extraction counts."""
    fitz = import_pymupdf()
    try:
        document = fitz.open(str(pdf_path))
    except Exception as exc:
        raise PDFReadError(f"باز کردن فایل PDF ناموفق بود: {exc}") from exc

    try:
        if getattr(document, "needs_pass", False):
            raise PDFReadError("این PDF رمزگذاری شده است و بدون رمز قابل‌خواندن نیست.")

        stats = PDFStats(pages=len(document))
        output.write(f"===== فایل: {label} =====\n\n")
        for page_index in range(len(document)):
            page = document[page_index]
            native_text = ""
            if not force_ocr:
                try:
                    native_text = page.get_text("text", sort=True) or ""
                except Exception:
                    # A failed text-layer read is another reason to try OCR.
                    native_text = ""

            try:
                if needs_ocr(native_text, force_ocr, min_native_chars):
                    text = ocr.extract(page)
                    stats.ocr_pages += 1
                else:
                    text = native_text
                    stats.text_pages += 1
                text = clean_text(text)
            except OCRSetupError:
                raise
            except Exception as exc:
                stats.failed_pages += 1
                detail = str(exc).replace("\n", " ").strip()
                print(
                    f"هشدار: صفحهٔ {page_index + 1} از «{label}» پردازش نشد: {detail}",
                    file=sys.stderr,
                )
                text = "[خطا در پردازش این صفحه]"

            output.write(f"----- صفحهٔ {page_index + 1} -----\n")
            output.write(text if text else "[متنی پیدا نشد]")
            output.write("\n\n")
        return stats
    finally:
        document.close()


def positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("باید یک عدد صحیح باشد") from exc
    if number <= 0:
        raise argparse.ArgumentTypeError("عدد باید بزرگ‌تر از صفر باشد")
    return number


def valid_dpi(value: str) -> int:
    number = positive_int(value)
    if not 72 <= number <= 600:
        raise argparse.ArgumentTypeError("DPI باید بین 72 و 600 باشد")
    return number


class ArgumentDefaultsRawDescriptionFormatter(
    argparse.ArgumentDefaultsHelpFormatter, argparse.RawDescriptionHelpFormatter
):
    pass


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="متن PDF را استخراج می‌کند و صفحه‌های اسکن‌شده را با OCR فارسی/انگلیسی می‌خواند.",
        formatter_class=ArgumentDefaultsRawDescriptionFormatter,
        epilog=(
            "نمونه‌ها:\n"
            "  python pdf_ocr.py scan.pdf -o result.txt\n"
            "  python pdf_ocr.py ./pdfs -o all_text.txt\n"
            "  python pdf_ocr.py ./pdfs -r --force-ocr -o all_text.txt"
        ),
    )
    parser.add_argument(
        "input",
        help="مسیر یک فایل PDF یا پوشه‌ای که PDFها در آن قرار دارند.",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="مسیر فایل TXT خروجی؛ اگر مشخص نشود، کنار ورودی ساخته می‌شود.",
    )
    parser.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help="در حالت پوشه، زیرپوشه‌ها را هم جست‌وجو کن.",
    )
    parser.add_argument(
        "--lang",
        default="fas+eng",
        help="زبان‌های Tesseract؛ برای چند زبان از + استفاده کن.",
    )
    parser.add_argument(
        "--force-ocr",
        action="store_true",
        help="همهٔ صفحه‌ها را OCR کن، حتی اگر متن قابل‌استخراج داشته باشند.",
    )
    parser.add_argument(
        "--min-native-chars",
        type=positive_int,
        default=40,
        metavar="N",
        help="اگر متن PDF در یک صفحه کمتر از N نویسه داشته باشد، OCR اجرا می‌شود.",
    )
    parser.add_argument(
        "--dpi",
        type=valid_dpi,
        default=300,
        help="وضوح رندر صفحه برای OCR (بین 72 تا 600).",
    )
    parser.add_argument(
        "--psm",
        type=int,
        choices=(3, 4, 6, 11, 12, 13),
        default=3,
        help="حالت چیدمان صفحه در Tesseract.",
    )
    parser.add_argument(
        "--tesseract-cmd",
        help="مسیر فایل اجرایی Tesseract، در صورتی که در PATH نباشد.",
    )
    return parser


def run(args: argparse.Namespace) -> int:
    input_path = Path(args.input).expanduser()
    pdfs = find_pdfs(input_path, recursive=args.recursive)
    output_path = (
        Path(args.output).expanduser() if args.output else default_output_path(input_path)
    )
    if output_path.exists() and output_path.is_dir():
        raise ToolError(f"مسیر خروجی باید نام یک فایل باشد، نه پوشه: {output_path}")

    resolved_output = output_path.resolve()
    if any(resolved_output == pdf.resolve() for pdf in pdfs):
        raise ToolError("فایل خروجی نمی‌تواند روی یکی از PDFهای ورودی نوشته شود.")

    import_pymupdf()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{output_path.name}.",
        suffix=".tmp",
        dir=str(output_path.parent),
    )
    temporary_path = Path(temporary_name)
    total_stats = PDFStats()
    failed_files = 0

    try:
        with os.fdopen(fd, "w", encoding="utf-8", errors="replace", newline="\n") as output:
            ocr = OCRProcessor(
                language=args.lang,
                dpi=args.dpi,
                psm=args.psm,
                tesseract_cmd=args.tesseract_cmd,
            )
            for file_index, pdf_path in enumerate(pdfs, start=1):
                if input_path.is_dir():
                    try:
                        label = str(pdf_path.relative_to(input_path))
                    except ValueError:
                        label = pdf_path.name
                else:
                    label = pdf_path.name

                print(f"[{file_index}/{len(pdfs)}] {label}", file=sys.stderr)
                try:
                    stats = extract_pdf(
                        pdf_path,
                        label,
                        output,
                        ocr,
                        force_ocr=args.force_ocr,
                        min_native_chars=args.min_native_chars,
                    )
                except OCRSetupError:
                    raise
                except PDFReadError as exc:
                    failed_files += 1
                    print(f"خطا: {label}: {exc}", file=sys.stderr)
                    output.write(f"===== فایل: {label} =====\n[خواندن این PDF ناموفق بود]\n\n")
                    continue

                total_stats.pages += stats.pages
                total_stats.ocr_pages += stats.ocr_pages
                total_stats.text_pages += stats.text_pages
                total_stats.failed_pages += stats.failed_pages
                print(
                    f"  صفحه‌ها: {stats.pages} | OCR: {stats.ocr_pages} | "
                    f"متن آماده: {stats.text_pages} | خطا: {stats.failed_pages}",
                    file=sys.stderr,
                )

        os.replace(temporary_path, output_path)
    except BaseException:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise

    print(f"\nفایل خروجی: {output_path}")
    print(
        f"PDFها: {len(pdfs)} | صفحه‌ها: {total_stats.pages} | "
        f"OCR: {total_stats.ocr_pages} | متن آماده: {total_stats.text_pages} | "
        f"خطا: {failed_files + total_stats.failed_pages}"
    )
    return 1 if failed_files or total_stats.failed_pages else 0


def main(argv: list[str] | None = None) -> int:
    parser = make_parser()
    args = parser.parse_args(argv)
    try:
        return run(args)
    except ToolError as exc:
        print(f"خطا: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\nپردازش توسط کاربر متوقف شد.", file=sys.stderr)
        return 130
    except OSError as exc:
        print(f"خطای فایل یا پوشه: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
