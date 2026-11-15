import re
import json
import hashlib
import os


class DocumentChunker:
    """
    Splits documents into coherent passages with rich metadata preservation.
    Specializes handling for:
      - changelog.md: partitioned by chronological updates (## YYYY-MM-DD).
      - plan-limits.csv: partitioned by subscription plan tier.
      - Markdown and HTML: partitioned by headers and semantic sections.
      - Deduplication via MD5 hash.
    """

    def __init__(self, processed_docs=None):
        self.processed_docs = processed_docs or []
        self.chunks = []

    def _generate_chunk_id(self, doc_id, heading, index):
        slug = re.sub(r"[^\w\s-]", "", heading.lower()).strip()
        slug = re.sub(r"[-\s]+", "-", slug)
        if not slug:
            slug = f"section-{index}"
        return f"{doc_id}#{slug}"

    def _chunk_changelog(self, doc):
        """Splits changelog.md into discrete date-stamped entries."""
        content = doc["content"]
        chunks = []
        
        # Regex to match ## YYYY-MM-DD
        entries = re.split(r"\n##\s+(\d{4}-\d{2}-\d{2})", content)
        # Entry 0 is the intro
        if entries and entries[0].strip():
            intro_text = entries[0].strip()
            chunks.append({
                "chunk_id": f"{doc['doc_id']}#intro",
                "doc_id": doc["doc_id"],
                "title": doc["title"],
                "section": doc["section"],
                "heading": "Introduction",
                "date": doc["date"],
                "format": doc["format"],
                "access": doc["access"],
                "text": intro_text,
            })

        idx = 1
        while idx < len(entries):
            date_str = entries[idx]
            entry_body = entries[idx + 1].strip() if idx + 1 < len(entries) else ""
            if entry_body:
                chunk_text = f"Product changelog update ({date_str}):\n{entry_body}"
                chunks.append({
                    "chunk_id": f"{doc['doc_id']}#{date_str}",
                    "doc_id": doc["doc_id"],
                    "title": doc["title"],
                    "section": "Changelog",
                    "heading": f"Update {date_str}",
                    "date": date_str,
                    "format": doc["format"],
                    "access": doc["access"],
                    "text": chunk_text,
                })
            idx += 2

        return chunks

    def _chunk_csv(self, doc):
        """Splits CSV into distinct plan-tier chunks."""
        chunks = []
        if "dataframe" in doc and doc["dataframe"]:
            for i, row in enumerate(doc["dataframe"]):
                plan_name = row.get("plan", f"Plan-{i}")
                rate_limit = row.get("api_requests_per_minute", "")
                payout_days = row.get("standard_payout_business_days", "")
                card_fee = row.get("card_fee", "")
                price = row.get("monthly_price_eur", "")
                seats = row.get("seats", "")
                support_sla = row.get("support_first_response", "")

                text = (
                    f"Paperkite {plan_name} Plan Specifications (as of {doc['date']}):\n"
                    f"- Monthly Subscription: €{price}\n"
                    f"- Team Seats Included: {seats}\n"
                    f"- API Rate Limit: {rate_limit} requests per minute\n"
                    f"- Standard Payout Schedule: {payout_days} business days\n"
                    f"- Card Processing Fee: {card_fee}\n"
                    f"- Support First Response Time: {support_sla}"
                )

                chunks.append({
                    "chunk_id": f"{doc['doc_id']}#{plan_name.lower()}",
                    "doc_id": doc["doc_id"],
                    "title": f"Plan Limits: {plan_name}",
                    "section": "Pricing & Limits",
                    "heading": f"Plan: {plan_name}",
                    "date": doc["date"],
                    "format": doc["format"],
                    "access": doc["access"],
                    "text": text,
                })
        else:
            chunks.append({
                "chunk_id": f"{doc['doc_id']}#table",
                "doc_id": doc["doc_id"],
                "title": doc["title"],
                "section": doc["section"],
                "heading": "Plan Limits Table",
                "date": doc["date"],
                "format": doc["format"],
                "access": doc["access"],
                "text": doc["content"],
            })
        return chunks

    def _chunk_by_headings(self, doc):
        """Splits markdown or text documents by headings (##, ###)."""
        content = doc["content"]
        chunks = []

        # Find heading lines (e.g. ## Heading or ### Heading)
        pattern = re.compile(r"^(#{1,4})\s+(.+)$", re.MULTILINE)
        matches = list(pattern.finditer(content))

        if not matches:
            # Short document or no headings: single chunk
            chunks.append({
                "chunk_id": f"{doc['doc_id']}#full",
                "doc_id": doc["doc_id"],
                "title": doc["title"],
                "section": doc["section"],
                "heading": doc["title"],
                "date": doc["date"],
                "format": doc["format"],
                "access": doc["access"],
                "text": content.strip(),
            })
            return chunks

        # Content before first heading
        first_start = matches[0].start()
        if first_start > 0:
            preamble = content[:first_start].strip()
            if preamble:
                chunks.append({
                    "chunk_id": f"{doc['doc_id']}#overview",
                    "doc_id": doc["doc_id"],
                    "title": doc["title"],
                    "section": doc["section"],
                    "heading": "Overview",
                    "date": doc["date"],
                    "format": doc["format"],
                    "access": doc["access"],
                    "text": f"{doc['title']}\n{preamble}",
                })

        for i, match in enumerate(matches):
            heading = match.group(2).strip()
            start_pos = match.start()
            end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(content)
            section_content = content[start_pos:end_pos].strip()

            if section_content:
                chunk_id = self._generate_chunk_id(doc["doc_id"], heading, i)
                chunks.append({
                    "chunk_id": chunk_id,
                    "doc_id": doc["doc_id"],
                    "title": doc["title"],
                    "section": doc["section"],
                    "heading": heading,
                    "date": doc["date"],
                    "format": doc["format"],
                    "access": doc["access"],
                    "text": section_content,
                })

        return chunks

    def chunk_all(self, processed_docs=None):
        if processed_docs:
            self.processed_docs = processed_docs

        self.chunks = []
        seen_hashes = set()

        for doc in self.processed_docs:
            doc_id = doc["doc_id"]
            if doc_id == "changelog.md":
                doc_chunks = self._chunk_changelog(doc)
            elif doc_id == "plan-limits.csv":
                doc_chunks = self._chunk_csv(doc)
            else:
                doc_chunks = self._chunk_by_headings(doc)

            for chunk in doc_chunks:
                # Deduplicate identical text
                text_hash = hashlib.md5(chunk["text"].encode("utf-8")).hexdigest()
                if text_hash not in seen_hashes:
                    seen_hashes.add(text_hash)
                    chunk["md5"] = text_hash
                    self.chunks.append(chunk)

        return self.chunks

    def save_chunks(self, output_path="data/chunks.json"):
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(self.chunks, f, indent=2, ensure_ascii=False)
        return output_path
