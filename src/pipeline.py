import time
from src.document_loader import DocumentLoader
from src.chunker import DocumentChunker
from src.retriever import HybridRetriever
from src.source_evaluator import SourceEvaluator
from src.security import SecurityGuard
from src.answer_generator import AnswerGenerator


class SagePipeline:
    """
    Unified end-to-end question answering pipeline for Paperkite.
    Coordinates security validation, hybrid retrieval, source authority evaluation,
    conflict resolution, and grounded answer generation.
    """

    def __init__(self, kb_zip="kb.zip", model="qwen2.5:3b", ollama_timeout=10):
        # 1. Initialize components
        self.security = SecurityGuard()
        self.evaluator = SourceEvaluator()
        self.generator = AnswerGenerator(model=model, timeout=ollama_timeout)

        # 2. Ensure documents and chunks are ready
        loader = DocumentLoader(kb_zip_path=kb_zip)
        docs = loader.load_all()
        loader.save_processed()

        chunker = DocumentChunker(docs)
        self.chunks = chunker.chunk_all()
        chunker.save_chunks()

        # 3. Build hybrid retriever
        self.retriever = HybridRetriever(chunks=self.chunks)

    def ask(self, question, conversation_id=None, top_k=6):
        """
        Processes a user question through the complete pipeline.
        Returns a dictionary conforming to the required REST API schema.
        """
        start_time = time.time()

        # Step 1: Security guardrail evaluation
        sec_result = self.security.evaluate_query(question)
        if not sec_result["is_safe"]:
            refusal = self.security.generate_refusal_response(category=sec_result["category"])
            refusal["latency_ms"] = int((time.time() - start_time) * 1000)
            refusal["conversation_id"] = conversation_id
            refusal["model"] = "security-guardrail"
            return refusal

        # Step 2: Hybrid retrieval (excluding internal files)
        retrieved = self.retriever.retrieve(question, top_k=top_k, filter_internal=True)

        # Step 3: Source evaluation and conflict resolution
        reranked_chunks, conflicts = self.evaluator.detect_and_resolve_conflicts(question, retrieved)

        # Step 4: Grounded answer generation
        response = self.generator.generate(question, reranked_chunks, conflicts=conflicts)
        response["conversation_id"] = conversation_id
        response["latency_ms"] = int((time.time() - start_time) * 1000)
        
        # Keep detailed evidence available for inspection
        response["retrieved_chunks"] = reranked_chunks

        # Format conflicts doc_ids as requested in technical spec
        clean_conflicts = []
        for c in conflicts:
            clean_conflicts.append({
                "doc_ids": c.get("doc_ids", []),
                "resolution": c.get("resolution", "")
            })
        response["conflicts"] = clean_conflicts

        return response
