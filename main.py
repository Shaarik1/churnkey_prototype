from fastapi import FastAPI, HTTPException, Request, Depends, status
from fastapi.staticfiles import StaticFiles 
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBasic, HTTPBasicCredentials # <--- NEW IMPORTS
from pydantic import BaseModel
import stripe
import sqlite3
import datetime
import secrets # Used to compare passwords safely

# --- CONFIGURATION ---
stripe.api_key = "sk_test_12345" 
COMMISSION_RATE = 0.20 
DB_FILE = "churnkey.db"

# --- ADMIN CREDENTIALS (CHANGE THESE!) ---
ADMIN_USER = "admin"
ADMIN_PASSWORD = "password123"

app = FastAPI()
security = HTTPBasic() # This handles the browser popup

# --- SECURITY LOGIC ---
def get_current_username(credentials: HTTPBasicCredentials = Depends(security)):
    """
    Checks if the user typed the correct username/password.
    """
    correct_user = secrets.compare_digest(credentials.username, ADMIN_USER)
    correct_password = secrets.compare_digest(credentials.password, ADMIN_PASSWORD)
    
    if not (correct_user and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
    conn.commit()
    conn.close()

init_db()

# --- DATA MODELS ---
class OfferRequest(BaseModel):
    project_id: str
    trigger: str
    type: str
    value: int
    code: str

# --- PUBLIC ENDPOINTS (No Login Required) ---
# These are for the customers/widget. They MUST remain open.

# --- PUBLIC ROUTES ---
@app.get("/")
async def read_landing():
    # Shows the new Marketing Homepage
    return FileResponse('static/index.html')

@app.get("/demo")
async def read_demo():
    # Shows the Cancellation Flow (formerly index.html)
    return FileResponse('static/demo.html')

# --- PROTECTED ROUTES (Login Required) ---
@app.get("/setup", dependencies=[Depends(get_current_username)])
async def read_setup():
    return FileResponse('static/setup.html')

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


# --- PROTECTED ENDPOINTS (Login Required) ---
# We add `dependencies=[Depends(get_current_username)]` to lock these.

@app.get("/dashboard", dependencies=[Depends(get_current_username)])
async def read_dashboard():
    return FileResponse('static/dashboard.html')

@app.get("/settings", dependencies=[Depends(get_current_username)])
async def read_settings():
    return FileResponse('static/settings.html')

@app.get("/dashboard-stats", dependencies=[Depends(get_current_username)])
async def get_dashboard_stats():
    conn = get_db_connection()
    saves = conn.execute("SELECT * FROM saves").fetchall()
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
        "recent_activity": recent_activity[:5]
    }

@app.post("/run-monthly-billing", dependencies=[Depends(get_current_username)])
async def run_monthly_billing():
    # Only the Admin can generate an invoice
    return {"invoice_total": 100} # Placeholder

@app.post("/api/create-offer", dependencies=[Depends(get_current_username)])
async def create_offer(offer: OfferRequest):
    conn = get_db_connection()
    existing = conn.execute("SELECT id FROM offers WHERE project_id = ? AND trigger_rule = ?", (offer.project_id, offer.trigger)).fetchone()

    if existing:
        conn.execute("UPDATE offers SET offer_type=?, offer_value=?, coupon_code=?, is_active=1 WHERE id=?", (offer.type, offer.value, offer.code, existing['id']))
    else:
        conn.execute("INSERT INTO offers (project_id, trigger_rule, offer_type, offer_value, coupon_code, is_active) VALUES (?, ?, ?, ?, ?, 1)", (offer.project_id, offer.trigger, offer.type, offer.value, offer.code))
    
    conn.commit()
    conn.close()
    return {"status": "success", "message": "Custom offer saved!"}

# --- STATIC FILES ---
app.mount("/static", StaticFiles(directory="static"), name="static")