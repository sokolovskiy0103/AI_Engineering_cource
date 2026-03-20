# CityPark Central - Parking Lot Assistant

An AI-powered chatbot for **CityPark Central** that answers questions about the parking facility and books reservations through a conversational interface, with an admin approval workflow.

Built with FastAPI, LangGraph agents, Azure OpenAI, PostgreSQL with pgvector for RAG-based context retrieval, and Streamlit dashboards.

## Features

- **Conversational Q&A** — answers questions about parking rates, hours, policies, and facilities using RAG over a knowledge base
- **Reservation booking with admin approval** — collects customer details through multi-turn conversation, submits reservations for administrator review before confirmation
- **Admin dashboard** — Streamlit app for reviewing, approving, or refusing pending reservations via UI buttons or an admin chat agent
- **User chat app** — Streamlit interface for end users to chat with the parking assistant
- **Booking status checks** — users can ask the assistant about the current status of their reservations
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

### 5. Run the Streamlit apps

```bash
# Admin dashboard (port 8501)
uv run streamlit run admin_app.py

# User chat app (port 8502)
uv run streamlit run user_app.py --server.port 8502
```

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

### Admin Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/admin/bookings/pending` | GET | List all bookings awaiting approval |
| `/admin/bookings/{id}/approve` | POST | Approve a pending booking |
| `/admin/bookings/{id}/refuse` | POST | Refuse a pending booking |
| `/admin/chat` | POST | Chat with the admin agent |

Approve/refuse endpoints accept an optional `admin_notes` field in the request body.

## Booking Approval Workflow

```
User → Agent collects 5 fields → book_parking (status='pending_approval')
  → User told "submitted for admin approval"
  → User can ask "what's my booking status?" via check_booking_status tool

Admin → Streamlit dashboard → Sees pending bookings (sidebar buttons + chat)
  → Approves or refuses → DB updated to 'confirmed' or 'refused'
```

## Project Structure

```
.
├── main.py                  # FastAPI app, /chat endpoint, admin endpoints, agents
├── config.py                # Pydantic Settings (Azure OpenAI config from .env)
├── guardrails.py            # PII redaction using Presidio
├── admin_app.py             # Streamlit admin dashboard (Agent 2 + booking buttons)
├── user_app.py              # Streamlit user chat interface
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
User App (Streamlit :8502)
  │
  └─► POST /chat → FastAPI (:8000)
                       │
                       ├─ Similarity search (k=3) against pgvector
                       ├─ LangGraph Agent 1:
                       │    ├─ System prompt + RAG context
                       │    ├─ book_parking tool → DB (status='pending_approval')
                       │    ├─ check_booking_status tool
                       │    └─ InMemorySaver (session state)
                       ├─ PII redaction (Presidio)
                       └─ Response → User

Admin Dashboard (Streamlit :8501)
  │
  ├─► GET/POST /admin/* → Direct booking management
  └─► POST /admin/chat → LangGraph Agent 2:
                            ├─ list_pending_bookings tool
                            ├─ approve_booking tool → DB (status='confirmed')
                            └─ reject_booking tool → DB (status='refused')
```
