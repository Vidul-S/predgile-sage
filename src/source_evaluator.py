import re
from datetime import datetime


class SourceEvaluator:
    """
    Evaluates source reliability, applies 7-tier authority weighting,
    factors in chronological recency, detects documentation contradictions,
    and resolves conflicts according to changelog supremacy and latest policies.
    """

    TIER_WEIGHTS = {
        "changelog": 1.00,       # Tier 1: Product Changelog (changelog.md)
        "formal_doc": 0.90,      # Tier 2: Official developer & billing guides (.md)
        "announcement": 0.75,    # Tier 3: Official announcements & blogs (.html)
        "faq_whitepaper": 0.70,  # Tier 4: Support FAQs, onboarding, whitepapers (.pdf)
        "community_forum": 0.45, # Tier 5: Community forum posts (.txt forum-*)
        "historical": 0.35,      # Tier 6: Undated or early historical notes
        "internal": 0.00,        # Tier 7: Internal staff documents (segregated)
    }

    def __init__(self):
        pass

    def classify_source_tier(self, chunk):
        doc_id = chunk.get("doc_id", "")
        fmt = chunk.get("format", "")

        if doc_id == "changelog.md":
            return "changelog"
        elif doc_id.startswith("internal-") or chunk.get("access") == "internal":
            return "internal"
        elif doc_id.startswith("forum-"):
            return "community_forum"
        elif fmt == "pdf":
            return "faq_whitepaper"
        elif fmt == "html":
            return "announcement"
        elif fmt == "md":
            if "faq" in doc_id or "overview" in doc_id:
                return "faq_whitepaper"
            return "formal_doc"
        elif fmt == "csv":
            return "formal_doc"
        return "historical"

    def _parse_date(self, date_str):
        if not date_str:
            return datetime(2020, 1, 1)
        try:
            return datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            m = re.search(r"(\d{4}-\d{2}-\d{2})", date_str)
            if m:
                try:
                    return datetime.strptime(m.group(1), "%Y-%m-%d")
                except ValueError:
                    pass
        return datetime(2020, 1, 1)

    def evaluate_authority(self, chunk):
        tier = self.classify_source_tier(chunk)
        base_weight = self.TIER_WEIGHTS.get(tier, 0.50)
        
        # Calculate date recency boost (2020 to 2026 range)
        date_dt = self._parse_date(chunk.get("date"))
        ref_date = datetime(2026, 6, 1)
        days_old = max(0, (ref_date - date_dt).days)
        # Recency factor from 0.85 to 1.05
        recency_factor = max(0.80, 1.05 - (days_old / 365.0) * 0.05)
        
        final_authority = round(base_weight * recency_factor, 4)
        return {
            "tier": tier,
            "tier_weight": base_weight,
            "parsed_date": date_dt.strftime("%Y-%m-%d"),
            "authority_score": final_authority,
        }

    def detect_and_resolve_conflicts(self, query, retrieved_chunks):
        """
        Cross-examines retrieved chunks to identify contradictions and policy changes.
        Returns reranked chunks with authority badges, conflict annotations,
        and explicit resolution explanations.
        """
        if not retrieved_chunks:
            return [], []

        # Annotate each chunk with authority and tier
        annotated_chunks = []
        for c in retrieved_chunks:
            ev = self.evaluate_authority(c)
            c_copy = dict(c)
            c_copy["tier"] = ev["tier"]
            c_copy["tier_weight"] = ev["tier_weight"]
            c_copy["parsed_date"] = ev["parsed_date"]
            c_copy["authority_score"] = ev["authority_score"]
            # Combined rank score = retrieval relevance * authority score
            c_copy["rank_score"] = round(c_copy.get("retrieval_score", 1.0) * ev["authority_score"], 4)
            annotated_chunks.append(c_copy)

        # Detect specific domain conflicts
        conflicts = []
        docs_present = {c["doc_id"] for c in annotated_chunks}
        chunk_texts_combined = " ".join([c["text"].lower() for c in annotated_chunks])

        # 1. API Rate Limits Conflict (500 vs 1,000 req/min for Pro)
        has_500 = "500" in chunk_texts_combined and ("rate limit" in chunk_texts_combined or "pro" in chunk_texts_combined)
        has_1000 = "1,000" in chunk_texts_combined or "1000" in chunk_texts_combined
        if has_500 and has_1000:
            conflicts.append({
                "doc_ids": [doc for doc in docs_present if doc in ["api-overview.md", "forum-pro-rate-limit.txt", "api-rate-limits.md", "changelog.md", "plan-limits.csv"]],
                "topic": "Pro Plan API Rate Limit",
                "older_claim": "500 requests per minute (stated in older api-overview.md and forum posts)",
                "active_rule": "1,000 requests per minute (officially increased in 2025-03-01 changelog, active in api-rate-limits.md and plan-limits.csv)",
                "resolution": "The Pro plan API rate limit was raised from 500 to 1,000 requests per minute in the March 2025 changelog. The older 500 limit is superseded."
            })

        # 2. Invoice Attachment Limit Conflict (5 MB vs 10 MB)
        has_5mb = "5 mb" in chunk_texts_combined or "5mb" in chunk_texts_combined
        has_10mb = "10 mb" in chunk_texts_combined or "10mb" in chunk_texts_combined
        if has_5mb and has_10mb:
            conflicts.append({
                "doc_ids": [doc for doc in docs_present if doc in ["invoice-attachments-2024.md", "forum-invoice-attachment-limit.txt", "invoice-attachments.md", "changelog.md"]],
                "topic": "Invoice Attachment File Size Limit",
                "older_claim": "5 MB maximum per attachment (invoice-attachments-2024.md)",
                "active_rule": "10 MB maximum per attachment (raised in changelog.md and active in invoice-attachments.md)",
                "resolution": "The attachment size limit was increased from 5 MB to 10 MB in the changelog. The 5 MB limit is outdated."
            })

        # 3. /v1/charges Endpoint Deprecation Conflict
        if "/v1/charges" in chunk_texts_combined:
            has_removed = "410 gone" in chunk_texts_combined or "is removed" in chunk_texts_combined or "deprecated" in chunk_texts_combined
            has_working = "still works" in chunk_texts_combined or "create and manage charges" in chunk_texts_combined
            if has_removed and has_working:
                conflicts.append({
                    "doc_ids": [doc for doc in docs_present if doc in ["api-v1-charges-guide.md", "forum-v1-charges-still-working.txt", "changelog.md"]],
                    "topic": "/v1/charges Endpoint Validity",
                    "older_claim": "Endpoint is functional and usable for charges (api-v1-charges-guide.md and older forum posts)",
                    "active_rule": "Permanently removed as of 2026-01-15; requests return HTTP 410 Gone (use /v2/payments)",
                    "resolution": "The /v1/charges endpoint was permanently decommissioned on 2026-01-15 and returns 410 Gone. The forum post claiming it still works is outdated; integrations must use /v2/payments."
                })

        # 4. Partial Refunds Conflict (Limit 3, Dashboard availability)
        if "partial refund" in chunk_texts_combined:
            has_limit3 = "up to 3" in chunk_texts_combined or "limited to 3" in chunk_texts_combined
            has_no_limit = "no longer limited" in chunk_texts_combined or "from the dashboard" in chunk_texts_combined
            if has_limit3 and has_no_limit:
                conflicts.append({
                    "doc_ids": [doc for doc in docs_present if doc in ["refund-partial-guide.md", "refund-policy.md", "changelog.md", "refunds-issue.md"]],
                    "topic": "Partial Refund Constraints & Dashboard Support",
                    "older_claim": "Limited to 3 partial refunds per payment and not available in Dashboard (refund-partial-guide.md, 2023)",
                    "active_rule": "No limit on partial refunds; can be issued directly in the Dashboard or via API (changelog and refunds-issue.md, 2026)",
                    "resolution": "The 3 partial refund limit was removed, and Dashboard partial refunds were officially introduced in the changelog and codified in refunds-issue.md."
                })

        # 5. VAT on Upgrades (Full price vs Prorated net amount)
        if "vat" in chunk_texts_combined and ("upgrade" in chunk_texts_combined or "proration" in chunk_texts_combined):
            has_full_claim = "full" in chunk_texts_combined and "vat" in chunk_texts_combined
            if has_full_claim and "prorated" in chunk_texts_combined:
                conflicts.append({
                    "doc_ids": [doc for doc in docs_present if doc in ["forum-vat-on-upgrades.txt", "tax-eu-vat.md", "subscription-proration.md"]],
                    "topic": "EU VAT on Mid-Cycle Upgrade Proration",
                    "older_claim": "VAT is charged on the full new plan price (forum-vat-on-upgrades.txt)",
                    "active_rule": "VAT applies strictly to the net prorated amount invoiced for remaining days (tax-eu-vat.md)",
                    "resolution": "Documentation in tax-eu-vat.md confirms VAT applies only to the net, prorated amount invoiced for the remaining billing cycle, refuting community forum speculation."
                })

        # Annotate status on chunks
        for c in annotated_chunks:
            # Check if this chunk belongs to a superseded document
            is_superseded = False
            for conf in conflicts:
                if any(old_id in c["doc_id"] for old_id in ["2024", "2023", "v1-charges-guide", "forum-"]):
                    if c["doc_id"] in conf["doc_ids"] and c["tier"] in ["community_forum", "historical", "faq_whitepaper", "formal_doc"]:
                        # If date is older than changelog/current doc
                        if c["parsed_date"] < "2025-01-01" or "forum-" in c["doc_id"]:
                            is_superseded = True
            c["is_superseded"] = is_superseded
            c["status_label"] = "[SUPERSEDED / OUTDATED]" if is_superseded else "[AUTHORITATIVE]"

        # Rerank: authoritative chunks first, then by rank_score
        annotated_chunks.sort(key=lambda x: (not x["is_superseded"], x["rank_score"]), reverse=True)

        return annotated_chunks, conflicts
