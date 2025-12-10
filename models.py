from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Rate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    vehicle_type = db.Column(db.String(50), unique=True, nullable=False)
    hourly_rate = db.Column(db.Float, nullable=False)

class Session(db.Model):
    token = db.Column(db.String(100), primary_key=True)
    plate = db.Column(db.String(20), nullable=False)
    vehicle_type = db.Column(db.String(50), nullable=False)
    brand = db.Column(db.String(50), nullable=True)  # Marca (opcional)
    model = db.Column(db.String(50), nullable=True)  # Modelo (opcional)
    color = db.Column(db.String(30), nullable=True)  # Color (opcional)
    entry_time = db.Column(db.DateTime, default=datetime.now)
    exit_time = db.Column(db.DateTime, nullable=True)
    amount_paid = db.Column(db.Float, nullable=True)
