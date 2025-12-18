# billing_script.py
import stripe
def run_monthly_billing():
    total_saved_revenue = 0
    
    # Get all saves from last month
    saves = database.get_last_month_saves()
    
    for save in saves:
        # Check if the customer is still active (The "Performance" check)
        is_active = stripe_check_if_active(save.customer_id)
        
        if is_active:
            total_saved_revenue += save.saved_amount
            save.status = "verified"
        else:
            save.status = "failed" # They cancelled anyway, you don't charge
            
    # Calculate your invoice
    my_invoice_amount = total_saved_revenue * 0.20
    
    # Send bill to the SaaS company
    stripe.Invoice.create(
        customer="YOUR_CLIENT_ID",
        amount=my_invoice_amount,
        currency="usd"
    )

    # --- ADD THIS TO FIX THE YELLOW 'database' LINE ---

# We create a simple class to act as our "Database" for now
class FakeDatabase:
    def __init__(self):
        self.data = []

    def add_entry(self, customer_id, saved_amount, status):
        # This saves the data to a temporary list in memory
        entry = {
            "customer_id": customer_id,
            "saved_amount": saved_amount,
            "status": status
        }
        self.data.append(entry)
        print(f"Saved to database: {entry}")

# Now we actually CREATE the variable 'database'
database = FakeDatabase() 

def stripe_check_if_active(customer_id):
    try:
        # 1. Ask Stripe for all subscriptions belonging to this customer
        # We look for subscriptions that are 'active' or 'trialing'
        subscriptions = stripe.Subscription.list(
            customer=customer_id, 
            status='all'
        )
        
        # 2. Loop through them to see if any are still valid
        for sub in subscriptions.data:
            if sub.status in ['active', 'trialing']:
                return True # They are still a customer!
        
        return False # No active subscriptions found (They churned)
        
    except Exception as e:
        print(f"Error checking Stripe: {e}")
        return False

# --------------------------------------------------