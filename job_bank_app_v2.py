"""
Higher Logic Job Bank API - v2
Backend application built with FastAPI and SQLite for zero-cost deployment.
Customized with fields requested by user:
- Member Verification (Is Member / Member ID)
- Job Title
- Company Name
- Salary Range
- Job Post Link
"""

from fastapi import FastAPI, HTTPException, Header, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
import sqlite3
import os
from datetime import datetime, timedelta

DB_FILE = "job_bank.db"
DEFAULT_ADMIN_KEY = os.getenv("ADMIN_KEY", "AdminPass2026")

app = FastAPI(
    title="Higher Logic Job Bank API",
    description="Backend service for customized job submissions and public listings.",
    version="2.0.0"
)

# CORS configuration for Higher Logic frontend embeds
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            is_member TEXT NOT NULL,
            member_id TEXT,
            title TEXT NOT NULL,
            company_name TEXT NOT NULL,
            salary_range TEXT,
            job_post_link TEXT NOT NULL,
            contact_email TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

init_db()

class JobSubmission(BaseModel):
    is_member: str = Field(..., description="'Yes' for Member, 'No' for Non-Member")
    member_id: Optional[str] = Field(None, description="Member ID if applicable")
    title: str = Field(..., min_length=2, max_length=150, description="Job Title")
    company_name: str = Field(..., min_length=2, max_length=150, description="Company / Organization Name")
    salary_range: Optional[str] = Field(None, description="Salary Range (e.g. $60,000 - $75,000 or DOE)")
    job_post_link: str = Field(..., description="URL to the full job posting")
    contact_email: EmailStr = Field(..., description="Contact Email for submission confirmation/questions")

class JobStatusUpdate(BaseModel):
    status: str

def verify_admin(x_admin_token: Optional[str] = Header(None)):
    if x_admin_token != DEFAULT_ADMIN_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return True

@app.get("/")
def status_check():
    return {"status": "online", "service": "Job Bank Backend v2", "custom_fields": True}

@app.get("/api/jobs")
def list_approved_jobs(search: Optional[str] = Query(None)):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    query = "SELECT id, is_member, title, company_name, salary_range, job_post_link, created_at FROM jobs WHERE status = 'approved'"
    params = []

    if search:
        query += " AND (title LIKE ? OR company_name LIKE ?)"
        term = f"%{search}%"
        params.extend([term, term])

    query += " ORDER BY created_at DESC"
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    
    return {"jobs": [dict(r) for r in rows]}

@app.get("/api/jobs/{job_id}")
def get_job_detail(job_id: int):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT id, is_member, title, company_name, salary_range, job_post_link, created_at FROM jobs WHERE id = ? AND status = 'approved'", (job_id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    return dict(row)

@app.post("/api/jobs/submit", status_code=201)
def submit_job(job: JobSubmission):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    expires = (datetime.now() + timedelta(days=60)).strftime("%Y-%m-%d %H:%M:%S")
    
    cursor.execute("""
        INSERT INTO jobs (is_member, member_id, title, company_name, salary_range, job_post_link, contact_email, status, expires_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)
    """, (
        job.is_member, job.member_id, job.title, job.company_name,
        job.salary_range, str(job.job_post_link), job.contact_email, expires
    ))
    
    job_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return {"message": "Job submission received for admin review", "job_id": job_id}

@app.get("/api/admin/jobs", dependencies=[Depends(verify_admin)])
def admin_list_jobs(status_filter: Optional[str] = Query(None)):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    if status_filter:
        cursor.execute("SELECT * FROM jobs WHERE status = ? ORDER BY created_at DESC", (status_filter,))
    else:
        cursor.execute("SELECT * FROM jobs ORDER BY created_at DESC")
        
    rows = cursor.fetchall()
    conn.close()
    return {"jobs": [dict(r) for r in rows]}

@app.post("/api/admin/jobs/{job_id}/status", dependencies=[Depends(verify_admin)])
def admin_set_status(job_id: int, payload: JobStatusUpdate):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE jobs SET status = ? WHERE id = ?", (payload.status, job_id))
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    
    if affected == 0:
        raise HTTPException(status_code=404, detail="Job ID not found")
        
    return {"message": f"Job status updated to {payload.status}"}

@app.delete("/api/admin/jobs/{job_id}", dependencies=[Depends(verify_admin)])
def admin_delete_job(job_id: int):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    
    if affected == 0:
        raise HTTPException(status_code=404, detail="Job ID not found")
        
    return {"message": f"Job #{job_id} deleted"}
