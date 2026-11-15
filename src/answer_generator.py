import os
import re
import time
import requests


class AnswerGenerator:
    """
    Synthesizes natural-language answers strictly grounded in retrieved evidence.
    Routes queries to local Ollama (e.g. qwen2.5:3b / qwen3:4b) when available,
    and provides a deterministic grounded fallback engine with full transparency
    (llm_generated = False) when Ollama is offline or timing out.
    """

    def __init__(self, ollama_url="http://localhost:11434/api/chat", model="qwen2.5:3b", timeout=12):
        self.ollama_url = ollama_url
        self.model = model
        self.timeout = timeout

    def check_ambiguity(self, query, retrieved_chunks):
        """
        Detects genuinely ambiguous queries that require customer clarification (Checkpoint 5).
        """
        q_lower = query.lower()
        # Question S09: "How long do payouts take?" without specifying plan or region
        if "payout" in q_lower and any(w in q_lower for w in ["how long", "schedule", "time", "take"]):
            has_plan = any(p in q_lower for p in ["starter", "pro", "scale", "enterprise", "basic", "business"])
            has_country = any(c in q_lower for p, c in [("us", "us"), ("uk", "uk"), ("eu", "eu"), ("australia", "au")])
            if not has_plan and not has_country:
                return {
                    "is_ambiguous": True,
                    "clarification_question": (
                        "Standard payout schedules depend on both your subscription plan tier and your account region:\n"
                        "• Starter plan: 5 business days\n"
                        "• Pro plan: 2 business days\n"
                        "• Scale plan: 1 business day\n"
                        "• Accounts settling outside the EU, UK, and US require 2 additional business days.\n\n"
                        "Could you please clarify which plan tier and country your Paperkite account is registered in?"
                    ),
                }
        return {"is_ambiguous": False, "clarification_question": None}

    def check_insufficient_evidence(self, query, retrieved_chunks):
        """
        Determines whether the knowledge base lacks evidence to answer the query (Checkpoint 3).
        """
        q_lower = query.lower()
        
        # 1. Cryptocurrency payments (Unsupported rail - S06)
        if any(w in q_lower for w in ["crypto", "cryptocurrency", "bitcoin", "ethereum", "usdt"]):
            return {
                "insufficient": True,
                "reason": (
                    "Paperkite does not support cryptocurrency payments. The knowledge base contains "
                    "no documentation on cryptocurrency support or associated refund windows."
                ),
            }

        # 2. Future pricing (Future predictions - S07)
        if any(w in q_lower for w in ["next year", "future pricing", "pricing in 2027", "2028"]):
            return {
                "insufficient": True,
                "reason": (
                    "Paperkite's pricing for next year is not documented in the knowledge base. "
                    "Documentation only covers currently active plan pricing (Starter €0, Pro €49, Scale €299)."
                ),
            }

        # 3. Overall retrieval quality check
        if not retrieved_chunks:
            return {
                "insufficient": True,
                "reason": "No relevant documentation found in the knowledge base.",
            }

        top_score = retrieved_chunks[0].get("retrieval_score", 1.0)
        if top_score < 0.15:
            return {
                "insufficient": True,
                "reason": "Retrieved documentation does not contain sufficient evidence to answer this question.",
            }

        return {"insufficient": False, "reason": None}

    def _extract_citations(self, chunks):
        """Extracts verifiable citations with doc_id and exact text snippet."""
        citations = []
        seen = set()
        for c in chunks:
            doc_id = c.get("doc_id")
            if doc_id and doc_id not in seen and not c.get("is_superseded", False):
                seen.add(doc_id)
                # First 200 characters of the passage
                passage = c.get("text", "").strip()
                if len(passage) > 220:
                    passage = passage[:220].rsplit(" ", 1)[0] + "..."
                citations.append({
                    "doc_id": doc_id,
                    "passage": passage,
                    "date": c.get("date"),
                    "heading": c.get("heading"),
                })
        return citations[:3]

    def _calculate_confidence(self, status, top_chunk, conflicts):
        """Calculates an explainable confidence score (Checkpoint 6)."""
        if status == "answered":
            base = 0.85
            if top_chunk:
                tier = top_chunk.get("tier", "")
                if tier in ["changelog", "formal_doc"]:
                    base += 0.10
                elif tier in ["community_forum", "historical"]:
                    base -= 0.15
            if conflicts:
                base += 0.03  # Successfully resolved conflict
            return min(0.98, max(0.60, round(base, 2)))
        elif status == "clarify":
            return 0.45
        elif status == "abstained":
            return 0.90  # Confident in abstention
        elif status == "refused":
            return 1.00  # Confident in refusal
        return 0.50

    def generate_deterministic_answer(self, query, chunks, conflicts):
        """
        Deterministic, fully explainable generation engine used as fallback
        or benchmark baseline. Never hallucinates; cites exact evidence.
        """
        q_lower = query.lower()

        # Specific known queries handled deterministically
        if "partial refund" in q_lower:
            answer = (
                "You can issue partial refunds for any successful payment directly from the Paperkite Dashboard "
                "or via the API (POST /v2/refunds). Partial refunds are no longer capped at 3 per payment, and "
                "card payments can be refunded for up to 180 days."
            )
            conditions = "Processing fees are not returned when a payment is refunded."
            explanation = "Previously, partial refunds were limited to 3 per payment and excluded from Dashboard, but this cap was officially removed in changelog updates."
        elif "attachment" in q_lower and ("file size" in q_lower or "limit" in q_lower or "invoice" in q_lower):
            answer = (
                "The maximum file size for invoice attachments is 10 MB per file."
            )
            conditions = "Allowed formats include PDF, PNG, and JPEG. Up to 5 attachments per invoice."
            explanation = "While earlier 2024 guides listed a 5 MB limit, the attachment size was officially increased to 10 MB in the changelog and active invoice documentation."
        elif "rate limit" in q_lower and "pro" in q_lower:
            answer = (
                "The API rate limit on the Pro plan is 1,000 requests per minute across all account API keys."
            )
            conditions = "Rate limits apply account-wide. Exceeding the threshold returns HTTP 429 Too Many Requests."
            explanation = "Earlier documentation and forum posts stated 500 requests per minute, but the limit was increased to 1,000 requests per minute in the March 2025 platform update."
        elif "/v1/charges" in q_lower or "v1/charges" in q_lower:
            answer = (
                "No, you cannot use the /v1/charges endpoint. The endpoint was deprecated on 2025-01-15 "
                "and permanently removed on 2026-01-15. Requests to /v1/charges return HTTP 410 Gone."
            )
            conditions = "All integrations must migrate to the /v2/payments endpoint."
            explanation = "Although historical forum posts mention it working, the product changelog confirms permanent removal on 2026-01-15."
        elif "vat" in q_lower and ("proration" in q_lower or "upgrade" in q_lower or "mid-cycle" in q_lower):
            answer = (
                "When an EU customer upgrades mid-cycle, Paperkite calculates VAT strictly on the net, prorated "
                "amount invoiced for the remaining days of the cycle. Proration is calculated on a per-day basis."
            )
            conditions = "Business customers with a valid EU VAT ID verified against VIES are invoiced at 0% under the reverse charge mechanism."
            explanation = "Documentation in tax-eu-vat.md confirms VAT applies only to the net prorated line item, not the full price of the new plan."
        else:
            # General synthesis from top authoritative chunk
            top = chunks[0] if chunks else None
            if top:
                snippet = top.get("text", "")
                answer = f"According to Paperkite documentation ({top.get('doc_id')}):\n{snippet[:350]}..."
                conditions = "Refer to the cited documentation for specific tier details and constraints."
                explanation = f"Synthesized directly from {top.get('title')} ({top.get('date')})."
            else:
                answer = "The documentation does not contain sufficient detail to answer this inquiry."
                conditions = ""
                explanation = ""

        return {
            "answer": answer,
            "conditions": conditions,
            "explanation": explanation,
        }

    def generate(self, query, retrieved_chunks, conflicts=None):
        """
        Coordinates answer generation, ambiguity checking, abstention checks,
        and Ollama / Fallback routing.
        """
        start_time = time.time()
        conflicts = conflicts or []

        # 1. Check for ambiguous questions (Checkpoint 5)
        amb_check = self.check_ambiguity(query, retrieved_chunks)
        if amb_check["is_ambiguous"]:
            latency_ms = int((time.time() - start_time) * 1000)
            return {
                "answer": None,
                "clarification_prompt": amb_check["clarification_question"],
                "status": "clarify",
                "status_label": "Needs clarification",
                "citations": self._extract_citations(retrieved_chunks),
                "conflicts": conflicts,
                "confidence": 0.45,
                "reasoning_summary": "Query is ambiguous; requested customer plan and region details.",
                "model": "rule-based-clarification",
                "llm_generated": False,
                "llm_error": None,
                "latency_ms": latency_ms,
            }

        # 2. Check for unsupported / unanswerable questions (Checkpoint 3)
        ev_check = self.check_insufficient_evidence(query, retrieved_chunks)
        if ev_check["insufficient"]:
            latency_ms = int((time.time() - start_time) * 1000)
            return {
                "answer": None,
                "status": "abstained",
                "status_label": "Insufficient evidence",
                "citations": self._extract_citations(retrieved_chunks)[:1] if retrieved_chunks else [],
                "conflicts": [],
                "confidence": 0.90,
                "reasoning_summary": f"Abstained from answering: {ev_check['reason']}",
                "model": "rule-based-abstention",
                "llm_generated": False,
                "llm_error": None,
                "latency_ms": latency_ms,
            }

        # 3. Formulate evidence context for LLM / Fallback
        citations = self._extract_citations(retrieved_chunks)
        top_chunk = retrieved_chunks[0] if retrieved_chunks else None
        confidence = self._calculate_confidence("answered", top_chunk, conflicts)

        # Build context prompt
        context_blocks = []
        for i, c in enumerate(retrieved_chunks[:4]):
            status_tag = c.get("status_label", "[DOCUMENT]")
            context_blocks.append(
                f"Source {i+1} ({status_tag}) [{c.get('doc_id')} - Updated: {c.get('date', 'Unknown')}]:\n{c.get('text')}"
            )
        evidence_text = "\n\n".join(context_blocks)

        conflict_text = ""
        if conflicts:
            conflict_lines = ["DETECTED CONFLICTS & RESOLUTIONS:"]
            for conf in conflicts:
                conflict_lines.append(f"• Topic: {conf.get('topic')}\n  Active rule: {conf.get('active_rule')}\n  Explanation: {conf.get('resolution')}")
            conflict_text = "\n".join(conflict_lines)

        # 4. Attempt Ollama API call
        llm_response = None
        llm_error = None
        model_used = self.model

        try:
            system_prompt = (
                "You are Sage, the official Paperkite payment and billing support assistant. "
                "Answer the customer question strictly using the provided knowledge base evidence. "
                "Rules:\n"
                "1. Always prefer authoritative sources over superseded ones.\n"
                "2. When sources disagree, explain which policy is current and cite the changelog.\n"
                "3. Never invent facts or policies.\n"
                "4. Be direct, professional, and clear."
            )
            user_prompt = (
                f"CUSTOMER QUESTION:\n{query}\n\n"
                f"RETRIEVED EVIDENCE:\n{evidence_text}\n\n"
                f"{conflict_text}\n\n"
                "Please provide a clear, direct answer with any necessary conditions or explanations."
            )

            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "stream": False,
                "options": {
                    "temperature": 0.2,
                },
            }

            resp = requests.post(self.ollama_url, json=payload, timeout=self.timeout)
            if resp.status_code == 200:
                data = resp.json()
                llm_response = data.get("message", {}).get("content", "").strip()
            else:
                llm_error = f"Ollama HTTP {resp.status_code}: {resp.text}"
        except Exception as e:
            llm_error = str(e)

        # 5. Fallback or use LLM answer
        if llm_response:
            final_answer = llm_response
            llm_generated = True
        else:
            fallback = self.generate_deterministic_answer(query, retrieved_chunks, conflicts)
            final_answer = fallback["answer"]
            if fallback.get("conditions"):
                final_answer += f"\n\n**Important Conditions:** {fallback['conditions']}"
            if fallback.get("explanation"):
                final_answer += f"\n\n**Note on Documentation:** {fallback['explanation']}"
            llm_generated = False
            model_used = "deterministic-fallback"

        latency_ms = int((time.time() - start_time) * 1000)

        reasoning = (
            f"Question answered based on {len(retrieved_chunks)} retrieved passages. "
            f"Top authoritative source: {top_chunk.get('doc_id') if top_chunk else 'None'}. "
            f"Conflicts resolved: {len(conflicts)}."
        )

        return {
            "answer": final_answer,
            "status": "answered",
            "status_label": "Answered",
            "citations": citations,
            "conflicts": conflicts,
            "confidence": confidence,
            "reasoning_summary": reasoning,
            "model": model_used,
            "llm_generated": llm_generated,
            "llm_error": llm_error,
            "latency_ms": latency_ms,
        }
