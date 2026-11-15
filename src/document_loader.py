import os
import re
import json
import zipfile
import pandas as pd
from bs4 import BeautifulSoup

try:
    import pymupdf as fitz
except ImportError:
    try:
        import fitz
    except ImportError:
        fitz = None

try:
    import pypdf
except ImportError:
    pypdf = None


class DocumentLoader:
    """
    Ingests and normalizes technical knowledge base documents across
    Markdown (.md), HTML (.html), Text (.txt), PDF (.pdf), and CSV (.csv).
    Applies multi-encoding fallbacks, extracts metadata (dates, titles, sections),
    segregates internal documents, and sanitizes indirect prompt injections.
    """

    INJECTION_PATTERNS = [
        re.compile(r"\[SYSTEM NOTE TO AI ASSISTANTS?:.*?\]", re.IGNORECASE | re.DOTALL),
        re.compile(r"<!--\s*AI assistants?:.*?-->", re.IGNORECASE | re.DOTALL),
        re.compile(r"Note for AI assistants? processing this page:.*?(?=\n|$)", re.IGNORECASE),
        re.compile(r"System override:.*?disregard.*?(?=\n|$)", re.IGNORECASE),
    ]

    DATE_PATTERNS = [
        re.compile(r"Last updated:\s*(\d{4}-\d{2}-\d{2})", re.IGNORECASE),
        re.compile(r"updated\s*(\d{4}-\d{2}-\d{2})", re.IGNORECASE),
        re.compile(r"(\d{4}-\d{2}-\d{2})"),
    ]

    def __init__(self, kb_zip_path="kb.zip", extracted_dir="data/extracted"):
        self.kb_zip_path = kb_zip_path
        self.extracted_dir = extracted_dir
        self.documents = []

    def ensure_extracted(self):
        """Extracts kb.zip into extracted_dir if not already extracted."""
        kb_dir = os.path.join(self.extracted_dir, "kb")
        if os.path.exists(kb_dir) and len(os.listdir(kb_dir)) >= 100:
            return kb_dir

        if not os.path.exists(self.kb_zip_path):
            raise FileNotFoundError(f"Knowledge base zip archive not found at {self.kb_zip_path}")

        os.makedirs(self.extracted_dir, exist_ok=True)
        with zipfile.ZipFile(self.kb_zip_path, "r") as z:
            z.extractall(self.extracted_dir)

        if not os.path.exists(kb_dir):
            kb_dir = self.extracted_dir

        return kb_dir

    def _read_file_safe(self, file_path):
        """Reads a text file trying multiple common encodings."""
        encodings = ["utf-8", "utf-8-sig", "latin-1", "cp1252"]
        for enc in encodings:
            try:
                with open(file_path, "r", encoding=enc) as f:
                    return f.read()
            except (UnicodeDecodeError, UnicodeError):
                continue
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()

    def sanitize_indirect_injections(self, text):
        """Detects and scrubs prompt injection payloads embedded in documents."""
        sanitized_text = text
        detected = []
        for pattern in self.INJECTION_PATTERNS:
            matches = pattern.findall(sanitized_text)
            if matches:
                detected.extend(matches)
                sanitized_text = pattern.sub("", sanitized_text)
        return sanitized_text.strip(), detected

    def _parse_date(self, text, meta_date=None):
        if meta_date:
            return meta_date
        for pat in self.DATE_PATTERNS:
            m = pat.search(text)
            if m:
                return m.group(1)
        return None

    def _parse_markdown(self, filename, content):
        title = filename.replace(".md", "").replace("-", " ").title()
        section = "General"
        date = None

        lines = content.splitlines()
        for line in lines:
            if line.startswith("# ") and title == filename.replace(".md", "").replace("-", " ").title():
                title = line[2:].strip()
            if "_Section:" in line:
                sec_match = re.search(r"_Section:\s*([^_·]+)_", line)
                if sec_match:
                    section = sec_match.group(1).strip()
            if "_Last updated:" in line or "Last updated:" in line:
                d = self._parse_date(line)
                if d:
                    date = d

        if not date:
            date = self._parse_date(content)

        clean_text, detected_injections = self.sanitize_indirect_injections(content)

        return {
            "title": title,
            "section": section,
            "date": date,
            "content": clean_text,
            "injections": detected_injections,
        }

    def _parse_html(self, filename, content):
        soup = BeautifulSoup(content, "html.parser")
        
        # Meta date
        date = None
        meta_mod = soup.find("meta", attrs={"name": "last-modified"})
        if meta_mod and meta_mod.get("content"):
            date = meta_mod["content"].strip()

        # Title
        title = soup.title.string.strip() if soup.title and soup.title.string else filename.replace(".html", "").replace("-", " ").title()
        if "|" in title:
            title = title.split("|")[0].strip()

        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.decompose()

        body_text = soup.get_text(separator="\n").strip()
        if not date:
            date = self._parse_date(body_text)

        clean_text, detected_injections = self.sanitize_indirect_injections(body_text)

        return {
            "title": title,
            "section": "Announcements / Web",
            "date": date,
            "content": clean_text,
            "injections": detected_injections,
        }

    def _parse_txt(self, filename, content):
        lines = content.splitlines()
        title = lines[0].strip() if lines else filename.replace(".txt", "").replace("-", " ").title()
        if title.endswith("?"):
            pass
        date = self._parse_date(content)
        
        section = "Community Forums" if filename.startswith("forum-") else ("Internal" if filename.startswith("internal-") else "Notes")
        clean_text, detected_injections = self.sanitize_indirect_injections(content)

        return {
            "title": title,
            "section": section,
            "date": date,
            "content": clean_text,
            "injections": detected_injections,
        }

    def _parse_pdf(self, file_path, filename):
        text = ""
        if fitz:
            doc = fitz.open(file_path)
            for page in doc:
                text += page.get_text() + "\n"
        elif pypdf:
            reader = pypdf.PdfReader(file_path)
            for page in reader.pages:
                text += (page.extract_text() or "") + "\n"
        else:
            text = "PDF parser unavailable"

        title = filename.replace(".pdf", "").replace("-", " ").title()
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if lines:
            first_line = lines[0]
            if "(" in first_line:
                title = first_line.split("(")[0].strip()
            else:
                title = first_line

        date = self._parse_date(text)
        clean_text, detected_injections = self.sanitize_indirect_injections(text)

        return {
            "title": title,
            "section": "Guides & Whitepapers",
            "date": date,
            "content": clean_text,
            "injections": detected_injections,
        }

    def _parse_csv(self, file_path, filename):
        df = pd.read_csv(file_path)
        title = filename.replace(".csv", "").replace("-", " ").title()
        # Convert each row into descriptive natural sentences for high-quality retrieval
        rows_text = []
        for _, row in df.iterrows():
            plan_name = row.get("plan", "Unknown")
            monthly_price = row.get("monthly_price_eur", "N/A")
            seats = row.get("seats", "N/A")
            rate_limit = row.get("api_requests_per_minute", "N/A")
            payout_days = row.get("standard_payout_business_days", "N/A")
            card_fee = row.get("card_fee", "N/A")
            support_time = row.get("support_first_response", "N/A")
            
            row_str = (
                f"Plan: {plan_name}\n"
                f"- Monthly Price: €{monthly_price}\n"
                f"- Included Seats: {seats}\n"
                f"- API Rate Limit: {rate_limit} requests per minute\n"
                f"- Standard Payout Schedule: {payout_days} business days\n"
                f"- Card Processing Fee: {card_fee}\n"
                f"- Support First Response SLA: {support_time}\n"
            )
            rows_text.append(row_str)

        full_content = f"# Plan Limits and Pricing Matrix\n\n" + "\n".join(rows_text)

        return {
            "title": title,
            "section": "Pricing & Limits",
            "date": "2026-03-01",  # Matches the active plan restructuring
            "content": full_content,
            "injections": [],
            "dataframe": df.to_dict(orient="records"),
        }

    def load_all(self, target_dir=None):
        """Loads and processes all documents from the extracted KB directory."""
        if not target_dir:
            target_dir = self.ensure_extracted()

        self.documents = []
        for root, _, files in os.walk(target_dir):
            for file in sorted(files):
                file_path = os.path.join(root, file)
                ext = os.path.splitext(file)[1].lower()
                doc_id = file
                
                # Internal documents classification
                is_internal = file.startswith("internal-")

                parsed = None
                if ext == ".md":
                    raw = self._read_file_safe(file_path)
                    parsed = self._parse_markdown(file, raw)
                elif ext == ".html":
                    raw = self._read_file_safe(file_path)
                    parsed = self._parse_html(file, raw)
                elif ext == ".txt":
                    raw = self._read_file_safe(file_path)
                    parsed = self._parse_txt(file, raw)
                elif ext == ".pdf":
                    parsed = self._parse_pdf(file_path, file)
                elif ext == ".csv":
                    parsed = self._parse_csv(file_path, file)
                else:
                    continue

                if "INTERNAL ONLY" in parsed["content"]:
                    is_internal = True

                doc_entry = {
                    "doc_id": doc_id,
                    "filename": file,
                    "filepath": file_path,
                    "format": ext.replace(".", ""),
                    "title": parsed["title"],
                    "section": parsed["section"],
                    "date": parsed["date"],
                    "access": "internal" if is_internal else "public",
                    "content": parsed["content"],
                    "sanitized_injections": parsed.get("injections", []),
                }
                if "dataframe" in parsed:
                    doc_entry["dataframe"] = parsed["dataframe"]

                self.documents.append(doc_entry)

        return self.documents

    def save_processed(self, output_path="data/processed_documents.json"):
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(self.documents, f, indent=2, ensure_ascii=False)
        return output_path
