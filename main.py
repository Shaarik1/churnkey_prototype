import os
import datetime
from fastapi import FastAPI, HTTPException, Request, Depends, status, Response
from fastapi.staticfiles import StaticFiles 
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import stripe
import psycopg2
from psycopg2.extras import RealDictCursor

# --- CONFIGURATION ---
# We now get the DB URL from Render's Environment Variables
DATABASE_URL = os.environ.get("DATABASE_URL") 
stripe.api_key = "sk_test_..." # PASTE YOUR REAL STRIPE KEY HERE
COMMISSION_RATE = 0.20 
SESSION_TOKEN = "secret_session_token_xyz"

app = FastAPI()

# --- DATABASE ENGINE (POSTGRES) ---
def get_db_connection():
    # Connect to the external Postgres server
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    return conn

def init_db():
    if not DATABASE_URL:
        print("Waiting for DATABASE_URL...")
        return

    conn = get_db_connection()
    cur = conn.cursor()
    
    # Create Tables (Postgres Syntax)
    cur.execute('''
        CREATE TABLE IF NOT EXISTS saves (
            id SERIAL PRIMARY KEY,
            customer_id TEXT NOT NULL,
            offer_type TEXT,
            saved_amount REAL,
            status TEXT,
            date TEXT
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS offers (
            id SERIAL PRIMARY KEY,
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
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password TEXT NOT NULL
        )
    ''')
    
    # Create Admin User if not exists
    try:
        cur.execute("INSERT INTO users (username, password) VALUES (%s, %s) ON CONFLICT DO NOTHING", ("admin", "password123"))
    except Exception as e:
        print("Admin user setup error:", e)
        
    conn.commit()
    cur.close()
    conn.close()

# Initialize on startup
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
    title: str 
    body: str   
    code: str

# --- AUTH ---
def get_current_user(request: Request):
    token = request.cookies.get("session_token")
    if not token: raise HTTPException(status_code=401, detail="Unauthorized")
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

# --- API ENDPOINTS (Updated for Postgres %s syntax) ---

@app.post("/api/signup")
async def api_signup(creds: LoginRequest):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO users (username, password) VALUES (%s, %s)", (creds.username, creds.password))
        conn.commit()
    except psycopg2.IntegrityError:
        conn.rollback()
        raise HTTPException(status_code=400, detail="User exists")
    finally:
        cur.close()
        conn.close()
    return {"status": "success"}

@app.post("/api/login")
async def api_login(response: Response, creds: LoginRequest):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE username = %s AND password = %s", (creds.username, creds.password))
    user = cur.fetchone()
    cur.close()
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

@app.get("/dashboard-stats")
async def get_dashboard_stats(request: Request, month: str = None, user: str = Depends(get_current_user)):
    conn = get_db_connection()
    cur = conn.cursor()
    query = "SELECT * FROM saves"
    params = []
    if month:
        query += " WHERE date LIKE %s"
        params.append(f"{month}%")
    
    cur.execute(query, tuple(params))
    saves = cur.fetchall()
    cur.close()
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
    cur = conn.cursor()
    
    # Check existing
    cur.execute("SELECT id FROM offers WHERE project_id = %s AND trigger_rule = %s", (offer.project_id, offer.trigger))
    existing = cur.fetchone()
    
    if existing:
        cur.execute("""
            UPDATE offers SET offer_type=%s, offer_value=%s, offer_title=%s, offer_body=%s, coupon_code=%s, is_active=1 
            WHERE id=%s
        """, (offer.type, offer.value, offer.title, offer.body, offer.code, existing['id']))
    else:
        cur.execute("""
            INSERT INTO offers (project_id, trigger_rule, offer_type, offer_value, offer_title, offer_body, coupon_code, is_active) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, 1)
        """, (offer.project_id, offer.trigger, offer.type, offer.value, offer.title, offer.body, offer.code))
    
    conn.commit()
    cur.close()
    conn.close()
    return {"status": "success"}

@app.get("/api/get-offer")
async def get_offer(project_id: str, reason: str):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM offers WHERE project_id = %s AND trigger_rule = %s", (project_id, reason))
    offer = cur.fetchone()
    
    if not offer:
        cur.execute("SELECT * FROM offers WHERE project_id = %s AND trigger_rule = 'default'", (project_id,))
        offer = cur.fetchone()
        
    cur.close()
    conn.close()
    
    if offer: return dict(offer)
    else: return {"offer_type": "pause", "offer_value": 1, "offer_title": "Wait!", "offer_body": "Don't go yet."}

@app.post("/accept-offer")
async def accept_offer(customer_id: str, offer_type: str):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO saves (customer_id, offer_type, saved_amount, status, date) VALUES (%s, %s, 50.0, 'pending', %s)", 
                (customer_id, offer_type, datetime.datetime.now().isoformat()))
    conn.commit()
    cur.close()
    conn.close()
    return {"status": "success"}

@app.post("/webhook")
async def stripe_webhook(request: Request):
    payload = await request.json()
    if payload.get('type') == 'invoice.payment_succeeded':
        customer_id = payload['data']['object']['customer']
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE saves SET status = 'verified' WHERE customer_id = %s AND status = 'pending'", (customer_id,))
        conn.commit()
        cur.close()
        conn.close()
    return {"status": "success"}

@app.get("/api/me")
async def get_my_info(user: str = Depends(get_current_user)):
    return {"username": user}

app.mount("/static", StaticFiles(directory="static"), name="static")