# RAG Chatbot Pipeline

## 1. Introduction

This chatbot answers questions about the IVI Vi-DT study documentation using retrieval-augmented generation (RAG). Rather than relying on a language model's built-in knowledge, it retrieves relevant chunks from a vector database of ingested documents and grounds every answer in that retrieved context. The chatbot acts as an introductory tool for all users to utilize before reviewing the dashboard that can fill in the gaps of domain knowledge in the clinical study.
## 2. Pipeline flow diagram.

```
┌───────────────────────────────────────────────────────────────────────┐
│                     1. Source Documents                               │
│   • README files (synthetic dataset summaries)                        │
│   • Research papers (T002, T005)                                │
│   • Clinical Research Summary (T006)                                  │
└──────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌───────────────────────────────────────────────────────────────────────┐
│                     2. Ingestion (rag-chat-bot/)                      │
│   • Loads PDFs from a local directory                                 │
│   • Splits documents into overlapping chunks                          │
│   • Embeds each chunk and stores it in the vector database            │
└──────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌───────────────────────────────────────────────────────────────────────┐
│                     3. Vector Database (Pinecone)                     │
│   • Serverless index, cosine similarity                               │
│   • Holds every embedded chunk with its metadata                      │
└──────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌───────────────────────────────────────────────────────────────────────┐
│                     4. Retrieval + Generation (Home.py)               │
│   • Embeds the user's question                                        │
│   • Retrieves the top matching chunks above a similarity threshold    │
│   • Injects retrieved context into the system prompt                  │
│   • Chat model generates an answer grounded in that context           │
└───────────────────────────────────────────────────────────────────────┘
```

## 3. Why RAG.

A chat model on its own only knows what it was trained on, and it has no way to answer questions about study-specific documents it's never seen. Retrieval-augmented generation solves this by pairing the model with a search step. Before generating an answer, the system retrieves the most relevant chunks of the actual source documents and feeds them into the prompt as context.

The tradeoff is that answer quality now depends on retrieval quality. If the wrong chunks get retrieved, or a relevant chunk got split awkwardly during ingestion, the model's answer will be grounded in the wrong context. This is addressed through chunk overlap at ingestion time and a similarity-score threshold at retrieval time, so weak or irrelevant matches are filtered out rather than forced into the prompt.

## 4. Architecture.

The pipeline is split across two locations. The ingestion and retrieval test scripts live in rag-chat-bot/, and the live retrieval-and-generation logic lives in Home.py at the project root, since that's also the dashboard's entry page.

**Ingestion** loads every PDF from a local documents directory, splits each one into overlapping chunks, and embeds each chunk into a vector before storing it in Pinecone. The chunks are set to 1000 characters in length with 150 characters in overlap. This is a relatively weak chunk; however, considering the chatbot’s goal as a simple introductory chatbot, this weak chunk is aimed to be more efficient in terms of its retrieval for short concise answers at a faster response rate. This step only needs to run when the source documents change.

**Retrieval** happens on every user question. The question itself gets embedded using the same embedding model as ingestion, then compared against every stored vector using cosine similarity. Only chunks above a set similarity threshold are returned, so a question with no good match in the source documents doesn't get forced into an answer.

**Generation** takes the retrieved chunks, injects them into a system prompt that instructs the chat model to answer only from that context, and sends the full conversation history to the chat model. The response is parsed back into plain text before being shown in the dashboard's chat interface.

## 5. Tech Stack

- LangChain
- Google Generative AI (Gemini embeddings, Gemini chat model)
- Pinecone (vector database)
- python-dotenv
- Streamlit (chat interface, inside `Home.py`)

## 6. Known Limitations / Next Steps

The first limitation is chunk size tuning. The current chunking configuration was adjusted once already during development, moving from a 50%-overlap setup to a leaner 15%-overlap setup to reduce index size. This tradeoff hasn't been validated against retrieval quality on the actual source documents yet, so it's worth revisiting if answers start missing context that should have been retrievable. It would be valuable to analyze the documents and consider the average sentence length and the different impact of the sizes on the RAG model’s performance.

A second limitation comes from relying on Gemini 3.6 Flash's free tier. The free tier enforces hard caps on queries per minute and per hour, so once those limits are hit, the chatbot stops responding or returns errors regardless of how well the retrieval pipeline itself is performing. This becomes a real constraint the moment more than a handful of users query the dashboard around the same time, since the rate limit is shared across all requests rather than scoped per user. Before this dashboard supports concurrent or production use, both the embedding model and the chat model need to be reassessed, either by moving to a paid tier with higher throughput, or by selecting models built to handle sustained concurrent load, since the current setup was chosen for development convenience, not for scale.

## 7. Data Provenance / Privacy Note

The documents ingested into this pipeline are limited to README files describing synthetic dataset structure and published research papers for T002, T005, and T006. No subject-level data, raw clinical records, or real participant information is ingested into the vector database. This scope is intentional. If subject-level datasets are ever added to the ingestion path, this note and the privacy review behind it need to be revisited before that happens.
