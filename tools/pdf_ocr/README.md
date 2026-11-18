# konkur

## ابزار OCR و استخراج متن PDF

`pdf_ocr.py` متن را از یک PDF یا از همهٔ PDFهای یک پوشه استخراج می‌کند و همه را به‌ترتیب در یک فایل متنی UTF-8 می‌نویسد. اگر صفحه‌ای متن قابل‌استخراج نداشته باشد (مثل PDF اسکن‌شده)، ابزار با Tesseract OCR روی آن اجرا می‌شود. زبان پیش‌فرض OCR فارسی و انگلیسی (`fas+eng`) است.

### پیش‌نیازها

۱. پایتون ۳٫۹ یا جدیدتر و کتابخانه‌های پایتون:

```bash
python -m pip install -r requirements.txt
```

۲. نصب برنامهٔ **Tesseract OCR** به‌همراه دادهٔ زبان‌های فارسی (`fas`) و انگلیسی (`eng`). نصب Tesseract به سیستم‌عامل بستگی دارد؛ در Ubuntu/Debian:

#### APT package managers

```bash
sudo apt update
sudo apt install tesseract-ocr tesseract-ocr-fas tesseract-ocr-eng
```

#### PACMAN package managers

``` bash
sudo pacman -Syu tesseract tesseract-data-fas tesseract-data-eng
tesseract --list-langs
```

در Windows، Tesseract را نصب کنید و مطمئن شوید داده‌های زبان `fas` و `eng` هم نصب شده‌اند. اگر برنامه در `PATH` نیست، مسیر `tesseract.exe` را با `--tesseract-cmd` بدهید.

### استفاده

استخراج یک فایل:

```bash
python pdf_ocr.py "data/qustions_data/KonkorFanni1405.pdf" -o fanni.txt
```

پردازش همهٔ PDFهای یک پوشه (فقط همان پوشه، بدون زیرپوشه‌ها):

```bash
python pdf_ocr.py "data/qustions_data" -o all_questions.txt
```

شامل زیرپوشه‌ها هم بشود:

```bash
python pdf_ocr.py "./pdfs" --recursive -o all_text.txt
```

اگر `-o` را ندهید، فایل خروجی کنار ورودی با پسوند `_ocr.txt` ساخته می‌شود. خروجی شامل نام هر PDF و جداکنندهٔ صفحه‌هاست تا متن‌ها از هم قابل‌تشخیص باشند. اگر متن قابل‌استخراج PDF در صفحه‌ای کمتر از ۴۰ نویسه باشد، آن صفحه به‌طور خودکار OCR می‌شود. برای OCR کردن اجباری همهٔ صفحه‌ها:

```bash
python pdf_ocr.py scan.pdf --force-ocr -o result.txt
```

گزینه‌های مفید را با `python pdf_ocr.py --help` ببینید. برای مثال، زبان OCR، وضوح (DPI) و مسیر Tesseract قابل‌تنظیم هستند. خطاهای صفحات/فایل‌ها در ترمینال گزارش می‌شوند و پردازش بقیهٔ فایل‌های پوشه ادامه پیدا می‌کند.
