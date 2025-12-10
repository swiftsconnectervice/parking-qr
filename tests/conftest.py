"""
Pytest configuration and fixtures for parking system tests.
"""
import pytest
import sys
import os
from datetime import datetime, timedelta

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from models import db, Rate, Session


@pytest.fixture
def test_app():
    """Create application configured for testing with in-memory SQLite."""
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    with app.app_context():
        db.create_all()
        yield app
        # Clean up data first, then drop tables with checkfirst to avoid errors
        try:
            db.session.rollback()
            db.session.query(Session).delete()
            db.session.query(Rate).delete()
            db.session.commit()
        except:
            db.session.rollback()
        try:
            db.drop_all()
        except:
            pass


@pytest.fixture
def client(test_app):
    """Flask test client."""
    return test_app.test_client()


@pytest.fixture
def db_session(test_app):
    """Database session for direct database operations."""
    with test_app.app_context():
        yield db.session
        db.session.rollback()


@pytest.fixture
def sample_rate(test_app):
    """Create a sample Rate record."""
    with test_app.app_context():
        rate = Rate(vehicle_type='Auto', hourly_rate=10.0)
        db.session.add(rate)
        db.session.commit()
        yield rate


@pytest.fixture
def sample_rates(test_app):
    """Create multiple sample Rate records."""
    with test_app.app_context():
        rates = [
            Rate(vehicle_type='Auto', hourly_rate=10.0),
            Rate(vehicle_type='Moto', hourly_rate=5.0),
            Rate(vehicle_type='Camioneta', hourly_rate=15.0),
        ]
        for rate in rates:
            db.session.add(rate)
        db.session.commit()
        yield rates


@pytest.fixture
def sample_session(test_app, sample_rate):
    """Create a sample active Session record."""
    with test_app.app_context():
        session = Session(
            token='test-token-123',
            plate='ABC123',
            vehicle_type='Auto',
            entry_time=datetime.now() - timedelta(hours=2)
        )
        db.session.add(session)
        db.session.commit()
        yield session


@pytest.fixture
def sample_sessions(test_app, sample_rates):
    """Create multiple sample Session records (active and completed)."""
    with test_app.app_context():
        now = datetime.now()
        sessions = [
            # Active sessions
            Session(
                token='active-1',
                plate='AAA111',
                vehicle_type='Auto',
                entry_time=now - timedelta(hours=3)
            ),
            Session(
                token='active-2',
                plate='BBB222',
                vehicle_type='Moto',
                entry_time=now - timedelta(hours=1)
            ),
            # Completed session
            Session(
                token='completed-1',
                plate='CCC333',
                vehicle_type='Camioneta',
                entry_time=now - timedelta(hours=5),
                exit_time=now - timedelta(hours=2),
                amount_paid=45.0
            ),
        ]
        for session in sessions:
            db.session.add(session)
        db.session.commit()
        yield sessions
