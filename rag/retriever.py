import math
import re
from collections import Counter

POLICY_DOCUMENTS = [
    {"id": "credit_policy", "title": "Credit Score Policy",
     "content": "Minimum credit score for loan approval is 700 on the CIBIL scale. Scores of 750+ are excellent. Scores below 700 do not meet automatic approval threshold."},
    {"id": "dti_policy", "title": "EMI-to-Income Ratio Policy",
     "content": "Total EMI must not exceed 40% of monthly income. Preferred ratio is 30% or below. EMI-to-income above 40% results in rejection."},
    {"id": "age_policy", "title": "Age Eligibility Policy",
     "content": "Applicants must be between 21 and 60 years. Age below 21 or above 60 is a hard ineligibility criterion."},
    {"id": "employment_policy", "title": "Employment Stability Policy",
     "content": "Salaried score 1.0, Self-Employed 0.75, Contract 0.60, Unemployed 0.0 and not eligible."},
    {"id": "compliance_policy", "title": "RBI Fair Lending Compliance",
     "content": "Decisions must comply with RBI Fair Lending Guidelines 2023. No discrimination by gender, religion, or caste. Every decision logged with trace ID."},
    {"id": "risk_policy", "title": "Risk Band Assessment",
     "content": "Risk composite: credit 45%, EMI-to-income 35%, employment 20%. LOW>=0.75, MEDIUM>=0.50, HIGH>=0.25, CRITICAL<0.25."},
]


class KnowledgeRetriever:
    def __init__(self):
        self._docs = POLICY_DOCUMENTS
        self._tfidf = self._build_tfidf()

    def _tokenize(self, text: str) -> list:
        return re.findall(r'\b[a-z]+\b', text.lower())

    def _build_tfidf(self) -> list:
        N = len(self._docs)
        df: Counter = Counter()
        tf_per_doc = []
        for doc in self._docs:
            tokens = self._tokenize(doc["content"])
            tf = Counter(tokens)
            total = sum(tf.values())
            tf_per_doc.append({t: c / total for t, c in tf.items()})
            df.update(set(tokens))
        idf = {term: math.log(N / freq) for term, freq in df.items()}
        return [{t: s * idf.get(t, 0) for t, s in tf.items()} for tf in tf_per_doc]

    def _cosine(self, q: dict, d: dict) -> float:
        dot = sum(q.get(t, 0) * d.get(t, 0) for t in q)
        nq = math.sqrt(sum(v ** 2 for v in q.values()))
        nd = math.sqrt(sum(v ** 2 for v in d.values()))
        return dot / (nq * nd) if nq and nd else 0.0

    def retrieve(self, query: str, top_k: int = 2) -> list:
        tokens = self._tokenize(query)
        total = len(tokens) or 1
        qvec = {t: tokens.count(t) / total for t in set(tokens)}
        scored = sorted(enumerate(self._tfidf), key=lambda x: self._cosine(qvec, x[1]), reverse=True)
        return [self._docs[i] for i, _ in scored[:top_k]]

    def get_context_for_applicant(self, applicant_data: dict) -> str:
        queries = ["loan eligibility rules compliance"]
        if applicant_data.get("credit_score", 900) < 750:
            queries.append("credit score minimum threshold")
        if applicant_data.get("employment_type") in ("Contract", "Self-Employed", "Unemployed"):
            queries.append("employment stability score")
        seen, docs = set(), []
        for q in queries:
            for d in self.retrieve(q):
                if d["id"] not in seen:
                    seen.add(d["id"])
                    docs.append(d)
        return "\n\n".join(f"## {d['title']}\n{d['content']}" for d in docs)
