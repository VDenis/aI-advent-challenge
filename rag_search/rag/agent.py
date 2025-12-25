from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List

from rag.index_faiss import search_store
from rag.ollama_client import generate_completion, chat_completion


@dataclass
class ComparisonResult:
    question: str
    rag_answer: str
    no_rag_answer: str
    conclusion: str
    rag_chunks: List[str]  # Snippets used


class Agent:
    def __init__(self, store_path: str, embed_model: str, gen_model: str):
        self.store_path = store_path
        self.embed_model = embed_model
        self.gen_model = gen_model

    def answer_with_rag(
        self, question: str, k: int = 5, threshold: float | None = None, rerank: bool = False
    ) -> tuple[str, List[str]]:
        """
        Retrieves chunks and generates an answer using RAG.
        Returns (answer_text, list_of_chunk_snippets).
        """
        # 1. Retrieve
        results = search_store(self.store_path, question, self.embed_model, k=k, threshold=threshold)
        # Extract text from chunks
        chunk_texts = [rec.text for _, rec in results]
        
        # 2. Rerank if requested
        if rerank and chunk_texts:
            logging.info("Reranking %d chunks with LLM...", len(chunk_texts))
            chunk_texts = self._rerank_with_llm(question, chunk_texts)
            logging.info("After reranking: %d chunks remained", len(chunk_texts))

        # 3. Augment Prompt
        if not chunk_texts:
            logging.info("No relevant chunks found after filtering/reranking.")
            context_block = "No relevant context found."
        else:
            context_block = "\n---\n".join(chunk_texts)

        prompt = (
            f"Use the following context to answer the user's question.\n"
            f"If the answer is not in the context, say so, but try to answer best you can.\n\n"
            f"Context:\n{context_block}\n\n"
            f"Question: {question}\n\n"
            f"Answer:"
        )

        # 4. Generate
        logging.info("Generating RAG answer with model %s...", self.gen_model)
        answer = generate_completion(prompt, model=self.gen_model)
        return answer.strip(), chunk_texts

    def _rerank_with_llm(self, question: str, chunks: List[str]) -> List[str]:
        """
        Asks the LLM to identify which chunks are actually relevant to the question.
        Returns only the relevant chunks.
        """
        if not chunks:
            return []

        # Prepare a numbered list of chunks for the LLM to review
        chunks_formatted = ""
        for i, chunk in enumerate(chunks, 1):
            chunks_formatted += f"CHUNK {i}:\n{chunk}\n\n"

        rerank_prompt = (
            f"You are a relevance filter. For the given question, identify which of the following chunks contain information that can help answer it.\n"
            f"Question: {question}\n\n"
            f"Chunks:\n{chunks_formatted}"
            f"Respond ONLY with the indices of relevant chunks separated by commas (e.g., '1,3,4'). If none are relevant, respond with 'NONE'."
        )

        response = generate_completion(rerank_prompt, model=self.gen_model).strip()
        logging.debug("Reranker response: %s", response)

        if "NONE" in response.upper() or not response:
            return []

        try:
            # Extract indices from response (handling various potential formats like "1, 2, 3" or "1,2,3.")
            import re
            indices = [int(idx.strip()) for idx in re.split(r",|\s", response) if idx.strip().isdigit()]
            
            relevant_chunks = []
            for idx in indices:
                if 1 <= idx <= len(chunks):
                    relevant_chunks.append(chunks[idx - 1])
            return relevant_chunks
        except Exception as exc:
            logging.warning("Error parsing reranker response '%s': %s", response, exc)
            return chunks  # Fallback to all chunks if parsing fails

    def answer_no_rag(self, question: str) -> str:
        """
        Generates an answer using only the LLM's internal knowledge.
        """
        logging.info("Generating No-RAG answer with model %s...", self.gen_model)
        # Using chat completion for better instruction adherence if needed, 
        # or just simple generation. Let's use simple generation to keep it comparable.
        prompt = f"Question: {question}\nAnswer:"
        answer = generate_completion(prompt, model=self.gen_model)
        return answer.strip()

    def compare(self, question: str, threshold: float | None = None, rerank: bool = False) -> ComparisonResult:
        """
        Runs both RAG and No-RAG, then asks the LLM to compare them.
        """
        logging.info("Starting comparison for query: %s (threshold=%s, rerank=%s)", question, threshold, rerank)
        
        # 1. Get Answers
        rag_ans, chunks = self.answer_with_rag(question, threshold=threshold, rerank=rerank)
        no_rag_ans = self.answer_no_rag(question)

        # 2. Judge
        logging.info("Running LLM Judge...")
        judge_prompt = (
            "You are an expert evaluator. Compare the following two answers to the user's question.\n"
            f"Question: {question}\n\n"
            f"Answer 1 (with retrieved context):\n{rag_ans}\n\n"
            f"Answer 2 (without context):\n{no_rag_ans}\n\n"
            "Analyze the differences. Did the retrieved context improve the answer?\n"
            "Provide a short conclusion formatted as:\n"
            "CONCLUSION: [Better with RAG / Better without RAG / Equivalent]\n"
            "REASON: [Your explanation]"
        )
        
        conclusion = generate_completion(judge_prompt, model=self.gen_model)

        return ComparisonResult(
            question=question,
            rag_answer=rag_ans,
            no_rag_answer=no_rag_ans,
            conclusion=conclusion.strip(),
            rag_chunks=chunks
        )
