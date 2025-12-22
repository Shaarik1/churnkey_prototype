from fastapi import FastAPI, HTTPException, Request, Depends, status, Response
from fastapi.staticfiles import StaticFiles 
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import stripe
import sqlite3
import datetime

# --- CONFIGURATION ---
stripe.api_key = "sk_test_..." # PASTE YOUR KEY HERE
COMMISSION_RATE = 0.20 
DB_FILE = "churnkey.db"
SESSION_TOKEN = "secret_session_token_xyz"

app = FastAPI()

# --- DATABASE ENGINE ---
def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS saves (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id TEXT NOT NULL,
            offer_type TEXT,
            saved_amount REAL,
            status TEXT,
            date TEXT
        )
    ''')
    # UPGRADED TABLE: NOW STORES CUSTOM TEXT
    conn.execute('''
        CREATE TABLE IF NOT EXISTS offers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL,
            trigger_rule TEXT,
            offer_type TEXT,
            offer_value INTEGER,
            offer_title TEXT,
            offer_body TEXT,
            coupon_code TEXT,
            is_active INTEGER DEFAULT 1
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password TEXT NOT NULL
        )
    ''')
    try:
        conn.execute("INSERT INTO users (username, password) VALUES (?, ?)", ("admin", "password123"))
        conn.commit()
    except: pass
    conn.commit()
    conn.close()

init_db()

# --- MODELS ---
class LoginRequest(BaseModel):
    username: str
    password: str

class OfferRequest(BaseModel):
    project_id: str
    trigger: str
    type: str
    value: int
    title: str  # NEW
    body: str   # NEW
    code: str

# --- AUTH ---
def get_current_user(request: Request):
    token = request.cookies.get("session_token")
    if not token: raise HTTPException(status_code=401, detail="Unauthorized")
    # In a real app, map token to user. For now, we return a placeholder or handle in frontend.
    return "admin" 

# --- ROUTES ---
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.get("/")
async def read_landing(): return FileResponse('static/index.html')
@app.get("/demo")
async def read_demo(): return FileResponse('static/demo.html')
@app.get("/login")
async def login_page(): return FileResponse('static/login.html')
@app.get("/signup")
async def signup_page(): return FileResponse('static/signup.html')

@app.post("/api/signup")
async def api_signup(creds: LoginRequest):
    conn = get_db_connection()
    try:
        conn.execute("INSERT INTO users (username, password) VALUES (?, ?)", (creds.username, creds.password))
        conn.commit()
    except: raise HTTPException(status_code=400, detail="User exists")
    conn.close()
    return {"status": "success"}

@app.post("/api/login")
async def api_login(response: Response, creds: LoginRequest):
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE username = ? AND password = ?", (creds.username, creds.password)).fetchone()
    conn.close()
    if user:
        response.set_cookie(key="session_token", value=SESSION_TOKEN, httponly=True)
        return {"status": "success"}
    raise HTTPException(status_code=401)

@app.get("/logout")
async def logout(response: Response):
    response = RedirectResponse(url="/login")
    response.delete_cookie("session_token")
    return response

# --- DASHBOARD PAGES ---
@app.get("/dashboard")
async def read_dashboard(request: Request):
    try:
        get_current_user(request)
        return FileResponse('static/dashboard.html')
    except: return RedirectResponse(url="/login")

@app.get("/settings")
async def read_settings(request: Request):
    try:
        get_current_user(request)
        return FileResponse('static/settings.html')
    except: return RedirectResponse(url="/login")

@app.get("/setup")
async def read_setup(request: Request):
    try:
        get_current_user(request)
        return FileResponse('static/setup.html')
    except: return RedirectResponse(url="/login")

# --- API ---
@app.get("/dashboard-stats")
async def get_dashboard_stats(request: Request, month: str = None, user: str = Depends(get_current_user)):
    conn = get_db_connection()
    query = "SELECT * FROM saves"
    params = []
    if month:
        query += " WHERE date LIKE ?"
        params.append(f"{month}%")
    saves = conn.execute(query, params).fetchall()
    conn.close()
    
    total_saved = 0
    total_commission = 0
    verified = 0
    pending = 0
    activity = []
    for s in saves:
        item = dict(s)
        activity.append(item)
        if item['status'] == 'verified':
            total_saved += item['saved_amount']
            total_commission += (item['saved_amount'] * COMMISSION_RATE)
            verified += 1
        else: pending += 1
    return {"total_revenue_saved": total_saved, "your_commission": total_commission, "verified_deals": verified, "pending_deals": pending, "recent_activity": activity[::-1]}

@app.post("/api/create-offer")
async def create_offer(offer: OfferRequest, user: str = Depends(get_current_user)):
    conn = get_db_connection()
    existing = conn.execute("SELECT id FROM offers WHERE project_id = ? AND trigger_rule = ?", (offer.project_id, offer.trigger)).fetchone()
    if existing:
        conn.execute("UPDATE offers SET offer_type=?, offer_value=?, offer_title=?, offer_body=?, coupon_code=?, is_active=1 WHERE id=?", 
                     (offer.type, offer.value, offer.title, offer.body, offer.code, existing['id']))
    else:
        conn.execute("INSERT INTO offers (project_id, trigger_rule, offer_type, offer_value, offer_title, offer_body, coupon_code, is_active) VALUES (?, ?, ?, ?, ?, ?, ?, 1)", 
                     (offer.project_id, offer.trigger, offer.type, offer.value, offer.title, offer.body, offer.code))
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.get("/api/get-offer")
async def get_offer(project_id: str, reason: str):
    conn = get_db_connection()
    offer = conn.execute("SELECT * FROM offers WHERE project_id = ? AND trigger_rule = ?", (project_id, reason)).fetchone()
    if not offer:
        offer = conn.execute("SELECT * FROM offers WHERE project_id = ? AND trigger_rule = 'default'", (project_id,)).fetchone()
    conn.close()
    if offer: return dict(offer)
    else: return {"offer_type": "pause", "offer_value": 1, "offer_title": "Wait!", "offer_body": "Don't go yet."}

@app.post("/accept-offer")
async def accept_offer(customer_id: str, offer_type: str):
    conn = get_db_connection()
    conn.execute("INSERT INTO saves (customer_id, offer_type, saved_amount, status, date) VALUES (?, ?, 50.0, 'pending', ?)", (customer_id, offer_type, datetime.datetime.now().isoformat()))
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.post("/webhook")
async def stripe_webhook(request: Request):
    payload = await request.json()
    if payload.get('type') == 'invoice.payment_succeeded':
        customer_id = payload['data']['object']['customer']
        conn = get_db_connection()
        conn.execute("UPDATE saves SET status = 'verified' WHERE customer_id = ? AND status = 'pending'", (customer_id,))
        conn.commit()
    return {"status": "success"}

app.mount("/static", StaticFiles(directory="static"), name="static")