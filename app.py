import os
import qrcode
from datetime import datetime
from flask import Flask, request, jsonify, render_template, send_from_directory
from models import db, Rate, Session
import uuid

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///parking.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

# Create tables and seed data on startup
with app.app_context():
    db.create_all()
    # Add default rates if they don't exist
    if not Rate.query.filter_by(vehicle_type='Auto').first():
        db.session.add(Rate(vehicle_type='Auto', hourly_rate=20.0))
    if not Rate.query.filter_by(vehicle_type='Moto').first():
        db.session.add(Rate(vehicle_type='Moto', hourly_rate=10.0))
    db.session.commit()

# Ensure static/qrs exists
os.makedirs('static/qrs', exist_ok=True)


# ============================================
# Shared Utility Functions
# ============================================

def get_active_sessions():
    """
    Query all active sessions (sessions where exit_time IS NULL).
    
    Returns:
        Query object for active sessions that can be further filtered or executed.
    
    Requirements: 3.2, 4.4
    """
    return Session.query.filter(Session.exit_time.is_(None))


def get_active_session_by_plate(plate):
    """
    Query active session by plate number.
    
    Args:
        plate: License plate string to search for
    
    Returns:
        Session object if found, None otherwise
    
    Requirements: 3.2
    """
    return get_active_sessions().filter_by(plate=plate).first()


def calculate_parking_fee(entry_time, hourly_rate, current_time=None):
    """
    Calculate parking fee based on entry time and hourly rate.
    
    First hour is always charged in full, regardless of actual time.
    After the first hour, charges are calculated by fraction.
    
    Args:
        entry_time: datetime when the vehicle entered
        hourly_rate: float rate per hour
        current_time: optional datetime for calculation (defaults to now)
    
    Returns:
        tuple: (duration_hours, amount) both rounded to 2 decimal places
    """
    if current_time is None:
        current_time = datetime.now()
    
    duration = current_time - entry_time
    hours = duration.total_seconds() / 3600
    
    # First hour is charged in full, after that by fraction
    if hours < 1:
        billable_hours = 1
    else:
        billable_hours = hours
    
    amount = round(billable_hours * hourly_rate, 2)
    
    return round(hours, 2), amount

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register')
def register():
    return render_template('register.html')

@app.route('/scanner')
def scanner():
    return render_template('scanner.html')

@app.route('/vehicle-types')
def vehicle_types():
    return render_template('vehicle_types.html')

@app.route('/calculator')
def calculator():
    return render_template('calculator.html')

@app.route('/dashboard')
def dashboard_view():
    return render_template('dashboard.html')

# ============================================
# Vehicle Types Management API
# ============================================

@app.route('/api/vehicle-types', methods=['GET'])
def get_vehicle_types():
    """List all vehicle types with active session counts."""
    rates = Rate.query.all()
    result = []
    for rate in rates:
        # Count active sessions using shared helper function
        active_count = get_active_sessions().filter_by(
            vehicle_type=rate.vehicle_type
        ).count()
        
        result.append({
            'id': rate.id,
            'vehicle_type': rate.vehicle_type,
            'hourly_rate': rate.hourly_rate,
            'active_sessions': active_count
        })
    return jsonify(result)


@app.route('/api/vehicle-types', methods=['POST'])
def create_vehicle_type():
    """Create a new vehicle type."""
    data = request.json
    
    # Validate required fields
    vehicle_type = data.get('vehicle_type')
    hourly_rate = data.get('hourly_rate')
    
    if not vehicle_type or hourly_rate is None:
        return jsonify({'error': 'Missing required fields'}), 400
    
    # Check for duplicate names
    existing = Rate.query.filter_by(vehicle_type=vehicle_type).first()
    if existing:
        return jsonify({'error': 'Vehicle type already exists'}), 400
    
    # Create new rate
    new_rate = Rate(vehicle_type=vehicle_type, hourly_rate=hourly_rate)
    db.session.add(new_rate)
    db.session.commit()
    
    return jsonify({
        'id': new_rate.id,
        'vehicle_type': new_rate.vehicle_type,
        'hourly_rate': new_rate.hourly_rate
    }), 201


@app.route('/api/vehicle-types/<int:id>', methods=['PUT'])
def update_vehicle_type(id):
    """Update an existing vehicle type."""
    rate = Rate.query.get(id)
    if not rate:
        return jsonify({'error': 'Vehicle type not found'}), 404
    
    data = request.json
    
    # Update name if provided
    new_vehicle_type = data.get('vehicle_type')
    if new_vehicle_type and new_vehicle_type != rate.vehicle_type:
        # Check for duplicate names
        existing = Rate.query.filter_by(vehicle_type=new_vehicle_type).first()
        if existing:
            return jsonify({'error': 'Vehicle type already exists'}), 400
        rate.vehicle_type = new_vehicle_type
    
    # Update hourly_rate if provided
    new_hourly_rate = data.get('hourly_rate')
    if new_hourly_rate is not None:
        rate.hourly_rate = new_hourly_rate
    
    db.session.commit()
    
    return jsonify({
        'id': rate.id,
        'vehicle_type': rate.vehicle_type,
        'hourly_rate': rate.hourly_rate
    })


@app.route('/api/vehicle-types/<int:id>', methods=['DELETE'])
def delete_vehicle_type(id):
    """Delete a vehicle type if no active sessions exist."""
    rate = Rate.query.get(id)
    if not rate:
        return jsonify({'error': 'Vehicle type not found'}), 404
    
    # Check for active sessions using shared helper function
    active_sessions = get_active_sessions().filter_by(
        vehicle_type=rate.vehicle_type
    ).count()
    
    if active_sessions > 0:
        return jsonify({'error': 'Cannot delete: active sessions exist'}), 400
    
    db.session.delete(rate)
    db.session.commit()
    
    return jsonify({'message': 'Vehicle type deleted successfully'})


# ============================================
# Fee Calculator API
# ============================================

@app.route('/api/calculator/search', methods=['GET'])
def calculator_search():
    """Search for active session by plate number and calculate fee."""
    plate = request.args.get('plate')
    
    if not plate:
        return jsonify({'error': 'Missing plate parameter'}), 400
    
    # Query active session by plate using shared helper function
    session = get_active_session_by_plate(plate)
    
    if not session:
        return jsonify({'error': 'No active session found for this plate'}), 404
    
    # Get rate for vehicle type
    rate = Rate.query.filter_by(vehicle_type=session.vehicle_type).first()
    if not rate:
        return jsonify({'error': 'Rate not found'}), 500
    
    # Calculate duration and amount using shared utility function
    duration_hours, amount = calculate_parking_fee(session.entry_time, rate.hourly_rate)
    
    return jsonify({
        'token': session.token,
        'plate': session.plate,
        'vehicle_type': session.vehicle_type,
        'entry_time': session.entry_time.isoformat(),
        'duration_hours': duration_hours,
        'amount': amount
    })


@app.route('/api/entry', methods=['POST'])
def entry():
    data = request.json
    plate = data.get('plate')
    vehicle_type = data.get('vehicle_type')
    brand = data.get('brand', '').strip() or None  # Opcional
    model = data.get('model', '').strip() or None  # Opcional
    color = data.get('color', '').strip() or None  # Opcional
    entry_time_str = data.get('entry_time')  # Hora local del cliente

    if not plate or not vehicle_type:
        return jsonify({'error': 'Missing data'}), 400

    # Parse entry time from client or use server time as fallback
    if entry_time_str:
        try:
            entry_time = datetime.fromisoformat(entry_time_str)
        except ValueError:
            entry_time = datetime.now()
    else:
        entry_time = datetime.now()

    token = str(uuid.uuid4())
    
    # Create QR Code
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(token)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    qr_path = f'static/qrs/{token}.png'
    img.save(qr_path)

    new_session = Session(
        token=token, 
        plate=plate, 
        vehicle_type=vehicle_type,
        brand=brand,
        model=model,
        color=color,
        entry_time=entry_time
    )
    db.session.add(new_session)
    db.session.commit()

    return jsonify({'token': token, 'qr_url': f'/static/qrs/{token}.png'})

@app.route('/api/verify/<token>', methods=['GET'])
def verify(token):
    session = Session.query.get(token)
    if not session:
        return jsonify({'error': 'Session not found'}), 404
    
    if session.exit_time:
        return jsonify({'error': 'Session already closed', 'amount_paid': session.amount_paid}), 400

    rate = Rate.query.filter_by(vehicle_type=session.vehicle_type).first()
    if not rate:
        return jsonify({'error': 'Rate not found'}), 500

    # Calculate duration and amount using shared utility function
    duration_hours, amount = calculate_parking_fee(session.entry_time, rate.hourly_rate)

    return jsonify({
        'plate': session.plate,
        'entry_time': session.entry_time.isoformat(),
        'duration_hours': duration_hours,
        'amount': amount,
        'vehicle_type': session.vehicle_type
    })

# ============================================
# Dashboard API
# ============================================

@app.route('/api/dashboard', methods=['GET'])
def dashboard():
    """Get dashboard statistics for a given date."""
    from sqlalchemy import func
    
    # Get date parameter (default to today)
    date_str = request.args.get('date')
    
    if date_str:
        try:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'error': 'Invalid date format'}), 400
    else:
        target_date = datetime.now().date()
    
    # Query entries count (entry_time on date)
    entries_count = Session.query.filter(
        func.date(Session.entry_time) == target_date
    ).count()
    
    # Query exits count (exit_time on date)
    exits_count = Session.query.filter(
        Session.exit_time.isnot(None),
        func.date(Session.exit_time) == target_date
    ).count()
    
    # Calculate total revenue (sum of amount_paid for exits on date)
    total_revenue_result = db.session.query(
        func.sum(Session.amount_paid)
    ).filter(
        Session.exit_time.isnot(None),
        func.date(Session.exit_time) == target_date
    ).scalar()
    total_revenue = round(total_revenue_result or 0.0, 2)
    
    # Get active vehicles list using shared helper function
    active_sessions = get_active_sessions().all()
    
    active_vehicles = [
        {
            'token': s.token,
            'plate': s.plate,
            'vehicle_type': s.vehicle_type,
            'brand': s.brand,
            'model': s.model,
            'color': s.color,
            'entry_time': s.entry_time.isoformat()
        }
        for s in active_sessions
    ]
    
    # Get stats grouped by vehicle type
    # Get all vehicle types that have sessions on this date
    all_vehicle_types = db.session.query(Session.vehicle_type).distinct().all()
    
    stats_by_type = []
    for (vtype,) in all_vehicle_types:
        # Entries for this type on target date
        type_entries = Session.query.filter(
            Session.vehicle_type == vtype,
            func.date(Session.entry_time) == target_date
        ).count()
        
        # Exits for this type on target date
        type_exits = Session.query.filter(
            Session.vehicle_type == vtype,
            Session.exit_time.isnot(None),
            func.date(Session.exit_time) == target_date
        ).count()
        
        # Revenue for this type on target date
        type_revenue_result = db.session.query(
            func.sum(Session.amount_paid)
        ).filter(
            Session.vehicle_type == vtype,
            Session.exit_time.isnot(None),
            func.date(Session.exit_time) == target_date
        ).scalar()
        type_revenue = round(type_revenue_result or 0.0, 2)
        
        # Only include types that have activity on this date
        if type_entries > 0 or type_exits > 0:
            stats_by_type.append({
                'vehicle_type': vtype,
                'entries': type_entries,
                'exits': type_exits,
                'revenue': type_revenue
            })
    
    return jsonify({
        'date': target_date.isoformat(),
        'entries_count': entries_count,
        'exits_count': exits_count,
        'total_revenue': total_revenue,
        'active_vehicles': active_vehicles,
        'stats_by_type': stats_by_type
    })


@app.route('/api/sessions/<token>', methods=['PUT'])
def update_session(token):
    """Update entry time for an active session."""
    session = Session.query.get(token)
    if not session:
        return jsonify({'error': 'Session not found'}), 404
    
    if session.exit_time:
        return jsonify({'error': 'Cannot edit closed session'}), 400
    
    data = request.json
    new_entry_time = data.get('entry_time')
    
    if not new_entry_time:
        return jsonify({'error': 'Missing entry_time'}), 400
    
    try:
        parsed_time = datetime.fromisoformat(new_entry_time)
    except ValueError:
        return jsonify({'error': 'Invalid date format'}), 400
    
    # Validate: entry time cannot be in the future
    if parsed_time > datetime.now():
        return jsonify({'error': 'Entry time cannot be in the future'}), 400
    
    session.entry_time = parsed_time
    db.session.commit()
    
    return jsonify({
        'token': session.token,
        'plate': session.plate,
        'entry_time': session.entry_time.isoformat(),
        'message': 'Entry time updated'
    })


@app.route('/api/exit', methods=['POST'])
def exit_parking():
    data = request.json
    token = data.get('token')
    
    session = Session.query.get(token)
    if not session:
        return jsonify({'error': 'Session not found'}), 404
    
    if session.exit_time:
        return jsonify({'error': 'Session already closed'}), 400

    # Recalculate amount using shared utility function
    rate = Rate.query.filter_by(vehicle_type=session.vehicle_type).first()
    now = datetime.now()
    _, amount = calculate_parking_fee(session.entry_time, rate.hourly_rate, now)

    session.exit_time = now
    session.amount_paid = amount
    db.session.commit()

    return jsonify({'message': 'Exit confirmed', 'amount_paid': amount})

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', debug=True)
