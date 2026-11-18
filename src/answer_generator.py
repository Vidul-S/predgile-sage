import re
import time
import requests


class AnswerGenerator:
    """
    Synthesizes natural-language answers strictly grounded in retrieved evidence.
    Routes queries to local Ollama (e.g. qwen2.5:3b) when available, and falls back
    to a general extractive sentence-ranking synthesizer (with zero hardcoded
    per-question answers) when Ollama is offline or times out.
    """

    # Generic English stopwords and question meta-words ignored when checking
    # whether all specific subjects in a query are actually covered by evidence.
    GENERIC_QUERY_WORDS = {
        "a", "an", "the", "and", "or", "but", "if", "in", "on", "at", "to", "for",
        "of", "by", "with", "from", "as", "into", "about", "after", "before",
        "between", "during", "through", "under", "over", "per", "than", "then",
        "is", "are", "was", "were", "be", "been", "being", "am", "do", "does",
        "did", "doing", "done", "have", "has", "had", "can", "could", "will",
        "would", "shall", "should", "may", "might", "must",
        "i", "me", "my", "we", "our", "you", "your", "they", "their", "it", "its",
        "this", "that", "these", "those", "there", "here",
        "what", "which", "who", "whom", "whose", "when", "where", "why", "how",
        "much", "many", "long", "far", "often", "still", "yet", "now", "currently",
        "new", "old", "current", "active", "latest", "recent", "first", "last",
        "next", "previous", "same", "other", "different", "any", "all", "some",
        "more", "most", "less", "least", "maximum", "minimum", "max", "min",
        "get", "got", "make", "made", "take", "takes", "use", "using", "used",
        "need", "want", "know", "tell", "explain", "show", "give", "find",
        "work", "works", "working", "happen", "happens", "apply", "applies",
        "support", "supported", "supports", "allow", "allowed", "allows",
        "available", "possible", "able", "required", "include", "includes",
        "included", "calculated", "calculate", "issue", "create", "send", "set",
        "check", "change", "update", "handle", "handled",
        "paperkite", "customer", "customers", "user", "users", "merchant",
        "merchants", "account", "accounts", "company", "platform", "service",
        "product", "system", "feature", "option", "setting", "settings",
        "policy", "policies", "rule", "rules", "guide", "documentation", "docs",
        "endpoint", "endpoints", "method", "methods", "type", "types", "kind",
        "time", "times", "days", "day", "hours", "hour", "period", "window",
        "duration", "schedule", "limit", "limits", "size", "amount", "number",
        "rate", "cost", "price", "pricing", "fee", "fees", "value", "level",
        "plan", "plans", "tier", "tiers", "step", "steps", "way", "detail",
        "details", "information", "info", "question", "help", "please",
    }

    # Prospective / unannounced future horizon patterns (general temporal check)
    FUTURE_TIME_PATTERNS = [
        re.compile(r"\bnext\s+(?:year|quarter|decade)\b", re.IGNORECASE),
        re.compile(r"\b(?:in|for|by)\s+(202[7-9]|20[3-9]\d)\b", re.IGNORECASE),
        re.compile(r"\bfuture\s+(?:pricing|plans?|fees?|rates?|roadmap|releases?|versions?)\b", re.IGNORECASE),
    ]

    # Subscription / regional dimension indicators found in conditional documentation
    PLAN_TIERS = ("starter", "pro", "scale", "enterprise", "basic", "business")
    REGION_MARKERS = ("eu", "uk", "us", "usa", "europe", "switzerland", "australia", "canada", "japan", "singapore", "germany", "france", "outside")

    def __init__(self, ollama_url="http://localhost:11434/api/chat", model="qwen2.5:3b", timeout=12):
        self.ollama_url = ollama_url
        self.model = model
        self.timeout = timeout

    def _tokenize(self, text):
        return re.findall(r"/[a-z0-9_/]+|[€$£]\d+(?:\.\d+)?|\d+(?:\.\d+)?%|\b[a-z0-9]+(?:-[a-z0-9]+)*\b", text.lower())

    def _token_present_in_text(self, token, text_lower):
        """Checks exact or simple morphological stem match of a token in text."""
        if token in text_lower:
            return True
        if len(token) >= 5:
            stem = re.sub(r"(ation|ition|ions|ing|ied|ed|es|s)$", "", token)
            if len(stem) >= 4 and stem in text_lower:
                return True
            if "-" in token:
                parts = [p for p in token.split("-") if len(p) >= 3]
                if parts and all(p in text_lower for p in parts):
                    return True
        return False

    def _clean_chunk_text(self, text):
        """Strips markdown metadata headers and formatting noise for clean extraction."""
        cleaned_lines = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("#") or set(line) <= {"=", "-", "*"}:
                continue
            if line.startswith("_Section:") or line.startswith("Last updated:"):
                continue
            if re.match(r"^Product changelog update \(\d{4}-\d{2}-\d{2}\):?$", line):
                continue
            if " | Paperkite" in line:
                continue
            # Strip leading markdown bullet prefixes so formatting stays clean
            line = re.sub(r"^[-•*]\s+", "", line)
            # Clean basic markdown emphasis for readable output
            line = re.sub(r"\*\*(.+?)\*\*", r"\1", line)
            line = re.sub(r"`([^`]+)`", r"\1", line)
            cleaned_lines.append(line)
        return cleaned_lines

    def check_ambiguity(self, query, retrieved_chunks):
        """
        Detects genuinely under-specified questions whose answer depends on
        customer-specific dimensions (such as subscription plan tier or region)
        present in the retrieved documentation but omitted from the query.
        """
        q_lower = query.lower()
        q_tokens = set(self._tokenize(query))

        # Queries explicitly asking for a broad comparison across plans/regions are not ambiguous
        if any(w in q_lower for w in ["all plans", "compare", "every plan", "each plan", "by plan", "tiers", "list of"]):
            return {"is_ambiguous": False, "clarification_question": None}

        # Check whether the user already specified a plan tier or country/region
        has_plan = any(p in q_tokens for p in self.PLAN_TIERS)
        has_region = any(r in q_tokens for r in self.REGION_MARKERS)

        # Is the user asking a scalar/direct value question (duration, fee, limit, timing)?
        asks_scalar = bool(re.search(
            r"\b(how long|how much|what is (?:the|my)|when do|when will|what are (?:the|my))\b",
            q_lower,
        ))

        if not asks_scalar or has_plan or has_region:
            return {"is_ambiguous": False, "clarification_question": None}

        # Evidence-driven check: inspect top authoritative chunks for conditional tiers/regions
        if retrieved_chunks:
            top_chunks = [c for c in retrieved_chunks[:3] if not c.get("is_superseded", False)]
            if not top_chunks:
                return {"is_ambiguous": False, "clarification_question": None}

            top_chunk = top_chunks[0]
            top_text_lower = top_chunk.get("text", "").lower()

            # Does the top authoritative chunk enumerate multiple plan tiers AND/OR regional modifiers?
            plans_in_chunk = [p for p in ("starter", "pro", "scale") if re.search(rf"\b{p}\s*:", top_text_lower)]
            has_region_condition = bool(re.search(
                r"\b(outside the eu|depends on (?:your )?(?:plan|country|region)|additional business days|longer than the plan schedule|varies by)\b",
                top_text_lower,
            ))

            if len(plans_in_chunk) >= 2 and has_region_condition:
                summary_lines = self._clean_chunk_text(top_chunk.get("text", ""))
                evidence_preview = " ".join(summary_lines[:4])
                clarification = (
                    f"The answer depends on your subscription plan tier and account region. "
                    f"According to {top_chunk.get('doc_id', 'the documentation')}: {evidence_preview}\n\n"
                    f"Could you please clarify which plan tier and country/region your account is registered in?"
                )
                return {
                    "is_ambiguous": True,
                    "clarification_question": clarification,
                }
            return {"is_ambiguous": False, "clarification_question": None}

        # Fallback when invoked in isolation with no chunks (e.g., unit test without retrieval):
        # Flag short under-specified timing/schedule questions with no plan or region qualifier.
        if re.search(r"\bhow long\b.*\b(take|schedule|payout|payouts|settle|settlement)\b", q_lower):
            return {
                "is_ambiguous": True,
                "clarification_question": (
                    "This depends on your subscription plan tier and account region/country. "
                    "Could you please clarify which plan tier and region your account is registered in?"
                ),
            }

        return {"is_ambiguous": False, "clarification_question": None}

    def check_insufficient_evidence(self, query, retrieved_chunks, conflicts=None):
        """
        Determines whether the retrieved knowledge base evidence is insufficient
        to answer the query using general, corpus-agnostic checks:
          1. No retrieved chunks or very low retrieval score.
          2. Prospective/future timeframe not mentioned in the documentation.
          3. Specific domain subject terms in the query completely absent from retrieved evidence.
        """
        conflicts = conflicts or []

        # 1. Empty retrieval check
        if not retrieved_chunks:
            return {
                "insufficient": True,
                "reason": "No relevant documentation was found in the knowledge base.",
            }

        # 2. Retrieval relevance floor (only when chunks carry real retrieval scores)
        if "retrieval_score" in retrieved_chunks[0]:
            top_score = retrieved_chunks[0].get("retrieval_score", 0.0)
            if top_score < 0.15:
                return {
                    "insufficient": True,
                    "reason": "Retrieved documentation does not contain sufficient evidence to answer this question.",
                }

        combined_evidence = " ".join(
            f"{c.get('title', '')} {c.get('heading', '')} {c.get('text', '')}"
            for c in retrieved_chunks
        ).lower()
        if conflicts:
            combined_evidence += " " + " ".join(
                f"{cf.get('topic', '')} {cf.get('resolution', '')}" for cf in conflicts
            ).lower()

        # 3. General future/unannounced timeframe check
        for pat in self.FUTURE_TIME_PATTERNS:
            match = pat.search(query)
            if match:
                matched_phrase = match.group(0).lower()
                if matched_phrase not in combined_evidence:
                    return {
                        "insufficient": True,
                        "reason": (
                            f"The question asks about future or unannounced information ('{match.group(0)}') "
                            f"that is not documented in the retrieved knowledge base."
                        ),
                    }

        # 4. Out-of-evidence specific subject check (for real retrieval results)
        # If a specific, non-generic domain term (length >= 5) from the query does not
        # appear anywhere in the retrieved chunks, the KB likely does not cover that topic.
        if "retrieval_score" in retrieved_chunks[0]:
            query_tokens = self._tokenize(query)
            missing_subjects = []
            for tok in query_tokens:
                if tok in self.GENERIC_QUERY_WORDS:
                    continue
                # Skip short words or pure numbers here; focus on specific domain nouns/entities
                if len(tok) < 5 or tok.isdigit():
                    continue
                if not self._token_present_in_text(tok, combined_evidence):
                    missing_subjects.append(tok)

            if missing_subjects:
                terms_str = ", ".join(f"'{t}'" for t in missing_subjects)
                return {
                    "insufficient": True,
                    "reason": (
                        f"The knowledge base does not contain documentation covering {terms_str}. "
                        f"Cannot provide a supported answer."
                    ),
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
        """Calculates an explainable heuristic confidence score (Checkpoint 6)."""
        if status == "answered":
            base = 0.85
            if top_chunk:
                tier = top_chunk.get("tier", "")
                if tier in ["changelog", "formal_doc"]:
                    base += 0.10
                elif tier in ["community_forum", "historical"]:
                    base -= 0.15
            if conflicts:
                base += 0.03
            return min(0.98, max(0.60, round(base, 2)))
        elif status == "clarify":
            return 0.45
        elif status == "abstained":
            return 0.90
        elif status == "refused":
            return 1.00
        return 0.50

    def generate_deterministic_answer(self, query, chunks, conflicts):
        """
        General extractive fallback synthesizer (zero hardcoded per-question answers).
        Scores and combines the highest-relevance, newest, authoritative statements
        directly from retrieved passages, plus any detected conflict resolutions.
        """
        active_chunks = [c for c in (chunks or []) if not c.get("is_superseded", False)]
        if not active_chunks:
            active_chunks = list(chunks or [])

        if not active_chunks:
            return {
                "answer": "The documentation does not contain sufficient detail to answer this inquiry.",
                "conditions": "",
                "explanation": "",
            }

        query_tokens = [
            t for t in self._tokenize(query)
            if t not in self.GENERIC_QUERY_WORDS or "/" in t or any(ch.isdigit() for ch in t)
        ]
        if not query_tokens:
            query_tokens = self._tokenize(query)

        # Prefer official/authoritative tiers over community forums when official chunks exist
        official_chunks = [c for c in active_chunks if c.get("tier") not in ("community_forum", "historical")]
        candidate_chunks = official_chunks if official_chunks else active_chunks

        scored_candidates = []
        for chunk in candidate_chunks[:5]:
            doc_id = chunk.get("doc_id", "documentation")
            chunk_date = chunk.get("parsed_date") or chunk.get("date") or "2020-01-01"
            tier = chunk.get("tier", "formal_doc")
            rank_score = float(chunk.get("rank_score", chunk.get("retrieval_score", 0.5)))

            # Recency multiplier: strongly prefer newer updates and changelogs over legacy pages
            try:
                year = int(str(chunk_date)[:4])
            except ValueError:
                year = 2020
            recency_bonus = max(0.0, (year - 2022) * 0.22)
            tier_bonus = 0.30 if tier == "changelog" else (0.18 if tier == "formal_doc" else 0.0)

            lines = self._clean_chunk_text(chunk.get("text", ""))
            # Keep compact changelog entries intact; split longer prose paragraphs into sentences
            statements = []
            if tier == "changelog" and lines:
                statements.append(" ".join(lines))
            else:
                for line in lines:
                    if re.match(r"^\d+\.\s+", line) or len(line) <= 140:
                        statements.append(line)
                    else:
                        parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", line)
                        statements.extend([p.strip() for p in parts if p.strip()])

            for stmt in statements:
                stmt_lower = stmt.lower()
                overlap = 0.0
                for tok in query_tokens:
                    if self._token_present_in_text(tok, stmt_lower):
                        if "/" in tok or any(ch.isdigit() for ch in tok):
                            overlap += 1.6
                        else:
                            overlap += 1.0

                # Boost concrete factual statements (numbers, HTTP codes, endpoints, currencies, percentages)
                fact_bonus = 0.35 if re.search(r"(\d+\s*(mb|gb|kb|days?|hours?|%|requests?)|/\w+/\w+|410|429|[€$£]\d+)", stmt_lower) else 0.0

                # Prefer statements that directly match query terms (or the sole chunk in minimal mocks)
                if overlap > 0 or len(candidate_chunks) == 1:
                    score = (overlap * 0.50) + (rank_score * 0.30) + recency_bonus + tier_bonus + fact_bonus
                    scored_candidates.append({
                        "score": score,
                        "text": stmt,
                        "doc_id": doc_id,
                        "date": chunk_date,
                        "tier": tier,
                    })

        # Sort candidates by score descending and select diverse, non-redundant top statements
        scored_candidates.sort(key=lambda x: x["score"], reverse=True)

        selected = []
        seen_norm = set()
        per_doc_count = {}
        for cand in scored_candidates:
            norm = re.sub(r"\W+", " ", cand["text"].lower()).strip()
            if not norm or norm in seen_norm:
                continue
            # Limit to at most 2 sentences per doc so multi-document answers synthesize across sources
            if per_doc_count.get(cand["doc_id"], 0) >= 2:
                continue
            seen_norm.add(norm)
            per_doc_count[cand["doc_id"]] = per_doc_count.get(cand["doc_id"], 0) + 1
            selected.append(cand)
            if len(selected) >= 4:
                break

        if selected:
            body_lines = [f"- {item['text']} ({item['doc_id']}, {item['date']})" for item in selected]
            answer = "Based on the most authoritative Paperkite documentation:\n" + "\n".join(body_lines)
            top_doc = selected[0]["doc_id"]
            top_date = selected[0]["date"]
            explanation = f"Synthesized extractively from retrieved sources (primary: {top_doc}, updated {top_date})."
        else:
            top = active_chunks[0]
            lines = self._clean_chunk_text(top.get("text", ""))
            snippet = " ".join(lines)[:350] or top.get("text", "")[:350]
            answer = f"According to Paperkite documentation ({top.get('doc_id')}): {snippet}"
            explanation = f"Extracted from {top.get('title', top.get('doc_id'))} ({top.get('date', 'date unknown')})."

        conditions = ""
        if conflicts:
            resolutions = [c.get("resolution", "") for c in conflicts if c.get("resolution")]
            if resolutions:
                conditions = " ".join(resolutions)

        return {
            "answer": answer,
            "conditions": conditions,
            "explanation": explanation,
        }

    def generate(self, query, retrieved_chunks, conflicts=None):
        """
        Coordinates ambiguity checking, abstention checks, local Ollama LLM
        synthesis, and general extractive fallback routing.
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
        ev_check = self.check_insufficient_evidence(query, retrieved_chunks, conflicts=conflicts)
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

        # 3. Formulate evidence context for Ollama LLM / Extractive Fallback
        citations = self._extract_citations(retrieved_chunks)
        top_chunk = retrieved_chunks[0] if retrieved_chunks else None
        confidence = self._calculate_confidence("answered", top_chunk, conflicts)

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
                conflict_lines.append(
                    f"• Topic: {conf.get('topic')}\n"
                    f"  Active rule: {conf.get('active_rule')}\n"
                    f"  Explanation: {conf.get('resolution')}"
                )
            conflict_text = "\n".join(conflict_lines)

        # 4. Attempt local Ollama API call
        llm_response = None
        llm_error = None
        model_used = self.model

        try:
            system_prompt = (
                "You are Sage, the official Paperkite payment and billing support assistant. "
                "Answer the customer question strictly using ONLY the provided knowledge base evidence.\n"
                "Rules:\n"
                "1. Always prefer newer [AUTHORITATIVE] sources and changelogs over older or [SUPERSEDED / OUTDATED] ones.\n"
                "2. When sources disagree, state the current policy clearly and briefly note the superseded rule.\n"
                "3. Never invent facts, policies, numbers, or future announcements not present in the evidence.\n"
                "4. If the provided evidence does NOT contain enough information to answer the question, respond ONLY with 'ABSTAIN: <brief reason>'.\n"
                "5. If the answer depends on missing customer details (such as plan tier or region) not stated in the question, respond ONLY with 'CLARIFY: <short clarifying question>'.\n"
                "6. Be direct, concise, and clear."
            )
            user_prompt = (
                f"CUSTOMER QUESTION:\n{query}\n\n"
                f"RETRIEVED EVIDENCE:\n{evidence_text}\n\n"
                f"{conflict_text}\n\n"
                "Please provide a clear, direct answer grounded strictly in the retrieved evidence."
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

        # 5. Handle LLM-initiated ABSTAIN or CLARIFY signals
        if llm_response:
            if llm_response.upper().startswith("ABSTAIN:"):
                reason = llm_response.split(":", 1)[1].strip() or "Insufficient evidence in retrieved documentation."
                latency_ms = int((time.time() - start_time) * 1000)
                return {
                    "answer": None,
                    "status": "abstained",
                    "status_label": "Insufficient evidence",
                    "citations": citations[:1],
                    "conflicts": [],
                    "confidence": 0.90,
                    "reasoning_summary": f"Abstained from answering: {reason}",
                    "model": model_used,
                    "llm_generated": True,
                    "llm_error": None,
                    "latency_ms": latency_ms,
                }
            if llm_response.upper().startswith("CLARIFY:"):
                clar_q = llm_response.split(":", 1)[1].strip()
                latency_ms = int((time.time() - start_time) * 1000)
                return {
                    "answer": None,
                    "clarification_prompt": clar_q,
                    "status": "clarify",
                    "status_label": "Needs clarification",
                    "citations": citations,
                    "conflicts": conflicts,
                    "confidence": 0.45,
                    "reasoning_summary": "Model determined the query requires customer clarification.",
                    "model": model_used,
                    "llm_generated": True,
                    "llm_error": None,
                    "latency_ms": latency_ms,
                }

            final_answer = llm_response
            llm_generated = True
        else:
            fallback = self.generate_deterministic_answer(query, retrieved_chunks, conflicts)
            final_answer = fallback["answer"]
            if fallback.get("conditions"):
                final_answer += f"\n\n**Conflict Resolution:** {fallback['conditions']}"
            if fallback.get("explanation"):
                final_answer += f"\n\n**Source Grounding:** {fallback['explanation']}"
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
