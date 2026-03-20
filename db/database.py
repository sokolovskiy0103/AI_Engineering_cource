import json
import os
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

load_dotenv()

DB_USER = os.getenv("POSTGRES_USER", "admin")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "password")
DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")
DB_NAME = os.getenv("POSTGRES_DB", "parking")

CONNECTION_STRING = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

SEED_FILE = Path(__file__).parent / "parking_data.json"


def get_connection():
    return psycopg2.connect(
        f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    )


def init_db():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS bookings (
                    id SERIAL PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    first_name TEXT,
                    last_name TEXT,
                    license_plate TEXT,
                    arrival_time TIMESTAMP,
                    departure_time TIMESTAMP,
                    status TEXT DEFAULT 'pending_approval',
                    admin_notes TEXT,
                    created_at TIMESTAMP DEFAULT NOW()
                );
            """)
            cur.execute(
                "ALTER TABLE bookings ADD COLUMN IF NOT EXISTS admin_notes TEXT;"
            )
        conn.commit()
    finally:
        conn.close()


def load_seed_data():
    with open(SEED_FILE, encoding="utf-8") as f:
        data = json.load(f)
    docs = data.get("park_info_docs", [])
    return (
        [doc["content"] for doc in docs],
        [doc.get("metadata", {}) for doc in docs],
    )


def create_booking(
    session_id: str,
    first_name: str,
    last_name: str,
    license_plate: str,
    arrival_time: str,
    departure_time: str,
) -> dict:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO bookings
                    (session_id, first_name, last_name, license_plate,
                     arrival_time, departure_time, status)
                VALUES (%s, %s, %s, %s, %s, %s, 'pending_approval')
                RETURNING id, status;
                """,
                (session_id, first_name, last_name, license_plate,
                 arrival_time, departure_time),
            )
            row = cur.fetchone()
        conn.commit()
        return {"booking_id": row[0], "status": row[1]}
    finally:
        conn.close()


def get_pending_bookings() -> list[dict]:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, session_id, first_name, last_name, license_plate,
                       arrival_time, departure_time, status, created_at
                FROM bookings
                WHERE status = 'pending_approval'
                ORDER BY created_at;
                """
            )
            cols = [desc[0] for desc in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        conn.close()


def get_bookings_by_session(session_id: str) -> list[dict]:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, first_name, last_name, license_plate,
                       arrival_time, departure_time, status, admin_notes, created_at
                FROM bookings
                WHERE session_id = %s
                ORDER BY created_at;
                """,
                (session_id,),
            )
            cols = [desc[0] for desc in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        conn.close()


def update_booking_status(
    booking_id: int, new_status: str, admin_notes: str = ""
) -> dict | None:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE bookings
                SET status = %s, admin_notes = %s
                WHERE id = %s AND status = 'pending_approval'
                RETURNING id, status, admin_notes;
                """,
                (new_status, admin_notes, booking_id),
            )
            row = cur.fetchone()
        conn.commit()
        if row is None:
            return None
        return {"booking_id": row[0], "status": row[1], "admin_notes": row[2]}
    finally:
        conn.close()
