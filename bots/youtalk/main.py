import os
import sys
import re
from typing import List

from dotenv import load_dotenv
from langchain.chains import ConversationalRetrievalChain
from langchain.memory import ConversationBufferMemory
from langchain_community.document_loaders import DirectoryLoader, TextLoader, YoutubeLoader
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEndpoint, HuggingFaceEmbeddings
from langchain_openai import ChatOpenAI
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.prompts import PromptTemplate
from langchain.schema import Document
from typing import List, Tuple

# Загрузка переменных окружения (HF_TOKEN)
load_dotenv()

# Пути
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOCS_DIR = os.path.join(BASE_DIR, "docs")
INDEX_PATH = os.path.join(BASE_DIR, "faiss_index")

def get_vectorstore():
    """Загружает документы, разбивает на чанки и создает/загружает индекс FAISS."""
    # Используем ЛОКАЛЬНЫЕ эмбеддинги — работают стабильно без API
    print("📦 Загрузка модели эмбеддингов...")
    print("   (При первом запуске модель скачивается ~400 МБ)")
    embeddings = HuggingFaceEmbeddings(
        model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        show_progress=True
    )
    print("✅ Модель эмбеддингов загружена")
    
    if os.path.exists(INDEX_PATH):
        print("📚 Загрузка существующей базы знаний...")
        try:
            vs = FAISS.load_local(INDEX_PATH, embeddings, allow_dangerous_deserialization=True)
            print(f"✅ База знаний загружена ({vs.index.ntotal} документов)")
            return vs
        except Exception as e:
            print(f"⚠️ Ошибка загрузки индекса: {e}. Создаем новый.")

    print("🆕 Инициализация новой базы знаний...")
    if not os.path.exists(DOCS_DIR):
        os.makedirs(DOCS_DIR)

    loader = DirectoryLoader(DOCS_DIR, glob="**/*.[tm][xd][t]", loader_cls=TextLoader)
    documents = loader.load()

    if not documents:
        # Локальные эмбеддинги работают с FAISS напрямую
        vectorstore = FAISS.from_texts(["Начало базы знаний."], embeddings)
    else:
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
        chunks = text_splitter.split_documents(documents)
        vectorstore = FAISS.from_documents(chunks, embeddings)

    vectorstore.save_local(INDEX_PATH)
    return vectorstore

def add_youtube_to_index(url, vectorstore):
    """Скачивает субтитры и добавляет их в индекс."""
    print(f"🔗 Подключение к YouTube: {url}")
    
    # Извлекаем video_id из URL
    import re as regex
    video_id_match = regex.search(r"(?:v=|youtu\.be/)([^&=%\?]{11})", url)
    if not video_id_match:
        print("❌ Не удалось извлечь ID видео из ссылки")
        return False
    
    video_id = video_id_match.group(1)
    
    # Пробуем разные способы загрузки субтитров
    documents = None
    
    # Способ 1: Ручные субтитры (ru, en)
    for lang in [["ru"], ["en"], ["ru", "en"]]:
        try:
            print(f"📝 Попытка загрузки субтитров: {lang}...")
            loader = YoutubeLoader.from_youtube_url(
                url, 
                add_video_info=True,
                language=lang,
            )
            documents = loader.load()
            if documents and documents[0].page_content.strip():
                print(f"✅ Найдены субтитры: {lang}")
                break
        except Exception as e:
            print(f"   ⚠️ {lang}: {str(e)[:80]}")
            documents = None
    
    # Способ 2: Через yt-dlp (самый надежный способ)
    if not documents:
        try:
            print("📝 Попытка загрузки через yt-dlp...")
            import yt_dlp
            
            ydl_opts = {
                'writesubtitles': True,
                'writeautomaticsub': True,
                'subtitleslangs': ['ru', 'en'],
                'skip_download': True,
                'quiet': True,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                title = info.get('title', f'YouTube: {video_id}')
                
                # Получаем субтитры из info
                subtitles = info.get('subtitles', {}) or info.get('automatic_captions', {})
                
                text = None
                used_lang = None
                
                # Пробуем русские, потом английские
                for lang in ['ru', 'en']:
                    if lang in subtitles:
                        subtitle_url = subtitles[lang][0].get('url')
                        if subtitle_url:
                            import urllib.request
                            subtitle_data = urllib.request.urlopen(subtitle_url).read().decode('utf-8')
                            
                            # Парсим субтитры (формат может быть разный)
                            if '<?xml' in subtitle_data or '<transcript>' in subtitle_data:
                                # XML формат
                                import re
                                text_parts = re.findall(r'<text[^>]*>([^<]+)</text>', subtitle_data)
                                text = " ".join(text_parts)
                            else:
                                # Простой текст или SRT
                                lines = subtitle_data.split('\n')
                                clean_lines = []
                                for line in lines:
                                    line = line.strip()
                                    if line and not line.isdigit() and '-->' not in line and not line.startswith('WEBVTT'):
                                        clean_lines.append(line)
                                text = " ".join(clean_lines)
                            
                            if text and len(text.strip()) > 10:
                                used_lang = lang
                                print(f"   ✅ Найдены субтитры: {lang} ({len(text)} символов)")
                                break
                
                if text and len(text.strip()) > 10:
                    from langchain.schema import Document
                    documents = [Document(
                        page_content=text,
                        metadata={"source": url, "title": title}
                    )]
                    print(f"✅ Субтитры загружены через yt-dlp")
        except Exception as e:
            print(f"   ⚠️ Ошибка yt-dlp: {e}")
    
    # Способ 3: Через youtube-transcript-api (запасной)
    if not documents:
        try:
            print("📝 Попытка через youtube-transcript-api...")
            try:
                from youtube_transcript_api import YouTubeTranscriptApi
                transcript_data = None
                
                for lang in ['ru', 'en']:
                    try:
                        print(f"   Пробуем язык: {lang}...")
                        transcript_data = YouTubeTranscriptApi.get_transcript(video_id, languages=[lang])
                        print(f"   ✅ Найдено: {lang}")
                        break
                    except Exception:
                        pass
                
                if not transcript_data:
                    print("   Пробуем любые доступные субтитры...")
                    transcript_data = YouTubeTranscriptApi.get_transcript(video_id)
                
                if transcript_data:
                    text = " ".join([entry['text'] for entry in transcript_data])
                    from langchain.schema import Document
                    documents = [Document(
                        page_content=text,
                        metadata={"source": url, "title": f"YouTube: {video_id}"}
                    )]
                    print(f"✅ Субтитры загружены через youtube-transcript-api ({len(text)} символов)")
            except Exception as e:
                print(f"   ⚠️ Ошибка youtube-transcript-api: {e}")
                
        except Exception as e:
            print(f"❌ Ошибка загрузки субтитров: {e}")
    
    if not documents or not documents[0].page_content.strip():
        print("❌ Субтитры не найдены или пусты")
        return False
    
    try:
        title = documents[0].metadata.get('title', f'YouTube: {video_id}')
        print(f"✂️ Разбиение на фрагменты: {title}")
        
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
        chunks = text_splitter.split_documents(documents)
        
        print(f"🧮 Создание эмбеддингов для {len(chunks)} фрагментов...")
        vectorstore.add_documents(chunks)
        
        print("💾 Сохранение в базу знаний...")
        vectorstore.save_local(INDEX_PATH)
        
        print(f"✅ Успешно добавлено: {title}")
        return True
    except Exception as e:
        print(f"❌ Ошибка при обработке: {e}")
        return False

def filter_by_similarity(docs_with_scores: List[Tuple[Document, float]], 
                        similarity_threshold: float = 0.5) -> List[Document]:
    """Фильтрует документы по порогу схожести."""
    filtered = []
    for doc, score in docs_with_scores:
        if score >= similarity_threshold:
            filtered.append((doc, score))
        else:
            print(f"   ⚠️ Отфильтрован документ (score={score:.3f} < {similarity_threshold})")
    return filtered

def rerank_with_llm(query: str, documents: List[Tuple[Document, float]], 
                    llm: ChatOpenAI, top_k: int = 3) -> List[Document]:
    """Переранжирует документы с помощью LLM по релевантности к запросу."""
    if not documents or len(documents) <= 1:
        return [doc for doc, _ in documents]
    
    print(f"   🔄 Reranking {len(documents)} документов...")
    
    # Формируем промпт для оценки релевантности
    docs_text = ""
    for i, (doc, score) in enumerate(documents):
        title = doc.metadata.get("title", doc.metadata.get("source", "unknown"))
        content_preview = doc.page_content[:200].replace("\n", " ")
        docs_text += f"\n{i+1}. [{title}] Score: {score:.3f}\n{content_preview}...\n"
    
    rerank_prompt = f"""Оцени релевантность следующих документов к запросу пользователя.
Верни ТОЛЬКО номера самых релевантных документов через запятую (например: 1,3,4).
Если ни один документ не релевантен, верни "NONE".

Запрос: {query}

Документы:
{docs_text}

Номера релевантных документов:"""
    
    try:
        response = llm.invoke(rerank_prompt)
        response_text = response.content if hasattr(response, 'content') else str(response)
        
        # Парсим ответ
        if "NONE" in response_text.upper() or not response_text.strip():
            print("   ⚠️ LLM не нашёл релевантных документов")
            return [doc for doc, _ in documents[:top_k]]
        
        # Извлекаем номера
        import re
        numbers = [int(n.strip()) for n in re.findall(r'\d+', response_text) 
                   if 1 <= int(n.strip()) <= len(documents)]
        
        if not numbers:
            print("   ⚠️ Не удалось распарсить ответ LLM, используем топ по score")
            return [doc for doc, _ in sorted(documents, key=lambda x: x[1], reverse=True)[:top_k]]
        
        # Возвращаем документы в порядке релевантности
        reranked = [documents[i-1][0] for i in numbers if 1 <= i <= len(documents)]
        print(f"   ✅ Отобрано {len(reranked)} релевантных документов")
        return reranked[:top_k]
        
    except Exception as e:
        print(f"   ⚠️ Ошибка reranking: {e}, используем исходный порядок")
        return [doc for doc, _ in sorted(documents, key=lambda x: x[1], reverse=True)[:top_k]]

def apply_filtering_and_reranking(vectorstore, query: str, similarity_threshold: float, 
                                 use_reranker: bool, top_k: int, llm=None) -> List[Document]:
    """Применяет фильтрацию и reranking к результатам поиска."""
    # Получаем больше документов для фильтрации
    search_k = top_k * 2 if use_reranker else top_k
    docs_with_scores = vectorstore.similarity_search_with_score(query, k=search_k)
    
    print(f"   📊 Найдено {len(docs_with_scores)} документов")
    
    # Фильтрация по порогу схожести
    filtered = filter_by_similarity(docs_with_scores, similarity_threshold)
    print(f"   ✅ После фильтрации: {len(filtered)} документов")
    
    if not filtered:
        # Если ничего не прошло фильтр, возвращаем топ-1
        if docs_with_scores:
            return [docs_with_scores[0][0]]
        return []
    
    # Reranking через LLM
    if use_reranker and llm and len(filtered) > 1:
        reranked = rerank_with_llm(query, filtered, llm, top_k=top_k)
        return reranked
    
    # Возвращаем топ по score
    return [doc for doc, _ in sorted(filtered, key=lambda x: x[1], reverse=True)[:top_k]]

class FilteredRetriever:
    """Retriever с фильтрацией и reranking."""
    
    def __init__(self, vectorstore, similarity_threshold=0.5, use_reranker=True, top_k=5, llm=None):
        self.vectorstore = vectorstore
        self.similarity_threshold = similarity_threshold
        self.use_reranker = use_reranker
        self.top_k = top_k
        self.llm = llm
    
    def get_relevant_documents(self, query: str) -> List[Document]:
        """Получает релевантные документы с фильтрацией и reranking."""
        return apply_filtering_and_reranking(
            self.vectorstore, query, 
            self.similarity_threshold, 
            self.use_reranker, 
            self.top_k, 
            self.llm
        )

def get_conversation_chain(vectorstore):
    """Инициализация цепочки с HuggingFace Online LLM через новый роутер."""
    hf_token = os.getenv("HF_TOKEN")
    
    # Используем ChatOpenAI с новым роутером Hugging Face
    llm = ChatOpenAI(
        model="meta-llama/Llama-3.1-8B-Instruct",
        openai_api_key=hf_token,
        openai_api_base="https://router.huggingface.co/v1",
        temperature=0.1,
        max_tokens=512,
        timeout=120
    )
    
    condense_question_template = """Учитывая историю диалога и новый вопрос, перефразируй его в самостоятельный вопрос на русском языке.
История:
{chat_history}
Вопрос: {question}
Самостоятельный вопрос:"""
    condense_question_prompt = PromptTemplate.from_template(condense_question_template)

    qa_template = """Используй следующий контекст, чтобы ответить на вопрос пользователя на русском языке. 
Если в контексте нет ответа, так и скажи.

Контекст:
{context}

Вопрос: {question}
Ответ:"""
    qa_prompt = PromptTemplate.from_template(qa_template)

    memory = ConversationBufferMemory(
        memory_key="chat_history", 
        return_messages=True, 
        output_key="answer"
    )

    # Используем стандартный retriever (без фильтрации в самом retriever)
    # Фильтрация будет применяться через кастомную функцию
    retriever = vectorstore.as_retriever(search_kwargs={"k": 10})

    return ConversationalRetrievalChain.from_llm(
        llm=llm,
        retriever=retriever,
        memory=memory,
        return_source_documents=True,
        condense_question_prompt=condense_question_prompt,
        combine_docs_chain_kwargs={"prompt": qa_prompt}
    )

def main():
    if not os.getenv("HF_TOKEN"):
        print("Ошибка: HF_TOKEN не найден в .env")
        return

    vectorstore = get_vectorstore()
    chain = get_conversation_chain(vectorstore)

    print("\n🤖 YouTalk RAG готов!")
    print("📺 Отправьте ссылку на YouTube для индексации")
    print("❓ Или задайте вопрос по базе знаний")
    print("🚪 Для выхода введите: exit\n")
    
    yt_regex = r"(https?://)?(www\.)?(youtube|youtu|youtube-nocookie)\.(com|be)/(watch\?v=|embed/|v/|.+\?v=)?([^&=%\?]{11})"

    while True:
        try:
            user_input = input("\nВы: ").strip()
            if user_input.lower() in ["exit", "quit", "выход"]: break
            if not user_input: continue

            yt_match = re.search(yt_regex, user_input)
            if yt_match:
                url = yt_match.group(0)
                if add_youtube_to_index(url, vectorstore):
                    print("Видео добавлено! Теперь можно спрашивать по его содержанию.")
                continue

            print("🔍 Поиск релевантных документов...")
            response = chain.invoke({"question": user_input})
            print(f"\n💬 Ответ: {response['answer']}")
            
            print("\nИсточники:")
            source_docs = response.get("source_documents", [])
            if source_docs:
                seen = set()
                for doc in source_docs:
                    title = doc.metadata.get("title") or os.path.basename(doc.metadata.get("source", "unknown"))
                    fragment = doc.page_content[:60].replace("\n", " ") + "..."
                    line = f"{title} — {fragment}"
                    if line not in seen:
                        print(line)
                        seen.add(line)
            else:
                print("Нет источников")
        except KeyboardInterrupt: break

if __name__ == "__main__":
    main()
