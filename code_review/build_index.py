"""Build RAG index for code review context."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../progect_assistant"))

from assistant.rag import RagIndexer


def main():
    """Build RAG index for the project."""
    project_root = os.getenv("PROJECT_ROOT", os.getcwd())
    cache_path = os.path.join(project_root, ".cache/rag_index.json")

    print(f"Building RAG index for project: {project_root}")
    print(f"Cache path: {cache_path}")

    indexer = RagIndexer(project_root=project_root, cache_path=cache_path)

    # Build index with verbose output
    index = indexer.build_index(verbose=True)

    print(f"\n✓ RAG index built successfully!")
    print(f"  Total chunks: {len(index.chunks)}")
    print(f"  Cached at: {cache_path}")


if __name__ == "__main__":
    main()
