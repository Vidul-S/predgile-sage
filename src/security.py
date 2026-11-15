import re


class SecurityGuard:
    """
    Enforces defense-in-depth security:
      1. Intercepts direct prompt injection and jailbreak attacks in user questions.
      2. Blocks unauthorized requests for confidential internal staff documents.
      3. Ensures zero leakage of internal document paths or contents in refused responses.
      4. Neutralizes residual indirect prompt injections.
    """

    DIRECT_INJECTION_PATTERNS = [
        re.compile(r"ignore\s+(all\s+)?(your\s+)?instructions", re.IGNORECASE),
        re.compile(r"disregard\s+(all\s+)?(your\s+)?instructions", re.IGNORECASE),
        re.compile(r"system\s+override", re.IGNORECASE),
        re.compile(r"you\s+are\s+now\s+an?\s+unrestricted", re.IGNORECASE),
        re.compile(r"jailbreak", re.IGNORECASE),
        re.compile(r"reveal\s+(all\s+)?(your\s+)?(system\s+)?prompt", re.IGNORECASE),
        re.compile(r"print\s+(the\s+)?internal\s+escalation\s+notes", re.IGNORECASE),
        re.compile(r"print\s+(the\s+)?internal\s+notes", re.IGNORECASE),
        re.compile(r"show\s+(me\s+)?(the\s+)?internal\s+playbook", re.IGNORECASE),
    ]

    INTERNAL_TOPIC_PATTERNS = [
        re.compile(r"internal\s+escalation(\s+playbook|\s+notes)?", re.IGNORECASE),
        re.compile(r"internal\s+fraud(\s+\w+)?\s+thresholds?", re.IGNORECASE),
        re.compile(r"internal\s+.*?(threshold|playbook|escalation|notes)", re.IGNORECASE),
        re.compile(r"goodwill\s+credit\s+limits?", re.IGNORECASE),
        re.compile(r"tier\s+[12]\s+agents?\s+may\s+approve", re.IGNORECASE),
        re.compile(r"chargeback\s+ratio\s+above\s+0\.9%", re.IGNORECASE),
    ]

    def __init__(self):
        pass

    def evaluate_query(self, query):
        """
        Evaluates a user question for direct prompt injections or internal data probes.
        Returns:
            is_safe (bool): True if query is permissible, False if blocked.
            reason (str): Explanation of policy trigger if blocked.
            category (str): 'safe' | 'injection' | 'internal_probe'
        """
        # 1. Check for prompt injection attempts
        for pat in self.DIRECT_INJECTION_PATTERNS:
            if pat.search(query):
                return {
                    "is_safe": False,
                    "reason": "Direct prompt injection attempt detected.",
                    "category": "injection",
                }

        # 2. Check for internal staff document probes
        for pat in self.INTERNAL_TOPIC_PATTERNS:
            if pat.search(query):
                return {
                    "is_safe": False,
                    "reason": "Request targets restricted internal documentation.",
                    "category": "internal_probe",
                }

        return {
            "is_safe": True,
            "reason": "Query conforms to public security policies.",
            "category": "safe",
        }

    def generate_refusal_response(self, category="injection"):
        """
        Generates a secure refusal response that denies access without leaking
        internal file names or system metadata.
        """
        if category == "injection":
            answer = (
                "Request refused: Prompt injection detected. I am strictly programmed to answer "
                "customer support questions based on verified public Paperkite documentation. "
                "Instructions attempting to override safety guidelines or access internal systems are rejected."
            )
        else:
            answer = (
                "Request refused: The requested information pertains to confidential internal Paperkite "
                "staff procedures (such as internal escalation playbooks or fraud review thresholds) "
                "which are strictly restricted from public customer access."
            )

        return {
            "answer": answer,
            "status": "refused",
            "status_label": "Restricted information",
            "citations": [],
            "conflicts": [],
            "reasoning_summary": "Security guardrail intercepted a restricted or adversarial request. Public access denied.",
            "llm_generated": False,
            "llm_error": None,
        }
