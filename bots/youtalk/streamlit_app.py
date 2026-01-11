import streamlit as st
import os
import re
from dotenv import load_dotenv

# Настройка страницы
st.set_page_config(page_title="YouTalk RAG Chat", page_icon="🤖", layout="wide")

# Загрузка переменных
load_dotenv()

# Инициализация сессии
if "messages" not in st.session_state:
    st.session_state.messages = []

if "similarity_threshold" not in st.session_state:
    st.session_state.similarity_threshold = 0.5

if "use_reranker" not in st.session_state:
    st.session_state.use_reranker = True

if "vectorstore" not in st.session_state:
    status = st.status("Инициализация системы...", expanded=True)
    
    status.write("📦 Загрузка модели эмбеддингов...")
    status.write("⏳ При первом запуске модель скачивается (~400 МБ)")
    
    from main import get_vectorstore
    st.session_state.vectorstore = get_vectorstore()
    
    status.write("✅ Модель эмбеддингов загружена")
    status.write("📚 База знаний готова")
    status.update(label="Система готова!", state="complete", expanded=False)

if "chain" not in st.session_state:
    from main import get_conversation_chain
    with st.spinner("Подключение к LLM..."):
        st.session_state.chain = get_conversation_chain(st.session_state.vectorstore)

# Боковая панель (Настройки)
with st.sidebar:
    st.title("⚙️ Настройки")
    
    # Секция API
    st.subheader("🔑 API")
    hf_token = st.text_input("HuggingFace Token", value=os.getenv("HF_TOKEN", ""), type="password")
    if hf_token:
        os.environ["HF_TOKEN"] = hf_token
    
    st.divider()
    
    # Настройки фильтрации и reranking
    st.subheader("🎯 Фильтрация результатов")
    similarity_threshold = st.slider(
        "Порог схожести", 
        min_value=0.0, 
        max_value=1.0, 
        value=st.session_state.similarity_threshold, 
        step=0.05,
        help="Минимальный score для включения документа в результаты"
    )
    use_reranker = st.checkbox(
        "Использовать LLM reranker", 
        value=st.session_state.use_reranker,
        help="Переранжирует результаты с помощью LLM для лучшей релевантности"
    )
    
    if st.button("🔄 Обновить настройки поиска", use_container_width=True):
        st.session_state.similarity_threshold = similarity_threshold
        st.session_state.use_reranker = use_reranker
        from main import get_conversation_chain
        st.session_state.chain = get_conversation_chain(st.session_state.vectorstore)
        st.success("Настройки обновлены! (Фильтрация будет добавлена в следующей версии)")
    
    st.divider()
    
    # Секция YouTube
    st.subheader("📺 Добавить YouTube")
    yt_url = st.text_input("Ссылка на видео", placeholder="https://youtube.com/watch?v=...")
    
    if st.button("Индексировать видео", use_container_width=True):
        if yt_url:
            from main import add_youtube_to_index
            
            status = st.status("Обработка видео...", expanded=True)
            status.write("🔗 Подключение к YouTube...")
            status.write("📝 Загрузка субтитров...")
            
            if add_youtube_to_index(yt_url, st.session_state.vectorstore):
                status.write("✂️ Разбиение на фрагменты...")
                status.write("🧮 Создание эмбеддингов...")
                status.write("💾 Сохранение в базу знаний...")
                status.update(label="✅ Видео добавлено!", state="complete", expanded=False)
                
                # Обновляем цепочку
                from main import get_conversation_chain
                st.session_state.chain = get_conversation_chain(st.session_state.vectorstore)
                st.success("Видео успешно добавлено! Задавайте вопросы.")
            else:
                status.update(label="❌ Ошибка загрузки", state="error", expanded=False)
                st.error("Не удалось загрузить видео. Проверьте ссылку или наличие субтитров.")
        else:
            st.warning("Введите ссылку на видео.")

    st.divider()
    
    # Статистика
    st.subheader("📊 Статистика")
    if "vectorstore" in st.session_state:
        try:
            doc_count = st.session_state.vectorstore.index.ntotal
            st.metric("Документов в базе", doc_count)
        except:
            st.write("База знаний активна")
    
    st.divider()
    
    if st.button("🗑️ Очистить историю чата", use_container_width=True):
        st.session_state.messages = []
        from main import get_conversation_chain
        st.session_state.chain = get_conversation_chain(st.session_state.vectorstore)
        st.rerun()

# Основной интерфейс чата
st.title("🤖 YouTalk: RAG Чат")
st.caption("Чат-бот с памятью и доступом к вашим документам и YouTube")

# Отображение истории сообщений
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if "sources" in message and message["sources"]:
            with st.expander("📎 Источники"):
                for source in message["sources"]:
                    st.write(source)

# Ввод пользователя
if prompt := st.chat_input("Спросите что-нибудь или отправьте ссылку на YouTube..."):
    # Проверка на YouTube ссылку
    yt_regex = r"(https?://)?(www\.)?(youtube|youtu|youtube-nocookie)\.(com|be)/(watch\?v=|embed/|v/|.+\?v=)?([^&=%\?]{11})"
    yt_match = re.search(yt_regex, prompt)
    
    if yt_match:
        url = yt_match.group(0)
        with st.chat_message("user"):
            st.markdown(prompt)
        st.session_state.messages.append({"role": "user", "content": prompt})
        
        from main import add_youtube_to_index, get_conversation_chain
        
        with st.chat_message("assistant"):
            status = st.status("Обработка видео...", expanded=True)
            status.write("🔗 Подключение к YouTube...")
            status.write("📝 Загрузка субтитров...")
            
            if add_youtube_to_index(url, st.session_state.vectorstore):
                status.write("✂️ Разбиение на фрагменты...")
                status.write("🧮 Создание эмбеддингов...")
                status.write("💾 Сохранение в базу...")
                status.update(label="✅ Готово!", state="complete", expanded=False)
                
                msg = f"Видео проиндексировано! Теперь вы можете задавать по нему вопросы."
                st.markdown(msg)
                st.session_state.messages.append({"role": "assistant", "content": msg})
                st.session_state.chain = get_conversation_chain(st.session_state.vectorstore)
            else:
                status.update(label="❌ Ошибка", state="error", expanded=False)
                msg = "Не удалось загрузить видео. Проверьте ссылку или наличие субтитров."
                st.error(msg)
                st.session_state.messages.append({"role": "assistant", "content": msg})
    else:
        # Обычный вопрос
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            status = st.status("Генерация ответа...", expanded=True)
            status.write("🔍 Поиск релевантных документов...")
            status.write("🤖 Формирование ответа...")
            
            response = st.session_state.chain.invoke({"question": prompt})
            answer = response["answer"]
            source_docs = response.get("source_documents", [])
            
            status.update(label="✅ Готово!", state="complete", expanded=False)
            
            st.markdown(answer)
            
            sources = []
            if source_docs:
                seen = set()
                for doc in source_docs:
                    title = doc.metadata.get("title") or os.path.basename(doc.metadata.get("source", "unknown"))
                    fragment = doc.page_content[:150].replace("\n", " ") + "..."
                    line = f"**{title}**: {fragment}"
                    if line not in seen:
                        sources.append(line)
                        seen.add(line)
                
                with st.expander("📎 Источники"):
                    for s in sources:
                        st.write(s)
            
            st.session_state.messages.append({
                "role": "assistant", 
                "content": answer,
                "sources": sources
            })
