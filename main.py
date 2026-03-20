from contextlib import asynccontextmanager

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langchain.embeddings import init_embeddings
from langchain_postgres import PGVector
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import BaseModel
from starlette.requests import Request

from config import settings
from db.database import (
    CONNECTION_STRING,
    init_db,
    load_seed_data,
    create_booking,
    get_bookings_by_session,
    get_pending_bookings,
    update_booking_status,
)
from guardrails import redact_pii


class ChatRequest(BaseModel):
    session_id: str
    message: str


class AdminChatRequest(BaseModel):
    message: str


class BookingActionRequest(BaseModel):
    admin_notes: str = ""


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
    app.state.admin_checkpointer = InMemorySaver()
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/chat")
def chat(request: Request, body: ChatRequest):
    answer, context = invoke(
        message=body.message,
        session_id=body.session_id,
        vectorstore=request.app.state.vectorstore,
        llm=request.app.state.llm,
        checkpointer=request.app.state.checkpointer,
    )

    return {"answer": answer}


def invoke(
        message,
        session_id,
        vectorstore,
        llm,
        checkpointer=None
) -> tuple[str, list[str]]:
    docs = vectorstore.similarity_search(message, k=3)
    context = [doc.page_content for doc in docs]

    @tool
    def book_parking(
            first_name: str,
            last_name: str,
            license_plate: str,
            arrival_time: str,
            departure_time: str,
    ) -> dict:
        """Collect and save a parking reservation for admin approval.
        Call this tool only when all five fields have been provided by the user.
        The reservation will be submitted for administrator approval before being confirmed.

        Args:
            first_name: Customer first name
            last_name: Customer last name
            license_plate: Vehicle license plate number
            arrival_time: Arrival datetime in ISO-8601 format, e.g. 2026-03-18T09:00:00
            departure_time: Departure datetime in ISO-8601 format, e.g. 2026-03-18T17:00:00
        """
        return create_booking(
            session_id=session_id,
            first_name=first_name,
            last_name=last_name,
            license_plate=license_plate,
            arrival_time=arrival_time,
            departure_time=departure_time,
        )

    @tool
    def check_booking_status() -> list[dict]:
        """Check the status of parking reservations for the current session.
        Use this when the user asks about the status of their booking(s)."""
        return get_bookings_by_session(session_id)

    agent = create_agent(
        model=llm,
        tools=[book_parking, check_booking_status],
        checkpointer=checkpointer,
        system_prompt=(
            "You are a helpful parking lot assistant. "
            "Answer questions based only on the context below.\n\n"
            "When a user wants to make a reservation, collect the following details one by one: "
            "first name, last name, license plate number, arrival time, and departure time. "
            "Once you have ALL five pieces of information, call the book_parking tool.\n\n"
            "After booking, inform the user that their reservation has been submitted for "
            "administrator approval and is not yet confirmed.\n\n"
            "When the user asks about their booking status, use the check_booking_status tool "
            "and report the current status of each booking.\n\n"
            f"Context:\n{"\n\n".join(context)}"
        )
    )

    response = agent.invoke(
        {"messages": [{"role": "user", "content": message}]},
        {"configurable": {"thread_id": session_id}}
    )

    last_message = response["messages"][-1]
    answer = redact_pii(last_message.content)
    return answer, context


@app.get("/admin/bookings/pending")
def admin_pending_bookings():
    bookings = get_pending_bookings()
    for b in bookings:
        for key, val in b.items():
            if hasattr(val, "isoformat"):
                b[key] = val.isoformat()
    return {"bookings": bookings}


@app.post("/admin/bookings/{booking_id}/approve")
def admin_approve_booking(booking_id: int, body: BookingActionRequest):
    result = update_booking_status(booking_id, "confirmed", body.admin_notes)
    if result is None:
        raise HTTPException(status_code=404, detail="Booking not found or already processed")
    return result


@app.post("/admin/bookings/{booking_id}/refuse")
def admin_refuse_booking(booking_id: int, body: BookingActionRequest):
    result = update_booking_status(booking_id, "refused", body.admin_notes)
    if result is None:
        raise HTTPException(status_code=404, detail="Booking not found or already processed")
    return result


@app.post("/admin/chat")
def admin_chat(request: Request, body: AdminChatRequest):
    answer = invoke_admin(
        message=body.message,
        llm=request.app.state.llm,
        checkpointer=request.app.state.admin_checkpointer,
    )
    return {"answer": answer}


def invoke_admin(message: str, llm, checkpointer) -> str:
    @tool
    def list_pending_bookings() -> list[dict]:
        """List all parking reservations that are pending admin approval."""
        return get_pending_bookings()

    @tool
    def approve_booking(booking_id: int, notes: str = "") -> dict | str:
        """Approve a pending parking reservation.

        Args:
            booking_id: The ID of the booking to approve
            notes: Optional admin notes
        """
        result = update_booking_status(booking_id, "confirmed", notes)
        if result is None:
            return f"Booking {booking_id} not found or already processed."
        return result

    @tool
    def reject_booking(booking_id: int, notes: str = "") -> dict | str:
        """Reject/refuse a pending parking reservation.

        Args:
            booking_id: The ID of the booking to reject
            notes: Optional admin notes explaining the reason for rejection
        """
        result = update_booking_status(booking_id, "refused", notes)
        if result is None:
            return f"Booking {booking_id} not found or already processed."
        return result

    agent = create_agent(
        model=llm,
        tools=[list_pending_bookings, approve_booking, reject_booking],
        checkpointer=checkpointer,
        system_prompt=(
            "You are an admin assistant for CityPark Central parking lot. "
            "You help administrators review and manage parking reservation requests.\n\n"
            "You can list pending bookings, approve them, or reject them. "
            "When approving or rejecting, always confirm the action to the admin."
        ),
    )

    response = agent.invoke(
        {"messages": [{"role": "user", "content": message}]},
        {"configurable": {"thread_id": "admin"}},
    )

    return response["messages"][-1].content
