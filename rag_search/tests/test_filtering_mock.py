import unittest
from unittest.mock import patch, MagicMock
from rag.agent import Agent
from rag.index_faiss import ChunkRecord

class TestReranking(unittest.TestCase):
    def setUp(self):
        self.agent = Agent(store_path="fake_store", embed_model="fake_embed", gen_model="fake_gen")

    @patch("rag.agent.search_store")
    @patch("rag.agent.generate_completion")
    def test_answer_with_rag_threshold(self, mock_gen, mock_search):
        # Mock search results: two chunks with different scores
        mock_search.return_value = [
            (0.8, ChunkRecord(1, "file1", 0, 10, "Relevant text")),
            (0.4, ChunkRecord(2, "file2", 0, 10, "Irrelevant noise"))
        ]
        mock_gen.return_value = "Final answer"

        # 1. Test without threshold
        ans, chunks = self.agent.answer_with_rag("Question", threshold=None)
        self.assertEqual(len(chunks), 2)
        mock_search.assert_called_with("fake_store", "Question", "fake_embed", k=5, threshold=None)

        # 2. Test with threshold
        # Note: threshold is passed to search_store, but search_store is mocked.
        # To test filtering, we simulate search_store filtering results.
        mock_search.return_value = [(0.8, ChunkRecord(1, "file1", 0, 10, "Relevant text"))]
        ans, chunks = self.agent.answer_with_rag("Question", threshold=0.5)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0], "Relevant text")

    @patch("rag.agent.search_store")
    @patch("rag.agent.generate_completion")
    def test_answer_with_rag_rerank(self, mock_gen, mock_search):
        mock_search.return_value = [
            (0.8, ChunkRecord(1, "file1", 0, 10, "Chunk 1 Content")),
            (0.7, ChunkRecord(2, "file2", 0, 10, "Chunk 2 Content"))
        ]
        
        # Mock reranker output: only chunk 1 is relevant
        # Mock sequence: 1st call for reranking, 2nd call for final answer
        mock_gen.side_effect = ["1", "Final answer"]

        ans, chunks = self.agent.answer_with_rag("Question", rerank=True)
        
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0], "Chunk 1 Content")
        self.assertEqual(ans, "Final answer")

    @patch("rag.agent.generate_completion")
    def test_rerank_parsing(self, mock_gen):
        chunks = ["Text 1", "Text 2", "Text 3"]
        
        # Test comma separated
        mock_gen.return_value = "1, 3"
        res = self.agent._rerank_with_llm("Q", chunks)
        self.assertEqual(res, ["Text 1", "Text 3"])

        # Test space separated
        mock_gen.return_value = "2 3"
        res = self.agent._rerank_with_llm("Q", chunks)
        self.assertEqual(res, ["Text 2", "Text 3"])

        # Test "NONE"
        mock_gen.return_value = "NONE"
        res = self.agent._rerank_with_llm("Q", chunks)
        self.assertEqual(res, [])

if __name__ == "__main__":
    unittest.main()
