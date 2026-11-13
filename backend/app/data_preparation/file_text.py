"""Optional extraction from supplied local files only; no remote file downloads."""
import zipfile
from pathlib import Path
from xml.etree import ElementTree

def extract_local_file(path: Path) -> tuple[str, str]:
    if path.stat().st_size > 25 * 1024 * 1024:
        return "", "file_too_large"
    data = path.read_bytes()
    suffix = path.suffix.lower()
    if suffix == ".txt":
        try:
            return data.decode("utf-8-sig"), "text"
        except UnicodeDecodeError:
            return "", "unreadable"
    if suffix == ".docx" and data.startswith(b"PK"):
        with zipfile.ZipFile(path) as archive:
            if sum(x.file_size for x in archive.infolist()) > 100 * 1024 * 1024:
                return "", "file_too_large"
            try:
                root = ElementTree.fromstring(archive.read("word/document.xml"))
            except (KeyError, ElementTree.ParseError):
                return "", "unreadable"
            ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            return "\n\n".join("".join(p.itertext()) for p in root.findall(".//w:p", ns)), "text"
    if suffix == ".pdf" and data.startswith(b"%PDF"):
        try:
            from pypdf import PdfReader
            text = "\n\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
            return text, "text" if text.strip() else "image_only_or_unreadable"
        except ImportError:
            raise RuntimeError("Install the catalog requirements to extract PDF")
        except Exception:
            return "", "unreadable"
    return "", "unsupported_or_invalid_format"
