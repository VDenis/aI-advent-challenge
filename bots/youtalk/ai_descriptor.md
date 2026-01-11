# AI Project Description: YouTalk RAG Bot

This document provides a technical overview for AI models to understand the architecture and capabilities of the YouTalk project.

## Core Objective
A conversational agent implementing RAG to provide answers based on local documents and dynamically fetched YouTube transcripts.

## Architecture
- **Retrieval Pipeline**: 
    - **Loaders**: `DirectoryLoader` (local text/markdown) and `YoutubeLoader` (remote transcripts).
    - **Chunking**: `RecursiveCharacterTextSplitter` (chunk_size: 1000, overlap: 100).
    - **Embedding**: `HuggingFaceInferenceAPIEmbeddings` (cloud-based).
    - **Vector Store**: `FAISS` (local file-based persistence at `faiss_index/`).
- **Conversational Chain**:
    - **Type**: `ConversationalRetrievalChain`.
    - **Condense Question Step**: Uses history to generate a standalone query via LLM.
    - **QA Step**: Uses retrieved context to answer the user query.
- **Memory**: `ConversationBufferMemory` tracks history for context-aware interactions.

## Key Logic Hooks
- **URL Detection**: Regex-based detection of YouTube URLs in the chat loop.
- **On-the-fly Indexing**: `add_youtube_to_index()` function adds new data to the vector store without restarting the session.
- **Source Citation**: Extracts metadata (`title` or `source`) from retrieved documents to provide a "Sources" block.

## Operational Constraints
- **Fallback**: Explicit "I don't know" response if context similarity is below a implicit threshold.
- **API Dependencies**: Requires `HF_TOKEN` for both embeddings and completion.
- **Language Support**: Optimized for Russian and English (multilingual embeddings).






