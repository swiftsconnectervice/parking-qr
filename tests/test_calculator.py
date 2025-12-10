"""
Property-based tests for Fee Calculator API.
"""
import pytest
import string
import uuid
from datetime import datetime, timedelta
from hypothesis import given, settings, assume
from hypothesis import strategies as st

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from models import db, Rate, Session
from tests.strategies import vehicle_type_names, hourly_rates, license_plates, rate_data


# Configure app for testing once
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
app.config['TESTING'] = True


class TestCalculatorSearch:
    """Tests for GET /api/calculator/search endpoint."""

    # **Feature: parking-enhancements, Property 5: Calculator Search Correctness**
    # **Validates: Requirements 2.2, 2.3**
    @given(
        rate=rate_data(),
        plate=license_plates,
        hours_ago=st.floats(min_value=0.1, max_value=24.0, allow_nan=False, allow_infinity=False)
    )
    @settings(max_examples=100, deadline=None)
    def test_calculator_search_returns_correct_session_details(self, rate, plate, hours_ago):
        """
        For any active session with a given plate, searching by that plate SHALL return
        the session details with correctly calculated duration and amount based on
        entry time and hourly rate.
        """
        with app.app_context():
            db.create_all()
            try:
                # Create vehicle type
                new_rate = Rate(
                    vehicle_type=rate['vehicle_type'],
                    hourly_rate=rate['hourly_rate']
                )
                db.session.add(new_rate)
                db.session.commit()
                
                # Create active session with specific entry time
                entry_time = datetime.now() - timedelta(hours=hours_ago)
                token = str(uuid.uuid4())
                session = Session(
                    token=token,
                    plate=plate,
                    vehicle_type=rate['vehicle_type'],
                    entry_time=entry_time,
                    exit_time=None
                )
                db.session.add(session)
                db.session.commit()
                
                with app.test_client() as client:
                    # Search by plate
                    response = client.get(f'/api/calculator/search?plate={plate}')
                    assert response.status_code == 200
                    
                    data = response.get_json()
                    
                    # Verify session details
                    assert data['token'] == token
                    assert data['plate'] == plate
                    assert data['vehicle_type'] == rate['vehicle_type']
                    assert 'entry_time' in data
                    assert 'duration_hours' in data
                    assert 'amount' in data
                    
                    # Verify duration is approximately what we expect
                    # Allow small tolerance for time elapsed during test execution
                    assert abs(data['duration_hours'] - hours_ago) < 0.1, \
                        f"Duration {data['duration_hours']} should be close to {hours_ago}"
                    
                    # Verify amount is reasonable: should be close to duration * rate
                    # The API uses full precision hours for amount calculation
                    # so we verify the amount is in the expected range
                    min_expected = round((hours_ago - 0.1) * rate['hourly_rate'], 2)
                    max_expected = round((hours_ago + 0.1) * rate['hourly_rate'], 2)
                    assert min_expected <= data['amount'] <= max_expected, \
                        f"Amount {data['amount']} should be between {min_expected} and {max_expected}"
            finally:
                db.session.rollback()
                db.drop_all()

    # **Feature: parking-enhancements, Property 5: Calculator Search Correctness**
    # **Validates: Requirements 2.3**
    @given(plate=license_plates)
    @settings(max_examples=100, deadline=None)
    def test_calculator_search_returns_not_found_for_inactive_plate(self, plate):
        """
        For any plate without an active session, searching SHALL return
        a not found error.
        """
        with app.app_context():
            db.create_all()
            try:
                with app.test_client() as client:
                    # Search for non-existent plate
                    response = client.get(f'/api/calculator/search?plate={plate}')
                    assert response.status_code == 404
                    
                    data = response.get_json()
                    assert 'error' in data
                    assert 'No active session' in data['error']
            finally:
                db.session.rollback()
                db.drop_all()

    # **Feature: parking-enhancements, Property 5: Calculator Search Correctness**
    # **Validates: Requirements 2.3**
    @given(
        rate=rate_data(),
        plate=license_plates
    )
    @settings(max_examples=100, deadline=None)
    def test_calculator_search_ignores_completed_sessions(self, rate, plate):
        """
        For any plate with only completed sessions (exit_time IS NOT NULL),
        searching SHALL return a not found error.
        """
        with app.app_context():
            db.create_all()
            try:
                # Create vehicle type
                new_rate = Rate(
                    vehicle_type=rate['vehicle_type'],
                    hourly_rate=rate['hourly_rate']
                )
                db.session.add(new_rate)
                db.session.commit()
                
                # Create completed session
                now = datetime.now()
                session = Session(
                    token=str(uuid.uuid4()),
                    plate=plate,
                    vehicle_type=rate['vehicle_type'],
                    entry_time=now - timedelta(hours=2),
                    exit_time=now,  # Completed
                    amount_paid=20.0
                )
                db.session.add(session)
                db.session.commit()
                
                with app.test_client() as client:
                    # Search by plate - should not find completed session
                    response = client.get(f'/api/calculator/search?plate={plate}')
                    assert response.status_code == 404
                    
                    data = response.get_json()
                    assert 'error' in data
            finally:
                db.session.rollback()
                db.drop_all()



class TestFeeCalculationConsistency:
    """Tests for fee calculation consistency between endpoints."""

    # **Feature: parking-enhancements, Property 6: Fee Calculation Consistency**
    # **Validates: Requirements 2.5**
    @given(
        rate=rate_data(),
        plate=license_plates,
        hours_ago=st.floats(min_value=0.1, max_value=24.0, allow_nan=False, allow_infinity=False)
    )
    @settings(max_examples=100, deadline=None)
    def test_calculator_and_verify_return_same_fee(self, rate, plate, hours_ago):
        """
        For any active session, the fee calculated by the calculator search endpoint
        SHALL equal the fee calculated by the QR verify endpoint.
        """
        with app.app_context():
            db.create_all()
            try:
                # Create vehicle type
                new_rate = Rate(
                    vehicle_type=rate['vehicle_type'],
                    hourly_rate=rate['hourly_rate']
                )
                db.session.add(new_rate)
                db.session.commit()
                
                # Create active session
                entry_time = datetime.now() - timedelta(hours=hours_ago)
                token = str(uuid.uuid4())
                session = Session(
                    token=token,
                    plate=plate,
                    vehicle_type=rate['vehicle_type'],
                    entry_time=entry_time,
                    exit_time=None
                )
                db.session.add(session)
                db.session.commit()
                
                with app.test_client() as client:
                    # Get fee from calculator search (by plate)
                    calc_response = client.get(f'/api/calculator/search?plate={plate}')
                    assert calc_response.status_code == 200
                    calc_data = calc_response.get_json()
                    
                    # Get fee from verify endpoint (by token/QR)
                    verify_response = client.get(f'/api/verify/{token}')
                    assert verify_response.status_code == 200
                    verify_data = verify_response.get_json()
                    
                    # Both endpoints should return the same amount
                    # Allow small tolerance for time elapsed between calls
                    calc_amount = calc_data['amount']
                    verify_amount = verify_data['amount']
                    
                    # The amounts should be very close (within 1 cent per hour of rate)
                    # since both use the same calculation function
                    tolerance = rate['hourly_rate'] * 0.01  # 1% of hourly rate
                    assert abs(calc_amount - verify_amount) <= tolerance, \
                        f"Calculator amount {calc_amount} should equal verify amount {verify_amount}"
                    
                    # Both should return the same vehicle type
                    assert calc_data['vehicle_type'] == verify_data['vehicle_type']
                    
                    # Both should return the same plate
                    assert calc_data['plate'] == verify_data['plate']
            finally:
                db.session.rollback()
                db.drop_all()
