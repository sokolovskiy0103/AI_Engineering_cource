# CityPark Central - Parking Lot Assistant

An AI-powered chatbot for **CityPark Central** that answers questions about the parking facility and books reservations through a conversational interface.

Built with FastAPI, LangGraph agents, Azure OpenAI, and PostgreSQL with pgvector for RAG-based context retrieval.

## Features

- **Conversational Q&A** — answers questions about parking rates, hours, policies, and facilities using RAG over a knowledge base
- **Reservation booking** — collects customer details through multi-turn conversation and creates bookings via a tool-calling agent
- **PII redaction** — automatically detects and redacts sensitive information (SSNs, credit cards, phone numbers, etc.) from responses using Presidio
- **Session memory** — maintains conversation history per session for natural multi-turn interactions
- **RAG evaluation** — offline evaluation pipeline using RAGAS metrics (context recall, precision, faithfulness, relevancy)

## Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) package manager
- Docker (for PostgreSQL + pgvector)
- Azure OpenAI access with deployed models:
  - `gpt-4.1-mini` (LLM)
  - `text-embedding-3-large` (embeddings)

## Setup

### 1. Start the database

```bash
docker compose up -d
```

This launches a PostgreSQL instance with the pgvector extension on port 5432.

### 2. Configure environment variables

Create a `.env` file in the project root:

```env
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
OPENAI_API_VERSION=2024-02-01

# Database (defaults shown — override if needed)
POSTGRES_USER=admin
POSTGRES_PASSWORD=password
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=parking
```

Azure authentication uses `DefaultAzureCredential` (e.g., Azure CLI login, managed identity, or environment variables).

### 3. Install dependencies

```bash
uv sync
```

### 4. Run the server

```bash
uv run uvicorn main:app --reload
```

The API will be available at `http://localhost:8000`. On first startup, the knowledge base from `db/parking_data.json` is automatically embedded and seeded into the vector store.

## API Usage

### `POST /chat`

Send a message and receive a response from the parking assistant.

**Request:**

```json
{
  "session_id": "user-123",
  "message": "What are your parking rates?"
}
```

**Response:**

```json
{
  "answer": "CityPark Central offers hourly rates starting at..."
}
```

Use the same `session_id` across requests to maintain conversation context (e.g., for multi-step reservation booking).

## Project Structure

```
.
├── main.py                  # FastAPI app, /chat endpoint, LangGraph agent setup
├── config.py                # Pydantic Settings (Azure OpenAI config from .env)
├── guardrails.py            # PII redaction using Presidio
├── db/
│   ├── database.py          # PostgreSQL connection, schema init, booking CRUD
│   └── parking_data.json    # RAG knowledge base (parking info documents)
├── evaluation/
│   ├── eval_dataset.json    # Question/ground-truth pairs for RAG evaluation
│   ├── rag_evaluation.py    # RAGAS evaluation pipeline
│   └── eval_results.json    # Evaluation output
├── docker-compose.yml       # PostgreSQL + pgvector container
└── pyproject.toml           # Project metadata and dependencies (uv)
```

## RAG Evaluation

Run the offline evaluation pipeline to measure retrieval and generation quality:

```bash
uv run python -m evaluation.rag_evaluation
```

This evaluates the system against `evaluation/eval_dataset.json` using four RAGAS metrics:

- **Context Recall** — how much of the ground truth is covered by retrieved context
- **Context Precision** — relevance of retrieved documents to the question
- **Faithfulness** — whether the response is grounded in the retrieved context
- **Response Relevancy** — how relevant the response is to the user's question

Results are printed to the console and saved to `evaluation/eval_results.json`.

## Architecture

```
User → POST /chat → FastAPI
                       │
                       ├─ Similarity search (k=3) against pgvector
                       │
                       ├─ LangGraph agent with:
                       │    ├─ System prompt + RAG context
                       │    ├─ book_parking tool
                       │    └─ InMemorySaver (session state)
                       │
                       ├─ PII redaction (Presidio)
                       │
                       └─ Response → User
```