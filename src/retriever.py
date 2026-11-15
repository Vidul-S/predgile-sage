import os
import re
import json
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from rank_bm25 import BM25Okapi


class HybridRetriever:
    """
    Hybrid Retrieval Engine combining:
      1. BM25Okapi for exact keyword and identifier matching
      2. TF-IDF unigram+bigram cosine similarity for topical relevance
      3. Exact token boosting for API paths (/v1/charges), numbers (10 MB), and currencies
      4. Internal document segregation (excluding internal staff files by default)
    """

    def __init__(self, chunks=None, chunks_path="data/chunks.json"):
        if chunks:
            self.chunks = chunks
        elif os.path.exists(chunks_path):
            with open(chunks_path, "r", encoding="utf-8") as f:
                self.chunks = json.load(f)
        else:
            self.chunks = []

        self._build_indices()

    def _tokenize(self, text):
        """
        Custom tokenizer preserving API paths (/v1/charges), percentages (2.4%),
        numbers, plan tiers, and currencies.
        """
        # Lowercase while preserving punctuation inside tokens
        text_lower = text.lower()
        # Extract API endpoints, currencies, percentages, and words
        tokens = re.findall(r"/[a-z0-9_/]+|[€$£]\d+(?:\.\d+)?|\d+(?:\.\d+)?%|\b\w+(?:-\w+)*\b", text_lower)
        return tokens

    def _build_indices(self):
        if not self.chunks:
            return

        # Prepare corpus
        self.corpus_texts = []
        for c in self.chunks:
            # Combine title, heading, and text for rich indexing
            full_text = f"{c['title']} {c['heading']}\n{c['text']}"
            self.corpus_texts.append(full_text)

        # 1. Tokenized corpus for BM25
        self.tokenized_corpus = [self._tokenize(doc) for doc in self.corpus_texts]
        self.bm25 = BM25Okapi(self.tokenized_corpus)

        # 2. TF-IDF Matrix (unigram + bigram, sublinear tf)
        self.tfidf_vectorizer = TfidfVectorizer(
            tokenizer=self._tokenize,
            ngram_range=(1, 2),
            sublinear_tf=True,
            token_pattern=None,
        )
        self.tfidf_matrix = self.tfidf_vectorizer.fit_transform(self.corpus_texts)

    def retrieve(self, query, top_k=6, filter_internal=True):
        """
        Retrieves top_k chunks matching query.
        """
        if not self.chunks:
            return []

        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        # BM25 scores
        bm25_scores = np.array(self.bm25.get_scores(query_tokens))
        max_bm25 = np.max(bm25_scores) if np.max(bm25_scores) > 0 else 1.0
        norm_bm25 = bm25_scores / max_bm25

        # TF-IDF cosine similarity
        query_vec = self.tfidf_vectorizer.transform([query])
        tfidf_scores = cosine_similarity(query_vec, self.tfidf_matrix).flatten()

        # Compute composite scores
        results = []
        for i, chunk in enumerate(self.chunks):
            # Access control check
            if filter_internal and chunk.get("access") == "internal":
                continue

            bm25_s = float(norm_bm25[i])
            tfidf_s = float(tfidf_scores[i])

            # Exact phrase / identifier boost
            boost = 0.0
            chunk_text_lower = self.corpus_texts[i].lower()
            for token in query_tokens:
                # API paths or exact numbers gets bonus
                if "/" in token or "%" in token or any(c.isdigit() for c in token):
                    if token in chunk_text_lower:
                        boost += 0.25
                elif len(token) > 3 and token in chunk_text_lower:
                    boost += 0.05

            composite_score = (0.65 * bm25_s) + (0.35 * tfidf_s) + boost

            # Filter out chunks with virtually 0 relevance
            if composite_score > 0.05 or bm25_s > 0.1:
                chunk_copy = dict(chunk)
                chunk_copy["retrieval_score"] = round(float(composite_score), 4)
                chunk_copy["bm25_score"] = round(float(bm25_s), 4)
                chunk_copy["tfidf_score"] = round(float(tfidf_s), 4)
                results.append(chunk_copy)

        # Sort descending by composite score
        results.sort(key=lambda x: x["retrieval_score"], reverse=True)
        return results[:top_k]
