from __future__ import annotations

import contextlib
import io
import logging
import os
from typing import Optional

try:
    import PyPDF2
except ImportError:
    PyPDF2 = None

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

try:
    import fitz  # PyMuPDF
except Exception:
    fitz = None


def _env_truthy(name: str) -> bool:
    v = (os.getenv(name) or "").strip().lower()
    return v in {"1", "true", "yes", "y", "on"}


@contextlib.contextmanager
def _suppress_pdf_noise(enabled: bool):
    """
    pdfminer/pdfplumber 在某些 PDF（字体/颜色描述异常）上会输出大量 warning 到 stdout/stderr。
    这些通常不影响提取结果，但会刷屏并显著拖慢体验（I/O 很慢）。
    """
    if not enabled:
        yield
        return

    # 1) 压低 pdfminer 的日志
    try:
        logging.getLogger("pdfminer").setLevel(logging.ERROR)
        logging.getLogger("pdfplumber").setLevel(logging.ERROR)
    except Exception:
        pass

    # 2) 捕获底层库直接写 stdout/stderr 的噪音
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        yield

class PDFParser:
    def __init__(self):
        pass

    def parse_pdf(self, file_path: str, max_pages: Optional[int] = None) -> str:
        """
        Extracts text from a PDF file.
        """
        if not PyPDF2 and not pdfplumber:
            print("PyPDF2/pdfplumber not installed. Please install one of them to parse PDFs.")
            return ""
            
        if not os.path.exists(file_path):
            print(f"File not found: {file_path}")
            return ""

        text = ""
        try:
            # 0) 优先 PyMuPDF（更快且更少噪音）；若未安装则跳过
            if fitz is not None:
                try:
                    doc = fitz.open(file_path)
                    pages = range(min(len(doc), max_pages)) if max_pages else range(len(doc))
                    out = []
                    for i in pages:
                        out.append((doc.load_page(i).get_text("text") or "").strip())
                    doc.close()
                    joined = "\n".join([x for x in out if x]).strip()
                    if joined:
                        return joined
                except Exception:
                    # 继续 fallback
                    pass

            # 优先用 pdfplumber（通常比 PyPDF2 提取效果更好）
            if pdfplumber:
                try:
                    # 默认静默 pdfminer 噪音；需要排查时可设置 MUJICA_PDF_DEBUG=1
                    with _suppress_pdf_noise(enabled=not _env_truthy("MUJICA_PDF_DEBUG")):
                        with pdfplumber.open(file_path) as pdf:
                            pages = pdf.pages[:max_pages] if max_pages else pdf.pages
                            for page in pages:
                                extracted = page.extract_text() or ""
                                if extracted.strip():
                                    text += extracted.strip() + "\n"

                    text = text.strip()
                    # If pdfplumber yields empty text, fall back to PyPDF2
                    if text:
                        return text
                    print(f"Warning: pdfplumber extracted empty text for {file_path}. Falling back to PyPDF2.")
                except Exception as e:
                    # If pdfplumber errors, fall back to PyPDF2
                    print(f"Warning: pdfplumber failed for {file_path}: {e}. Falling back to PyPDF2.")

                # reset before PyPDF2
                text = ""

            with open(file_path, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                pages = reader.pages[:max_pages] if max_pages else reader.pages
                for page in pages:
                    extracted = page.extract_text() or ""
                    if extracted.strip():
                        text += extracted.strip() + "\n"
            return text.strip()
        except Exception as e:
            print(f"Error parsing PDF {file_path}: {e}")
            return ""
