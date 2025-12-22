from fastapi import FastAPI, HTTPException, Request, Depends, status, Response
from fastapi.staticfiles import StaticFiles 
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import stripe
import sqlite3
import datetime
import secrets 

# --- CONFIGURATION ---
stripe.api_key = "sk_test_12345" 
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
    # 1. Saves Table
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
    # 2. Offers Table
    conn.execute('''
        CREATE TABLE IF NOT EXISTS offers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL,
            trigger_rule TEXT,
            offer_type TEXT,
            offer_value INTEGER,
            coupon_code TEXT,
            is_active INTEGER DEFAULT 1
        )
    ''')
    # 3. Users Table (NEW!)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password TEXT NOT NULL
        )
    ''')
    
    # Create default admin if not exists
    try:
        conn.execute("INSERT INTO users (username, password) VALUES (?, ?)", ("admin", "password123"))
        conn.commit()
    except sqlite3.IntegrityError:
        pass # Admin already exists

    conn.commit()
    conn.close()

init_db()

# --- SECURITY LOGIC ---
class AuthRequest(BaseModel):
    username: str
    password: str

def get_current_user(request: Request):
    token = request.cookies.get("session_token")
    if not token:
        raise HTTPException(status_code=401, detail="Unauthorized")
    # In a real app, we would validate the token against a session DB
    # For this demo, we trust the static token
    return "admin" 

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- DATA MODELS ---
class OfferRequest(BaseModel):
    project_id: str
    trigger: str
    type: str
    value: int
    code: str

# --- PAGE ROUTES ---
@app.get("/")
async def read_landing():
    return FileResponse('static/index.html')

@app.get("/demo")
async def read_demo():
    return FileResponse('static/demo.html')

@app.get("/login")
async def login_page():
    return FileResponse('static/login.html')

@app.get("/signup")
async def signup_page():
    return FileResponse('static/signup.html')

# --- AUTH API ---

@app.post("/api/signup")
async def api_signup(creds: AuthRequest):
    conn = get_db_connection()
    try:
        # Try to insert new user
        conn.execute("INSERT INTO users (username, password) VALUES (?, ?)", (creds.username, creds.password))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=400, detail="Username already exists")
    
    conn.close()
    return {"status": "success"}

@app.post("/api/login")
async def api_login(response: Response, creds: AuthRequest):
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE username = ? AND password = ?", (creds.username, creds.password)).fetchone()
    conn.close()

    if user:
        # Set cookie
        response.set_cookie(key="session_token", value=SESSION_TOKEN, httponly=True)
        return {"status": "success"}
    else:
        raise HTTPException(status_code=401, detail="Invalid credentials")

@app.get("/logout")
async def logout(response: Response):
    response = RedirectResponse(url="/login")
    response.delete_cookie("session_token")
    return response


# --- PROTECTED PAGES ---
@app.get("/dashboard")
async def read_dashboard(request: Request):
    try:
        get_current_user(request)
        return FileResponse('static/dashboard.html')
    except HTTPException:
        return RedirectResponse(url="/login")

@app.get("/settings")
async def read_settings(request: Request):
    try:
        get_current_user(request)
        return FileResponse('static/settings.html')
    except HTTPException:
        return RedirectResponse(url="/login")

@app.get("/setup")
async def read_setup(request: Request):
    try:
        get_current_user(request)
        return FileResponse('static/setup.html')
    except HTTPException:
        return RedirectResponse(url="/login")

# --- APP LOGIC ---
@app.get("/dashboard-stats")
async def get_dashboard_stats(request: Request, month: str = None, user: str = Depends(get_current_user)):
    conn = get_db_connection()
    
    # Base query
    query = "SELECT * FROM saves"
    params = []

    # If a month is selected (Format: YYYY-MM), filter by it
    if month:
        query += " WHERE date LIKE ?"
        params.append(f"{month}%")
    
    saves = conn.execute(query, params).fetchall()
    conn.close()
    
    total_saved = 0
    total_commission = 0
    verified_count = 0
    pending_count = 0
    recent_activity = []
    
    for save in saves:
        item = dict(save)
        recent_activity.append(item)
        if item['status'] == 'verified':
            total_saved += item['saved_amount']
            total_commission += (item['saved_amount'] * COMMISSION_RATE)
            verified_count += 1
        else:
            pending_count += 1
            
    recent_activity.reverse()
    return {
        "total_revenue_saved": total_saved,
        "your_commission": total_commission,
        "verified_deals": verified_count,
        "pending_deals": pending_count,
        "recent_activity": recent_activity # No limit, show all for that month
    }

@app.post("/api/create-offer")
async def create_offer(offer: OfferRequest, user: str = Depends(get_current_user)):
    conn = get_db_connection()
    existing = conn.execute("SELECT id FROM offers WHERE project_id = ? AND trigger_rule = ?", (offer.project_id, offer.trigger)).fetchone()

    if existing:
        conn.execute("UPDATE offers SET offer_type=?, offer_value=?, coupon_code=?, is_active=1 WHERE id=?", (offer.type, offer.value, offer.code, existing['id']))
    else:
        conn.execute("INSERT INTO offers (project_id, trigger_rule, offer_type, offer_value, coupon_code, is_active) VALUES (?, ?, ?, ?, ?, 1)", (offer.project_id, offer.trigger, offer.type, offer.value, offer.code))
    
    conn.commit()
    conn.close()
    return {"status": "success", "message": "Custom offer saved!"}

@app.get("/api/get-offer")
async def get_offer(project_id: str, reason: str):
    conn = get_db_connection()
    offer = conn.execute(
        "SELECT * FROM offers WHERE project_id = ? AND trigger_rule = ? AND is_active = 1",
        (project_id, reason)
    ).fetchone()
    
    if not offer:
        offer = conn.execute(
            "SELECT * FROM offers WHERE project_id = ? AND trigger_rule = 'default' AND is_active = 1",
            (project_id,)
        ).fetchone()
    conn.close()
    
    if offer: return dict(offer)
    else: return {"offer_type": "pause", "offer_value": 1}

@app.post("/accept-offer")
async def accept_offer(customer_id: str, offer_type: str):
    plan_amount = 100.00 
    saved_value = plan_amount * 0.50 
    conn = get_db_connection()
    conn.execute(
        "INSERT INTO saves (customer_id, offer_type, saved_amount, status, date) VALUES (?, ?, ?, ?, ?)",
        (customer_id, offer_type, saved_value, 'pending', datetime.datetime.now().isoformat())
    )
    conn.commit()
    conn.close()
    return {"status": "success", "message": "Discount applied!"}

@app.post("/webhook")
async def stripe_webhook(request: Request):
    payload = await request.json()
    if payload.get('type') == 'invoice.payment_succeeded':
        customer_id = payload['data']['object']['customer']
        conn = get_db_connection()
        conn.execute("UPDATE saves SET status = 'verified' WHERE customer_id = ? AND status = 'pending'", (customer_id,))
        conn.commit()
        conn.close()
    return {"status": "success"}

app.mount("/static", StaticFiles(directory="static"), name="static")