import types
import unittest

from cli import hf_llama3_openai as cli


class DummyTokenizer:
    def __init__(self, counter):
        self._counter = counter

    def __call__(self, text: str, add_special_tokens: bool = False):
        token_count = self._counter(text)
        return types.SimpleNamespace(input_ids=list(range(token_count)))


class CountTokensLocalTests(unittest.TestCase):
    def setUp(self):
        self._original_auto_tokenizer = cli.AutoTokenizer
        cli._get_tokenizer.cache_clear()

        def fake_from_pretrained(model_id: str):
            return DummyTokenizer(lambda text: len(text.encode("utf-8")))

        cli.AutoTokenizer = types.SimpleNamespace(from_pretrained=fake_from_pretrained)

    def tearDown(self):
        cli.AutoTokenizer = self._original_auto_tokenizer
        cli._get_tokenizer.cache_clear()

    def test_empty_string_has_zero_tokens(self):
        self.assertEqual(cli.count_tokens_local(""), 0)

    def test_non_empty_text_has_tokens(self):
        self.assertGreater(cli.count_tokens_local("Привет"), 0)


if __name__ == "__main__":
    unittest.main()
