from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
import os
from dotenv import load_dotenv
from openai import OpenAI

from database import create_tables, get_db, Thread, Message

load_dotenv()

app = FastAPI(title="Mini AI Chat API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── LLM client setup ──────────────────────────────────────────────────────────
# Supports OpenAI, Groq (OpenAI-compatible), or Gemini via openai-compat layer.
# Set PROVIDER=openai | groq | gemini in your .env

PROVIDER    = os.getenv("PROVIDER", "groq").lower()
API_KEY     = os.getenv("API_KEY", "")
MODEL_NAME  = os.getenv("MODEL_NAME", "")

if PROVIDER == "groq":
    client     = OpenAI(api_key=API_KEY, base_url="https://api.groq.com/openai/v1")
    MODEL_NAME = MODEL_NAME or "llama3-8b-8192"
elif PROVIDER == "gemini":
    client     = OpenAI(api_key=API_KEY, base_url="https://generativelanguage.googleapis.com/v1beta/openai/")
    MODEL_NAME = MODEL_NAME or "gemini-1.5-flash"
else:  # openai
    client     = OpenAI(api_key=API_KEY)
    MODEL_NAME = MODEL_NAME or "gpt-3.5-turbo"

# ── DB init ───────────────────────────────────────────────────────────────────
create_tables()


# ── Pydantic schemas ──────────────────────────────────────────────────────────
class ThreadCreate(BaseModel):
    title: str = "New Thread"

class ThreadOut(BaseModel):
    id: int
    title: str
    class Config:
        from_attributes = True

class MessageOut(BaseModel):
    id: int
    thread_id: int
    role: str
    content: str
    class Config:
        from_attributes = True

class ChatRequest(BaseModel):
    thread_id: int
    user_message: str


# ── Helpers ───────────────────────────────────────────────────────────────────
def _build_universal_context(db: Session, current_thread_id: int) -> str:
    """
    Gather a compact summary of ALL past threads (excluding the current one)
    so the AI has universal memory across threads.
    """
    threads = db.query(Thread).filter(Thread.id != current_thread_id).all()
    if not threads:
        return ""

    parts = ["=== Past conversation context from other threads ==="]
    for t in threads:
        msgs = (
            db.query(Message)
            .filter(Message.thread_id == t.id)
            .order_by(Message.created_at)
            .all()
        )
        if not msgs:
            continue
        parts.append(f"\n[Thread: {t.title}]")
        for m in msgs:
            parts.append(f"  {m.role.upper()}: {m.content}")
    parts.append("=== End of past context ===\n")
    return "\n".join(parts)


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"message": "Mini AI Chat API is running 🚀"}


# -- Threads --
@app.post("/threads", response_model=ThreadOut)
def create_thread(data: ThreadCreate, db: Session = Depends(get_db)):
    thread = Thread(title=data.title)
    db.add(thread)
    db.commit()
    db.refresh(thread)
    return thread


@app.get("/threads", response_model=List[ThreadOut])
def list_threads(db: Session = Depends(get_db)):
    return db.query(Thread).order_by(Thread.created_at.desc()).all()


@app.delete("/threads/{thread_id}")
def delete_thread(thread_id: int, db: Session = Depends(get_db)):
    thread = db.query(Thread).filter(Thread.id == thread_id).first()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    db.delete(thread)
    db.commit()
    return {"detail": "Thread deleted"}


# -- Messages --
@app.get("/threads/{thread_id}/messages", response_model=List[MessageOut])
def get_messages(thread_id: int, db: Session = Depends(get_db)):
    thread = db.query(Thread).filter(Thread.id == thread_id).first()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    return (
        db.query(Message)
        .filter(Message.thread_id == thread_id)
        .order_by(Message.created_at)
        .all()
    )


@app.post("/chat", response_model=MessageOut)
def chat(req: ChatRequest, db: Session = Depends(get_db)):
    thread = db.query(Thread).filter(Thread.id == req.thread_id).first()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    # Save user message
    user_msg = Message(thread_id=req.thread_id, role="user", content=req.user_message)
    db.add(user_msg)
    db.commit()

    # Auto-title the thread from the first message
    if thread.title == "New Thread":
        thread.title = req.user_message[:60]
        db.commit()

    # Build message history for this thread
    history = (
        db.query(Message)
        .filter(Message.thread_id == req.thread_id)
        .order_by(Message.created_at)
        .all()
    )

    # Universal memory context injected as a system message
    universal_ctx = _build_universal_context(db, req.thread_id)
    system_prompt = (
        "You are a helpful AI assistant with memory across all conversation threads. "
        "When relevant, use the past context provided to give coherent answers.\n\n"
        + universal_ctx
    )

    llm_messages = [{"role": "system", "content": system_prompt}]
    for m in history:
        llm_messages.append({"role": m.role, "content": m.content})

    # Call LLM
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=llm_messages,
            max_tokens=1024,
        )
        ai_text = response.choices[0].message.content
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM error: {str(e)}")

    # Save assistant reply
    ai_msg = Message(thread_id=req.thread_id, role="assistant", content=ai_text)
    db.add(ai_msg)
    db.commit()
    db.refresh(ai_msg)
    return ai_msg