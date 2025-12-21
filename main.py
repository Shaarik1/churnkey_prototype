from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles # <--- New Import
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import stripe
import sqlite3
import datetime
from pydantic import BaseModel

# --- CONFIGURATION ---
stripe.api_key = "sk_test_12345" 
COMMISSION_RATE = 0.20 
DB_FILE = "churnkey.db"

app = FastAPI()

# --- SECURITY ---
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

    # 2. Create the OFFERS table (New!)
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
    print("✅ DATABASE: Tables initialized.")

init_db()

# --- API ENDPOINTS ---
@app.post("/accept-offer")
async def accept_offer(customer_id: str, offer_type: str):
    if offer_type == "50_percent_off":
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
    
    return {"status": "error"}

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

@app.get("/dashboard-stats")
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

@app.post("/run-monthly-billing")
async def run_monthly_billing():
    stats = await get_dashboard_stats()
    return {"invoice_total": stats['your_commission']}

# --- SERVE STATIC FILES (THE WEBSITE) ---
# This must be at the END of the file
@app.get("/")
async def read_index():
    return FileResponse('static/index.html')

@app.get("/dashboard")
async def read_dashboard():
    return FileResponse('static/dashboard.html')

app.mount("/static", StaticFiles(directory="static"), name="static")

# --- CREATE A CUSTOM OFFER ---
@app.post("/api/create-offer")
async def create_offer(project_id: str, trigger: str, type: str, value: int, code: str):
    conn = get_db_connection()
    conn.execute(
        """INSERT INTO offers 
           (project_id, trigger_rule, offer_type, offer_value, coupon_code, is_active) 
           VALUES (?, ?, ?, ?, ?, 1)""",
        (project_id, trigger, type, value, code)
    )
    conn.commit()
    conn.close()
    return {"status": "success", "message": "Custom offer saved!"}

# --- GET THE CORRECT OFFER FOR A USER ---
@app.get("/api/get-offer")
async def get_offer(project_id: str, reason: str):
    conn = get_db_connection()
    
    # 1. Try to find a specific rule for this reason
    offer = conn.execute(
        "SELECT * FROM offers WHERE project_id = ? AND trigger_rule = ? AND is_active = 1",
        (project_id, reason)
    ).fetchone()
    
    # 2. If no specific rule, find the 'default' fallback
    if not offer:
        offer = conn.execute(
            "SELECT * FROM offers WHERE project_id = ? AND trigger_rule = 'default' AND is_active = 1",
            (project_id,)
        ).fetchone()
        
    conn.close()
    
    if offer:
        return dict(offer) # Send the custom config to the frontend
    else:
        # Fallback if the client hasn't set up anything yet
        return {"offer_type": "pause", "offer_value": 1}
    
    # Copy/Paste this into main.py if you haven't yet



# 1. Define the data structure (Pydantic makes it easy to read JSON)
class OfferRequest(BaseModel):
    project_id: str
    trigger: str
    type: str
    value: int
    code: str

# 2. The Endpoint
@app.post("/api/create-offer")
async def create_offer(offer: OfferRequest):
    conn = get_db_connection()
    
    # Check if a rule already exists for this trigger, if so, replace it
    existing = conn.execute(
        "SELECT id FROM offers WHERE project_id = ? AND trigger_rule = ?", 
        (offer.project_id, offer.trigger)
    ).fetchone()

    if existing:
        # Update existing rule
        conn.execute(
            """UPDATE offers SET offer_type=?, offer_value=?, coupon_code=?, is_active=1 
               WHERE id=?""",
            (offer.type, offer.value, offer.code, existing['id'])
        )
    else:
        # Create new rule
        conn.execute(
            """INSERT INTO offers 
               (project_id, trigger_rule, offer_type, offer_value, coupon_code, is_active) 
               VALUES (?, ?, ?, ?, ?, 1)""",
            (offer.project_id, offer.trigger, offer.type, offer.value, offer.code)
        )
    
    conn.commit()
    conn.close()
    return {"status": "success", "message": "Custom offer saved!"}
    
    # --- ADD THIS NEW ROUTE ---
@app.get("/settings")
async def read_settings():
    return FileResponse('static/settings.html')