from contextlib import asynccontextmanager

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from fastapi import FastAPI, Request
from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langchain.embeddings import init_embeddings
from langchain_postgres import PGVector
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import BaseModel

from config import settings
from db.database import CONNECTION_STRING, init_db, load_seed_data, create_booking


class ChatRequest(BaseModel):
    session_id: str
    message: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    token_provider = get_bearer_token_provider(
        DefaultAzureCredential(),
        settings.azure_openai_scope
    )
    app.state.llm = init_chat_model(
        settings.llm_model,
        azure_ad_token_provider=token_provider
    )
    app.state.embedding = init_embeddings(
        settings.embedding_model,
        azure_ad_token_provider=token_provider
    )
    app.state.checkpointer = InMemorySaver()
    init_db()

    vectorstore = PGVector(
        embeddings=app.state.embedding,
        collection_name="park_info_docs",
        connection=CONNECTION_STRING,
        create_extension=False,
    )

    if not vectorstore.similarity_search("", k=1):
        texts, metadatas = load_seed_data()
        vectorstore.add_texts(texts, metadatas=metadatas)

    app.state.vectorstore = vectorstore

    yield


app = FastAPI(lifespan=lifespan)


@app.post("/chat")
async def chat(request: Request, body: ChatRequest):
    docs = request.app.state.vectorstore.similarity_search(body.message, k=3)
    context = "\n\n".join(doc.page_content for doc in docs)

    @tool
    def book_parking(
            first_name: str,
            last_name: str,
            license_plate: str,
            arrival_time: str,
            departure_time: str,
    ) -> dict:
        """Collect and save a parking reservation. Call this tool only when all five fields have been provided by the user.

        Args:
            first_name: Customer first name
            last_name: Customer last name
            license_plate: Vehicle license plate number
            arrival_time: Arrival datetime in ISO-8601 format, e.g. 2026-03-18T09:00:00
            departure_time: Departure datetime in ISO-8601 format, e.g. 2026-03-18T17:00:00
        """
        return create_booking(
            session_id=body.session_id,
            first_name=first_name,
            last_name=last_name,
            license_plate=license_plate,
            arrival_time=arrival_time,
            departure_time=departure_time,
        )

    agent = create_agent(
        model=request.app.state.llm,
        tools=[book_parking],
        checkpointer=request.app.state.checkpointer,
        system_prompt=(
            "You are a helpful parking lot assistant. "
            "Answer questions based only on the context below.\n\n"
            "When a user wants to make a reservation, collect the following details one by one: "
            "first name, last name, license plate number, arrival time, and departure time. "
            "Once you have ALL five pieces of information, call the book_parking tool.\n\n"
            f"Context:\n{context}"
        )
    )

    response = agent.invoke(
        {"messages": [{"role": "user", "content": body.message}]},
        {"configurable": {"thread_id": body.session_id}}
    )

    last_message = response["messages"][-1]

    return {"answer": last_message.content}