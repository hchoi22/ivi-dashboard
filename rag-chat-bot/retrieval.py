"""
Haechan Choi
IVI Data Sceince & Innovations
Checks the retrieval logic in the RAG pipeline.
"""

import os
from dotenv import load_dotenv
from pinecone import Pinecone
from langchain_pinecone import PineconeVectorStore
from langchain_google_genai import GoogleGenerativeAIEmbeddings

load_dotenv()

pc = Pinecone(api_key=os.environ.get("PINECONE_API_KEY"))
index_name = os.environ.get("PINECONE_INDEX_NAME")
index = pc.Index(index_name)

embeddings = GoogleGenerativeAIEmbeddings(
    model="models/gemini-embedding-001",
    google_api_key=os.environ.get("GEMINI_API_KEY"),
    output_dimensionality=768,
)
vector_store = PineconeVectorStore(index=index, embedding=embeddings)

# retrieves the vectors using the similarity score.
# only retrieve the necessary vectors only.
retriever = vector_store.as_retriever(
    search_type="similarity_score_threshold",
    search_kwargs={"k": 5, "score_threshold": 0.5},
)
results = retriever.invoke(
    "What was the STUDY_A trial's vaccine dose schedule?"
)

print("RESULTS:")
for res in results:
    print(f"* {res.page_content} [{res.metadata}]")
