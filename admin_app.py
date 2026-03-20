import streamlit as st
import requests

from config import settings

st.set_page_config(page_title="CityPark Admin", layout="wide")
st.title("CityPark Central — Admin Dashboard")

if "admin_messages" not in st.session_state:
    st.session_state.admin_messages = []

st.sidebar.header("Pending Bookings")

if st.sidebar.button("Refresh"):
    st.rerun()

try:
    resp = requests.get(f"{settings.api_base}/admin/bookings/pending", timeout=5)
    resp.raise_for_status()
    pending = resp.json().get("bookings", [])
except requests.RequestException:
    st.sidebar.error("Could not connect to the API server.")
    pending = []

if not pending:
    st.sidebar.info("No pending bookings.")

for booking in pending:
    bid = booking["id"]
    with st.sidebar.expander(
        f"#{bid} — {booking['first_name']} {booking['last_name']}"
    ):
        st.write(f"**Plate:** {booking['license_plate']}")
        st.write(f"**Arrival:** {booking['arrival_time']}")
        st.write(f"**Departure:** {booking['departure_time']}")
        st.write(f"**Created:** {booking['created_at']}")

        notes = st.text_input("Admin notes", key=f"notes_{bid}")
        col1, col2 = st.columns(2)

        with col1:
            if st.button("Approve", key=f"approve_{bid}"):
                r = requests.post(
                    f"{settings.api_base}/admin/bookings/{bid}/approve",
                    json={"admin_notes": notes},
                    timeout=5,
                )
                if r.ok:
                    st.success(f"Booking #{bid} approved.")
                    st.rerun()
                else:
                    st.error(r.json().get("detail", "Error"))

        with col2:
            if st.button("Refuse", key=f"refuse_{bid}"):
                r = requests.post(
                    f"{settings.api_base}/admin/bookings/{bid}/refuse",
                    json={"admin_notes": notes},
                    timeout=5,
                )
                if r.ok:
                    st.success(f"Booking #{bid} refused.")
                    st.rerun()
                else:
                    st.error(r.json().get("detail", "Error"))


st.subheader("Admin Agent Chat")
st.caption(
    'Talk to the admin agent — e.g. "show pending bookings", '
    '"approve booking 5", "reject booking 3 reason: invalid plate"'
)

for msg in st.session_state.admin_messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if prompt := st.chat_input("Message the admin agent..."):
    st.session_state.admin_messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                r = requests.post(
                    f"{settings.api_base}/admin/chat",
                    json={"message": prompt},
                    timeout=30,
                )
                r.raise_for_status()
                answer = r.json()["answer"]
            except requests.RequestException as e:
                answer = f"Error communicating with the API: {e}"

        st.markdown(answer)

    st.session_state.admin_messages.append({"role": "assistant", "content": answer})
    st.rerun()
