"""
Haechan Choi
IVI Data Sceince & Innovations
Ingestion Phase of the RAG pipeline.
Embeds to a model using Gemini API key. Chuncked by 1000 / 150.
Indexed with cosine similarity. Stored in Pinecone vector db.
"""

# import basics
import os
from dotenv import load_dotenv
import time

# import pinecone
from pinecone import Pinecone

# import langchain
from langchain_pinecone import PineconeVectorStore
from langchain_google_genai import GoogleGenerativeAIEmbeddings
# from langchain_core.documents import Document

# documents
from langchain_community.document_loaders import (
    PyPDFDirectoryLoader, DirectoryLoader, TextLoader
)
from langchain_text_splitters import RecursiveCharacterTextSplitter

load_dotenv()

pc = Pinecone(api_key=os.environ.get("PINECONE_API_KEY"))
index_name = os.environ.get("PINECONE_INDEX_NAME")

# index already created manually in the Pinecone console
# (dense, dimension=768, cosine)
index = pc.Index(index_name)

# initialize embeddings model + vector store
embeddings = GoogleGenerativeAIEmbeddings(
    model="models/gemini-embedding-001",
    google_api_key=os.environ.get("GEMINI_API_KEY"),
    output_dimensionality=768,
)
vector_store = PineconeVectorStore(index=index, embedding=embeddings)

# loading documents (PDFs + Markdown)
pdf_loader = PyPDFDirectoryLoader("documents/")
md_loader = DirectoryLoader(
    "documents/", glob="**/*.md", loader_cls=TextLoader
)
raw_documents = pdf_loader.load() + md_loader.load()

text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,
    chunk_overlap=150,
    length_function=len,
    is_separator_regex=False,
)
documents = text_splitter.split_documents(raw_documents)

uuids = [f"id{i}" for i in range(1, len(documents) + 1)]

BATCH_SIZE = 90  # stay safely under the 100/minute free-tier cap


def load_corpus_in_batches(vector_store, documents, uuids,
                           batch_size=BATCH_SIZE):
    total = len(documents)
    for i in range(0, total, batch_size):
        batch_docs = documents[i:i + batch_size]
        batch_ids = uuids[i:i + batch_size]
        vector_store.add_documents(documents=batch_docs, ids=batch_ids)
        print(f"Embedded {min(i + batch_size, total)}/{total} chunks")
        if i + batch_size < total:
            time.sleep(60)


load_corpus_in_batches(vector_store, documents, uuids)

print(f"Ingested {len(documents)} chunks into '{index_name}'.")
