from flask import Flask, render_template, redirect, url_for, request, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import json

app = Flask(__name__, template_folder='templates')
app.config['SECRET_KEY'] = 'mashemeji_derby_secret_key' # Change this in production
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///sokaticket.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'user_login'
login_manager.login_message = "Please log in to access this page."

# --- Database Models ---

class User(UserMixin, db.Model):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
    role = db.Column(db.String(50), nullable=False, default='user')  # 'admin', 'vendor', 'user'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    tickets = db.relationship('Ticket', backref='owner', lazy=True, foreign_keys='Ticket.user_id')
    events = db.relationship('Event', backref='vendor', lazy=True, foreign_keys='Event.vendor_id')
    cart_items = db.relationship('Cart', backref='user', lazy=True)
    transactions = db.relationship('Transaction', backref='user', lazy=True)

class Event(db.Model):
    __tablename__ = 'event'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    venue = db.Column(db.String(200), nullable=False)
    date = db.Column(db.DateTime, nullable=False)
    ticket_quantity = db.Column(db.Integer, nullable=False)
    ticket_price = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(100), nullable=False)
    image_url = db.Column(db.String(500))
    vendor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    tickets = db.relationship('Ticket', backref='event', lazy=True)
    
    @property
    def tickets_sold(self):
        return Ticket.query.filter_by(event_id=self.id, status='purchased').count()
    
    @property
    def tickets_available(self):
        return self.ticket_quantity - self.tickets_sold

class Ticket(db.Model):
    __tablename__ = 'ticket'
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    purchase_date = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(50), default='purchased')  # 'purchased', 'resale', 'sold'
    qr_code = db.Column(db.String(500))
    price_paid = db.Column(db.Float, nullable=False)
    
    # Resale fields
    is_for_sale = db.Column(db.Boolean, default=False)
    resale_price = db.Column(db.Float)

class Cart(db.Model):
    __tablename__ = 'cart'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    added_date = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    event = db.relationship('Event')

class Transaction(db.Model):
    __tablename__ = 'transaction'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(50), default='pending')  # 'pending', 'completed', 'failed'
    payment_method = db.Column(db.String(50))  # 'mpesa', 'card'
    mpesa_code = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    items = db.Column(db.Text)  # JSON string of purchased items

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- Context Processor ---
@app.context_processor
def utility_processor():
    def cart_count():
        if current_user.is_authenticated and current_user.role == 'user':
            return Cart.query.filter_by(user_id=current_user.id).count()
        return 0
    
    return dict(cart_count=cart_count, now=datetime.utcnow)

# --- Routes ---

@app.route('/')
def home():
    """Landing page"""
    events = Event.query.filter(Event.date > datetime.utcnow()).order_by(Event.date).limit(6).all()
    return render_template('landing.html', events=events)

# --- Authentication Routes ---

@app.route('/user/login', methods=['GET', 'POST'])
def user_login():
    """Regular user login"""
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password, password):
            if user.role != 'user':
                flash(f'This is a {user.role} account. Please use the appropriate login.', 'warning')
                return redirect(url_for('home'))
            login_user(user)
            return redirect(url_for('user_dashboard'))
        flash('Invalid credentials. Please try again.', 'danger')
    return render_template('user_login.html')

@app.route('/vendor/login', methods=['GET', 'POST'])
def vendor_login():
    """Vendor login"""
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password, password):
            if user.role != 'vendor':
                flash('Invalid vendor account.', 'danger')
                return redirect(url_for('home'))
            login_user(user)
            return redirect(url_for('vendor_dashboard'))
        flash('Invalid vendor credentials.', 'danger')
    return render_template('vendor_login.html')

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    """Admin login"""
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password, password):
            if user.role != 'admin':
                flash('Invalid admin account.', 'danger')
                return redirect(url_for('home'))
            login_user(user)
            return redirect(url_for('admin_dashboard'))
        flash('Invalid admin credentials.', 'danger')
    return render_template('admin_login.html')

@app.route('/register/user', methods=['GET', 'POST'])
def register_user():
    """Regular user registration"""
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return redirect(url_for('register_user'))

        if User.query.filter_by(username=username).first():
            flash('Username already exists.', 'warning')
            return redirect(url_for('register_user'))
        
        if User.query.filter_by(email=email).first():
            flash('Email already registered.', 'warning')
            return redirect(url_for('register_user'))

        hashed_pw = generate_password_hash(password, method='pbkdf2:sha256')
        new_user = User(username=username, email=email, password=hashed_pw, role='user')
        db.session.add(new_user)
        db.session.commit()
        flash('Account created successfully! Please login.', 'success')
        return redirect(url_for('user_login'))
    return render_template('register_user.html')

@app.route('/register/vendor', methods=['GET', 'POST'])
def register_vendor():
    """Vendor registration"""
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        business_name = request.form.get('business_name')
        phone = request.form.get('phone')

        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return redirect(url_for('register_vendor'))

        if User.query.filter_by(username=username).first():
            flash('Username already exists.', 'warning')
            return redirect(url_for('register_vendor'))
        
        if User.query.filter_by(email=email).first():
            flash('Email already registered.', 'warning')
            return redirect(url_for('register_vendor'))

        hashed_pw = generate_password_hash(password, method='pbkdf2:sha256')
        new_vendor = User(username=username, email=email, password=hashed_pw, role='vendor')
        db.session.add(new_vendor)
        db.session.commit()
        
        flash('Vendor account created successfully! Please login.', 'success')
        return redirect(url_for('vendor_login'))
    return render_template('register_vendor.html')

# --- User Routes ---

@app.route('/user/dashboard')
@login_required
def user_dashboard():
    """Regular user dashboard"""
    if current_user.role != 'user':
        flash('Access denied.', 'danger')
        return redirect(url_for('home'))
    
    # Upcoming events
    upcoming_events = Event.query.filter(Event.date > datetime.utcnow()).order_by(Event.date).all()
    
    # User's tickets
    my_tickets = Ticket.query.filter_by(user_id=current_user.id, status='purchased').all()
    
    # Resale tickets available
    resale_tickets = Ticket.query.filter_by(is_for_sale=True).filter(Ticket.user_id != current_user.id).all()
    
    return render_template('user_dashboard.html', 
                         upcoming_events=upcoming_events,
                         my_tickets=my_tickets,
                         resale_tickets=resale_tickets)

@app.route('/events')
def browse_events():
    """Browse all events"""
    category = request.args.get('category', 'all')
    search = request.args.get('search', '')
    
    query = Event.query.filter(Event.date > datetime.utcnow())
    
    if category != 'all':
        query = query.filter_by(category=category)
    
    if search:
        query = query.filter(Event.title.contains(search) | Event.description.contains(search))
    
    events = query.order_by(Event.date).all()
    categories = db.session.query(Event.category).distinct().all()
    
    return render_template('browse_events.html', events=events, categories=[c[0] for c in categories])

@app.route('/event/<int:event_id>')
def event_detail(event_id):
    """Event details page"""
    event = Event.query.get_or_404(event_id)
    return render_template('event_detail.html', event=event)

# --- Cart Routes ---

@app.route('/cart/add/<int:event_id>', methods=['POST'])
@login_required
def add_to_cart(event_id):
    """Add ticket to cart"""
    if current_user.role != 'user':
        flash('Only users can purchase tickets.', 'warning')
        return redirect(url_for('home'))
    
    quantity = int(request.form.get('quantity', 1))
    event = Event.query.get_or_404(event_id)
    
    # Check if enough tickets available
    if event.tickets_available < quantity:
        flash(f'Only {event.tickets_available} tickets available.', 'danger')
        return redirect(url_for('event_detail', event_id=event_id))
    
    # Check if already in cart
    cart_item = Cart.query.filter_by(user_id=current_user.id, event_id=event_id).first()
    
    if cart_item:
        cart_item.quantity += quantity
    else:
        cart_item = Cart(user_id=current_user.id, event_id=event_id, quantity=quantity)
        db.session.add(cart_item)
    
    db.session.commit()
    flash(f'Added {quantity} ticket(s) to cart!', 'success')
    return redirect(url_for('view_cart'))

@app.route('/cart')
@login_required
def view_cart():
    """View shopping cart"""
    if current_user.role != 'user':
        flash('Access denied.', 'danger')
        return redirect(url_for('home'))
    
    cart_items = Cart.query.filter_by(user_id=current_user.id).all()
    total = sum(item.event.ticket_price * item.quantity for item in cart_items)
    
    return render_template('cart.html', cart_items=cart_items, total=total)

@app.route('/cart/remove/<int:item_id>')
@login_required
def remove_from_cart(item_id):
    """Remove item from cart"""
    cart_item = Cart.query.get_or_404(item_id)
    if cart_item.user_id == current_user.id:
        db.session.delete(cart_item)
        db.session.commit()
        flash('Item removed from cart.', 'success')
    return redirect(url_for('view_cart'))

@app.route('/cart/update/<int:item_id>', methods=['POST'])
@login_required
def update_cart(item_id):
    """Update cart item quantity"""
    cart_item = Cart.query.get_or_404(item_id)
    if cart_item.user_id == current_user.id:
        quantity = int(request.form.get('quantity', 1))
        if quantity > 0:
            cart_item.quantity = quantity
            db.session.commit()
            flash('Cart updated.', 'success')
        else:
            db.session.delete(cart_item)
            db.session.commit()
            flash('Item removed.', 'success')
    return redirect(url_for('view_cart'))

@app.route('/checkout', methods=['GET', 'POST'])
@login_required
def checkout():
    """Checkout and payment"""
    if current_user.role != 'user':
        return redirect(url_for('home'))
    
    cart_items = Cart.query.filter_by(user_id=current_user.id).all()
    if not cart_items:
        flash('Your cart is empty.', 'warning')
        return redirect(url_for('browse_events'))
    
    total = sum(item.event.ticket_price * item.quantity for item in cart_items)
    
    if request.method == 'POST':
        payment_method = request.form.get('payment_method')
        
        # Create transaction record
        items_json = json.dumps([{
            'event_id': item.event_id,
            'event_title': item.event.title,
            'quantity': item.quantity,
            'price': item.event.ticket_price
        } for item in cart_items])
        
        transaction = Transaction(
            user_id=current_user.id,
            amount=total,
            payment_method=payment_method,
            status='pending',
            items=items_json
        )
        db.session.add(transaction)
        db.session.commit()
        
        if payment_method == 'mpesa':
            return redirect(url_for('mpesa_payment', transaction_id=transaction.id))
        else:
            return redirect(url_for('process_payment', transaction_id=transaction.id))
    
    return render_template('checkout.html', cart_items=cart_items, total=total)

@app.route('/mpesa/payment/<int:transaction_id>')
@login_required
def mpesa_payment(transaction_id):
    """M-Pesa payment page"""
    transaction = Transaction.query.get_or_404(transaction_id)
    if transaction.user_id != current_user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('home'))
    
    return render_template('mpesa_payment.html', transaction=transaction)

@app.route('/process-payment/<int:transaction_id>', methods=['POST'])
@login_required
def process_payment(transaction_id):
    """Process payment and create tickets"""
    transaction = Transaction.query.get_or_404(transaction_id)
    
    if transaction.user_id != current_user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('home'))
    
    mpesa_code = request.form.get('mpesa_code')
    
    # Simulate payment processing
    transaction.status = 'completed'
    transaction.mpesa_code = mpesa_code
    
    # Create tickets
    items = json.loads(transaction.items)
    for item in items:
        for _ in range(item['quantity']):
            ticket = Ticket(
                event_id=item['event_id'],
                user_id=current_user.id,
                price_paid=item['price'],
                status='purchased'
            )
            db.session.add(ticket)
    
    # Clear cart
    Cart.query.filter_by(user_id=current_user.id).delete()
    
    db.session.commit()
    
    flash('Payment successful! Tickets have been added to your account.', 'success')
    return redirect(url_for('my_tickets'))

@app.route('/my-tickets')
@login_required
def my_tickets():
    """View my purchased tickets"""
    if current_user.role != 'user':
        return redirect(url_for('home'))
    
    tickets = Ticket.query.filter_by(user_id=current_user.id, status='purchased').order_by(Ticket.purchase_date.desc()).all()
    return render_template('my_tickets.html', tickets=tickets)

@app.route('/ticket/<int:ticket_id>/resale', methods=['GET', 'POST'])
@login_required
def ticket_resale(ticket_id):
    """Put ticket on resale market"""
    ticket = Ticket.query.get_or_404(ticket_id)
    
    if ticket.user_id != current_user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('my_tickets'))
    
    if request.method == 'POST':
        resale_price = float(request.form.get('resale_price'))
        ticket.is_for_sale = True
        ticket.resale_price = resale_price
        ticket.status = 'resale'
        db.session.commit()
        flash('Ticket listed for resale!', 'success')
        return redirect(url_for('my_tickets'))
    
    return render_template('ticket_resale.html', ticket=ticket)

@app.route('/sell_ticket/<int:ticket_id>')
@login_required
def sell_ticket(ticket_id):
    """Toggle ticket resale status"""
    ticket = Ticket.query.get_or_404(ticket_id)
    if ticket.user_id == current_user.id:
        ticket.is_for_sale = not ticket.is_for_sale
        ticket.status = 'resale' if ticket.is_for_sale else 'purchased'
        db.session.commit()
        status = "on sale" if ticket.is_for_sale else "off sale"
        flash(f'Ticket is now {status}.', 'info')
    return redirect(url_for('my_tickets'))

@app.route('/buy_resale/<int:ticket_id>')
@login_required
def buy_resale(ticket_id):
    """Buy a resale ticket"""
    ticket = Ticket.query.get_or_404(ticket_id)
    
    if ticket.user_id == current_user.id:
        flash('You cannot buy your own ticket.', 'warning')
        return redirect(url_for('user_dashboard'))
    
    # Transfer ownership
    old_owner = ticket.user_id
    ticket.user_id = current_user.id
    ticket.is_for_sale = False
    ticket.status = 'purchased'
    ticket.price_paid = ticket.resale_price  # Update price paid
    db.session.commit()
    
    flash('You bought a resale ticket!', 'success')
    return redirect(url_for('my_tickets'))

# --- Vendor Routes ---

@app.route('/vendor/dashboard')
@login_required
def vendor_dashboard():
    """Vendor dashboard"""
    if current_user.role != 'vendor':
        flash('Access denied.', 'danger')
        return redirect(url_for('home'))
    
    # Vendor's events
    my_events = Event.query.filter_by(vendor_id=current_user.id).order_by(Event.date).all()
    
    # Sales statistics
    total_tickets_sold = 0
    total_revenue = 0
    for event in my_events:
        sold = event.tickets_sold
        total_tickets_sold += sold
        total_revenue += sold * event.ticket_price
    
    # Recent sales
    recent_tickets = Ticket.query.join(Event).filter(Event.vendor_id == current_user.id).order_by(Ticket.purchase_date.desc()).limit(10).all()
    
    return render_template('vendor_dashboard.html', 
                         my_events=my_events,
                         total_tickets_sold=total_tickets_sold,
                         total_revenue=total_revenue,
                         recent_tickets=recent_tickets)

@app.route('/vendor/events/create', methods=['GET', 'POST'])
@login_required
def create_event():
    """Create new event"""
    if current_user.role != 'vendor':
        flash('Access denied.', 'danger')
        return redirect(url_for('home'))
    
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        venue = request.form.get('venue')
        date_str = request.form.get('date')
        ticket_quantity = int(request.form.get('ticket_quantity'))
        ticket_price = float(request.form.get('ticket_price'))
        category = request.form.get('category')
        image_url = request.form.get('image_url')
        
        try:
            event_date = datetime.strptime(date_str, '%Y-%m-%dT%H:%M')
            
            new_event = Event(
                title=title,
                description=description,
                venue=venue,
                date=event_date,
                ticket_quantity=ticket_quantity,
                ticket_price=ticket_price,
                category=category,
                image_url=image_url,
                vendor_id=current_user.id
            )
            db.session.add(new_event)
            db.session.commit()
            flash('Event created successfully!', 'success')
            return redirect(url_for('vendor_dashboard'))
        except ValueError:
            flash('Invalid date format.', 'danger')
    
    return render_template('create_event.html')

@app.route('/vendor/events/<int:event_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_event(event_id):
    """Edit event"""
    event = Event.query.get_or_404(event_id)
    
    if event.vendor_id != current_user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('vendor_dashboard'))
    
    if request.method == 'POST':
        event.title = request.form.get('title')
        event.description = request.form.get('description')
        event.venue = request.form.get('venue')
        event.ticket_price = float(request.form.get('ticket_price'))
        event.category = request.form.get('category')
        event.image_url = request.form.get('image_url')
        
        db.session.commit()
        flash('Event updated successfully!', 'success')
        return redirect(url_for('vendor_dashboard'))
    
    return render_template('edit_event.html', event=event)

@app.route('/vendor/events/<int:event_id>/attendees')
@login_required
def event_attendees(event_id):
    """View event attendees"""
    event = Event.query.get_or_404(event_id)
    
    if event.vendor_id != current_user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('vendor_dashboard'))
    
    tickets = Ticket.query.filter_by(event_id=event_id, status='purchased').all()
    return render_template('event_attendees.html', event=event, tickets=tickets)

@app.route('/vendor/sales-report')
@login_required
def vendor_sales_report():
    """Vendor sales report"""
    if current_user.role != 'vendor':
        return redirect(url_for('home'))
    
    events = Event.query.filter_by(vendor_id=current_user.id).all()
    report_data = []
    
    for event in events:
        tickets_sold = event.tickets_sold
        report_data.append({
            'event': event,
            'tickets_sold': tickets_sold,
            'revenue': tickets_sold * event.ticket_price,
            'available': event.tickets_available
        })
    
    return render_template('vendor_sales_report.html', report_data=report_data)

# --- Admin Routes ---

@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    """Admin dashboard"""
    if current_user.role != 'admin':
        flash('Access denied.', 'danger')
        return redirect(url_for('home'))
    
    # Statistics
    total_users = User.query.count()
    total_vendors = User.query.filter_by(role='vendor').count()
    total_events = Event.query.count()
    total_tickets_sold = Ticket.query.count()
    total_revenue = db.session.query(db.func.sum(Ticket.price_paid)).scalar() or 0
    
    # Recent activity
    recent_users = User.query.order_by(User.created_at.desc()).limit(5).all()
    recent_events = Event.query.order_by(Event.created_at.desc()).limit(5).all()
    recent_transactions = Transaction.query.order_by(Transaction.created_at.desc()).limit(5).all()
    
    return render_template('admin_dashboard.html',
                         total_users=total_users,
                         total_vendors=total_vendors,
                         total_events=total_events,
                         total_tickets_sold=total_tickets_sold,
                         total_revenue=total_revenue,
                         recent_users=recent_users,
                         recent_events=recent_events,
                         recent_transactions=recent_transactions)

@app.route('/admin/users')
@login_required
def admin_users():
    """Manage users"""
    if current_user.role != 'admin':
        return redirect(url_for('home'))
    
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('admin_users.html', users=users)

@app.route('/admin/users/<int:user_id>/toggle-role', methods=['POST'])
@login_required
def toggle_user_role(user_id):
    """Change user role"""
    if current_user.role != 'admin':
        return redirect(url_for('home'))
    
    user = User.query.get_or_404(user_id)
    new_role = request.form.get('role')
    
    if new_role in ['user', 'vendor', 'admin'] and user.id != current_user.id:
        user.role = new_role
        db.session.commit()
        flash(f'User role updated to {new_role}.', 'success')
    
    return redirect(url_for('admin_users'))

@app.route('/admin/events')
@login_required
def admin_events():
    """Manage all events"""
    if current_user.role != 'admin':
        return redirect(url_for('home'))
    
    events = Event.query.order_by(Event.date.desc()).all()
    return render_template('admin_events.html', events=events)

@app.route('/admin/events/<int:event_id>/delete', methods=['POST'])
@login_required
def admin_delete_event(event_id):
    """Delete event (admin only)"""
    if current_user.role != 'admin':
        return redirect(url_for('home'))
    
    event = Event.query.get_or_404(event_id)
    db.session.delete(event)
    db.session.commit()
    flash('Event deleted.', 'success')
    return redirect(url_for('admin_events'))

@app.route('/admin/transactions')
@login_required
def admin_transactions():
    """View all transactions"""
    if current_user.role != 'admin':
        return redirect(url_for('home'))
    
    transactions = Transaction.query.order_by(Transaction.created_at.desc()).all()
    return render_template('admin_transactions.html', transactions=transactions)

# --- Logout ---

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('home'))

# --- Error Handlers ---

@app.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('500.html'), 500

# --- Seeding Data ---

def seed_data():
    """Seed initial data"""
    # Create admin if not exists
    if not User.query.filter_by(username='admin').first():
        admin = User(
            username='admin',
            email='admin@sokaticket.com',
            password=generate_password_hash('admin123', method='pbkdf2:sha256'),
            role='admin'
        )
        db.session.add(admin)
        print("✓ Admin user created (User: admin, Pass: admin123)")
    
    # Create test vendor
    if not User.query.filter_by(username='testvendor').first():
        vendor = User(
            username='testvendor',
            email='vendor@sokaticket.com',
            password=generate_password_hash('vendor123', method='pbkdf2:sha256'),
            role='vendor'
        )
        db.session.add(vendor)
        print("✓ Test vendor created (User: testvendor, Pass: vendor123)")
    
    # Create test user
    if not User.query.filter_by(username='testuser').first():
        user = User(
            username='testuser',
            email='user@sokaticket.com',
            password=generate_password_hash('user123', method='pbkdf2:sha256'),
            role='user'
        )
        db.session.add(user)
        print("✓ Test user created (User: testuser, Pass: user123)")
    
    # Create sample events if none exist
    if Event.query.count() == 0:
        vendor = User.query.filter_by(role='vendor').first()
        if vendor:
            sample_events = [
                Event(
                    title="African Cup Final 2024",
                    description="The biggest football match of the year! Kenya vs Ghana in an epic showdown for the African Cup trophy.",
                    venue="Kasarani Stadium, Nairobi",
                    date=datetime(2024, 12, 15, 16, 0),
                    ticket_quantity=5000,
                    ticket_price=1500,
                    category="Sports",
                    image_url="https://images.unsplash.com/photo-1577223625816-6500cc0d7247?ixlib=rb-4.0.3&auto=format&fit=crop&w=800&q=80",
                    vendor_id=vendor.id
                ),
                Event(
                    title="Sauti Sol: Live in Concert",
                    description="Kenya's favorite afro-pop band performs their greatest hits live. Featuring special guests.",
                    venue="KICC Grounds, Nairobi",
                    date=datetime(2024, 11, 20, 19, 0),
                    ticket_quantity=2000,
                    ticket_price=2500,
                    category="Music",
                    image_url="https://images.unsplash.com/photo-1501386761578-eac5c94b800a?ixlib=rb-4.0.3&auto=format&fit=crop&w=800&q=80",
                    vendor_id=vendor.id
                ),
                Event(
                    title="Churchill Live: Comedy Night",
                    description="An evening of laughter with Kenya's top comedians including Churchill, MC Jessy, and special guests.",
                    venue="The Alchemist, Westlands",
                    date=datetime(2024, 10, 30, 20, 0),
                    ticket_quantity=300,
                    ticket_price=1000,
                    category="Comedy",
                    image_url="https://images.unsplash.com/photo-1527224857830-43a7acc85260?ixlib=rb-4.0.3&auto=format&fit=crop&w=800&q=80",
                    vendor_id=vendor.id
                ),
                Event(
                    title="Nairobi Fashion Week",
                    description="Kenya's premier fashion event showcasing the best designers from across Africa.",
                    venue="Kenyatta International Convention Centre",
                    date=datetime(2024, 11, 5, 18, 0),
                    ticket_quantity=1000,
                    ticket_price=3000,
                    category="Fashion",
                    image_url="https://images.unsplash.com/photo-1490481651871-ab68de25d43d?ixlib=rb-4.0.3&auto=format&fit=crop&w=800&q=80",
                    vendor_id=vendor.id
                ),
                Event(
                    title="Koroga Festival",
                    description="Experience the best of Kenyan music, food, and culture at the monthly Koroga Festival.",
                    venue="Arboretum Park, Nairobi",
                    date=datetime(2024, 11, 10, 12, 0),
                    ticket_quantity=1500,
                    ticket_price=2000,
                    category="Festival",
                    image_url="https://images.unsplash.com/photo-1533174072545-7a4b6ad7a6c3?ixlib=rb-4.0.3&auto=format&fit=crop&w=800&q=80",
                    vendor_id=vendor.id
                ),
                Event(
                    title="Shujaa 7s Rugby Tournament",
                    description="International rugby sevens tournament featuring Kenya's national team and top international sides.",
                    venue="RFUEA Grounds, Nairobi",
                    date=datetime(2024, 12, 5, 9, 0),
                    ticket_quantity=3000,
                    ticket_price=2000,
                    category="Sports",
                    image_url="https://images.unsplash.com/photo-1540747913346-19e32dc3e97e?ixlib=rb-4.0.3&auto=format&fit=crop&w=800&q=80",
                    vendor_id=vendor.id
                )
            ]
            for event in sample_events:
                db.session.add(event)
            print("✓ Sample events created")

    db.session.commit()

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        seed_data()
    app.run(debug=True, port=5000)