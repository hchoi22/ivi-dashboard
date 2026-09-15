"""
Haechan Choi
IVI Data Sceince & Innovations
Home page of the Dashboard.
Initializes the chatbot in the homepage.
Gives a system prompt that purposely targets a simple concise answer.
"""
import streamlit as st
from sidebar_nav import render_sidebar
from auth_check import require_auth
import os
from dotenv import load_dotenv

from pinecone import Pinecone

from langchain_pinecone import PineconeVectorStore
from langchain_google_genai import (
    GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI
)
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

load_dotenv()

st.set_page_config(page_title="IVI Clinical Data Dashboard", layout="wide")
require_auth()

render_sidebar(current_page="Home")

st.header("IVI Clinical Data Dashboard")
st.caption("Start off with a simple question")

st.markdown(
    """
    <style>
    [data-testid="stChatMessage"]:has(
        [data-testid="stChatMessageAvatarUser"]
    ) {
        background-color: #FFFFFF;
        border: 1px solid #E0E0E0;
        border-radius: 12px;
        padding: 8px 12px;
    }
    [data-testid="stChatMessage"]:has(
        [data-testid="stChatMessageAvatarAssistant"]
    ) {
        background-color: #D6EAF8;
        border-radius: 12px;
        padding: 8px 12px;
    }
    [data-testid="stChatMessageAvatarUser"] {
        background-color: #FFFFFF !important;
    }
    [data-testid="stChatMessageAvatarAssistant"] {
        background-color: #D6EAF8 !important;
    }
    [data-testid="stChatMessageAvatarUser"] svg,
    [data-testid="stChatMessageAvatarAssistant"] svg,
    [data-testid="stChatMessageAvatarUser"] svg path,
    [data-testid="stChatMessageAvatarAssistant"] svg path {
        fill: #000000 !important;
        stroke: #000000 !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

pc = Pinecone(api_key=os.environ.get("PINECONE_API_KEY"))
index_name = os.environ.get("PINECONE_INDEX_NAME")
index = pc.Index(index_name)

embeddings = GoogleGenerativeAIEmbeddings(
    model="models/gemini-embedding-001",
    google_api_key=os.environ.get("GEMINI_API_KEY"),
    output_dimensionality=768,
)
vector_store = PineconeVectorStore(index=index, embedding=embeddings)

if "messages" not in st.session_state:
    st.session_state.messages = []

st.session_state.messages.append(
    SystemMessage("You are an assistant for question-answering tasks.")
)

for message in st.session_state.messages:
    if isinstance(message, HumanMessage):
        with st.chat_message("user"):
            st.markdown(message.content)
    elif isinstance(message, AIMessage):
        with st.chat_message("assistant"):
            st.markdown(message.content)

prompt = st.chat_input("How are you?")

if prompt:
    with st.chat_message("user"):
        st.markdown(prompt)
    st.session_state.messages.append(HumanMessage(prompt))

    llm = ChatGoogleGenerativeAI(
        model="gemini-3.6-flash",
        temperature=0.3,
        google_api_key=os.environ.get("GEMINI_API_KEY"),
    )

    # retrieves the vectors using the similarity score.
    # only retrieve the necessary vectors only.
    retriever = vector_store.as_retriever(
        search_type="similarity_score_threshold",
        search_kwargs={"k": 3, "score_threshold": 0.5},
    )
    docs = retriever.invoke(prompt)
    docs_text = "".join(d.page_content for d in docs)

    system_prompt = """You are an assistant for question-answering tasks.
Use the following pieces of retrieved context to answer the question.
If you don't know the answer, just say that you don't know.
Use three sentences maximum and keep the answer concise.
Context: {context}:"""
    system_prompt_fmt = system_prompt.format(context=docs_text)

    st.session_state.messages.append(SystemMessage(system_prompt_fmt))

    raw_result = llm.invoke(st.session_state.messages).content

    # considers when the result returns a list
    # takes whatever raw shape Gemini hands back
    # and pulls out just the human-readable text
    if isinstance(raw_result, list):
        result = "".join(
            block.get("text", "")
            for block in raw_result
            if isinstance(block, dict) and block.get("type") == "text"
        )
    else:
        result = raw_result

    with st.chat_message("assistant"):
        st.markdown(result)
    st.session_state.messages.append(AIMessage(result))
