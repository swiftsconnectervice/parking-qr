"""
Property-based tests for Vehicle Types Management API.
"""
import pytest
import string
from hypothesis import given, settings, assume, Phase
from hypothesis import strategies as st

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from models import db, Rate, Session
from tests.strategies import vehicle_type_names, hourly_rates, rate_data


# Configure app for testing once
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
app.config['TESTING'] = True


class TestVehicleTypeListing:
    """Tests for GET /api/vehicle-types endpoint."""

    # **Feature: parking-enhancements, Property 1: Vehicle Type CRUD Round-Trip**
    # **Validates: Requirements 1.1, 1.2, 1.6, 5.1, 5.2**
    @given(rate=rate_data())
    @settings(max_examples=100, deadline=None)
    def test_created_vehicle_type_appears_in_listing(self, rate):
        """
        For any valid vehicle type name and hourly rate, creating a vehicle type
        and then querying all types SHALL return a list containing that vehicle type
        with the correct rate.
        """
        with app.app_context():
            db.create_all()
            try:
                # Create the vehicle type directly in DB
                new_rate = Rate(
                    vehicle_type=rate['vehicle_type'],
                    hourly_rate=rate['hourly_rate']
                )
                db.session.add(new_rate)
                db.session.commit()
                created_id = new_rate.id
                
                # Query via API
                with app.test_client() as client:
                    response = client.get('/api/vehicle-types')
                    assert response.status_code == 200
                    
                    data = response.get_json()
                    assert isinstance(data, list)
                    
                    # Find our created type in the list
                    found = None
                    for item in data:
                        if item['id'] == created_id:
                            found = item
                            break
                    
                    assert found is not None, f"Created vehicle type not found in listing"
                    assert found['vehicle_type'] == rate['vehicle_type']
                    assert found['hourly_rate'] == rate['hourly_rate']
                    assert 'active_sessions' in found
            finally:
                db.session.rollback()
                db.drop_all()



class TestVehicleTypeCreation:
    """Tests for POST /api/vehicle-types endpoint."""

    # **Feature: parking-enhancements, Property 1: Vehicle Type CRUD Round-Trip**
    # **Validates: Requirements 1.1, 1.2, 1.6, 5.1, 5.2**
    @given(rate=rate_data())
    @settings(max_examples=100, deadline=None)
    def test_create_vehicle_type_via_api_round_trip(self, rate):
        """
        For any valid vehicle type name and hourly rate, creating via POST
        and then querying all types SHALL return a list containing that vehicle type
        with the correct rate.
        """
        with app.app_context():
            db.create_all()
            try:
                with app.test_client() as client:
                    # Create via API
                    create_response = client.post(
                        '/api/vehicle-types',
                        json=rate,
                        content_type='application/json'
                    )
                    assert create_response.status_code == 201
                    
                    created_data = create_response.get_json()
                    assert created_data['vehicle_type'] == rate['vehicle_type']
                    assert created_data['hourly_rate'] == rate['hourly_rate']
                    assert 'id' in created_data
                    
                    created_id = created_data['id']
                    
                    # Query via API to verify round-trip
                    list_response = client.get('/api/vehicle-types')
                    assert list_response.status_code == 200
                    
                    data = list_response.get_json()
                    found = None
                    for item in data:
                        if item['id'] == created_id:
                            found = item
                            break
                    
                    assert found is not None, "Created vehicle type not found in listing"
                    assert found['vehicle_type'] == rate['vehicle_type']
                    assert found['hourly_rate'] == rate['hourly_rate']
            finally:
                db.session.rollback()
                db.drop_all()

    # **Feature: parking-enhancements, Property 1: Vehicle Type CRUD Round-Trip**
    # **Validates: Requirements 1.2, 1.6**
    @given(rate=rate_data())
    @settings(max_examples=100, deadline=None)
    def test_duplicate_vehicle_type_rejected(self, rate):
        """
        For any vehicle type, attempting to create a duplicate SHALL fail
        with an appropriate error.
        """
        with app.app_context():
            db.create_all()
            try:
                with app.test_client() as client:
                    # Create first time - should succeed
                    first_response = client.post(
                        '/api/vehicle-types',
                        json=rate,
                        content_type='application/json'
                    )
                    assert first_response.status_code == 201
                    
                    # Create second time with same name - should fail
                    second_response = client.post(
                        '/api/vehicle-types',
                        json=rate,
                        content_type='application/json'
                    )
                    assert second_response.status_code == 400
                    
                    error_data = second_response.get_json()
                    assert 'error' in error_data
            finally:
                db.session.rollback()
                db.drop_all()



class TestVehicleTypeUpdate:
    """Tests for PUT /api/vehicle-types/<id> endpoint."""

    # **Feature: parking-enhancements, Property 2: Vehicle Type Update Consistency**
    # **Validates: Requirements 1.3**
    @given(
        original=rate_data(),
        new_name=vehicle_type_names,
        new_rate=hourly_rates
    )
    @settings(max_examples=100, deadline=None)
    def test_update_vehicle_type_consistency(self, original, new_name, new_rate):
        """
        For any existing vehicle type and new valid values, updating the type
        and then querying SHALL return the updated values.
        """
        # Ensure new_name is different from original to avoid duplicate check issues
        assume(new_name != original['vehicle_type'])
        
        with app.app_context():
            db.create_all()
            try:
                with app.test_client() as client:
                    # Create original vehicle type
                    create_response = client.post(
                        '/api/vehicle-types',
                        json=original,
                        content_type='application/json'
                    )
                    assert create_response.status_code == 201
                    created_id = create_response.get_json()['id']
                    
                    # Update with new values
                    update_data = {
                        'vehicle_type': new_name,
                        'hourly_rate': new_rate
                    }
                    update_response = client.put(
                        f'/api/vehicle-types/{created_id}',
                        json=update_data,
                        content_type='application/json'
                    )
                    assert update_response.status_code == 200
                    
                    updated_data = update_response.get_json()
                    assert updated_data['vehicle_type'] == new_name
                    assert updated_data['hourly_rate'] == new_rate
                    
                    # Query to verify persistence
                    list_response = client.get('/api/vehicle-types')
                    assert list_response.status_code == 200
                    
                    data = list_response.get_json()
                    found = None
                    for item in data:
                        if item['id'] == created_id:
                            found = item
                            break
                    
                    assert found is not None
                    assert found['vehicle_type'] == new_name
                    assert found['hourly_rate'] == new_rate
            finally:
                db.session.rollback()
                db.drop_all()



class TestVehicleTypeDeletion:
    """Tests for DELETE /api/vehicle-types/<id> endpoint."""

    # **Feature: parking-enhancements, Property 3: Delete Protection for Active Sessions**
    # **Validates: Requirements 1.4, 1.5**
    @given(rate=rate_data(), plate=st.text(
        alphabet=string.ascii_uppercase + string.digits,
        min_size=3,
        max_size=10
    ).filter(lambda x: len(x) >= 3))
    @settings(max_examples=100, deadline=None)
    def test_delete_protected_when_active_sessions_exist(self, rate, plate):
        """
        For any vehicle type that has at least one active session (exit_time IS NULL),
        attempting to delete that type SHALL fail and the type SHALL remain in the database.
        """
        with app.app_context():
            db.create_all()
            try:
                with app.test_client() as client:
                    # Create vehicle type
                    create_response = client.post(
                        '/api/vehicle-types',
                        json=rate,
                        content_type='application/json'
                    )
                    assert create_response.status_code == 201
                    created_id = create_response.get_json()['id']
                    
                    # Create an active session for this vehicle type
                    import uuid
                    active_session = Session(
                        token=str(uuid.uuid4()),
                        plate=plate,
                        vehicle_type=rate['vehicle_type'],
                        exit_time=None  # Active session
                    )
                    db.session.add(active_session)
                    db.session.commit()
                    
                    # Attempt to delete - should fail
                    delete_response = client.delete(f'/api/vehicle-types/{created_id}')
                    assert delete_response.status_code == 400
                    
                    error_data = delete_response.get_json()
                    assert 'error' in error_data
                    
                    # Verify type still exists
                    list_response = client.get('/api/vehicle-types')
                    data = list_response.get_json()
                    found = any(item['id'] == created_id for item in data)
                    assert found, "Vehicle type should still exist after failed delete"
            finally:
                db.session.rollback()
                db.drop_all()

    # **Feature: parking-enhancements, Property 4: Delete Success for Inactive Types**
    # **Validates: Requirements 1.4, 1.5**
    @given(rate=rate_data())
    @settings(max_examples=100, deadline=None)
    def test_delete_succeeds_when_no_active_sessions(self, rate):
        """
        For any vehicle type that has zero active sessions, deleting that type
        SHALL succeed and the type SHALL no longer exist in the database.
        """
        with app.app_context():
            db.create_all()
            try:
                with app.test_client() as client:
                    # Create vehicle type
                    create_response = client.post(
                        '/api/vehicle-types',
                        json=rate,
                        content_type='application/json'
                    )
                    assert create_response.status_code == 201
                    created_id = create_response.get_json()['id']
                    
                    # Delete - should succeed (no active sessions)
                    delete_response = client.delete(f'/api/vehicle-types/{created_id}')
                    assert delete_response.status_code == 200
                    
                    # Verify type no longer exists
                    list_response = client.get('/api/vehicle-types')
                    data = list_response.get_json()
                    found = any(item['id'] == created_id for item in data)
                    assert not found, "Vehicle type should not exist after successful delete"
            finally:
                db.session.rollback()
                db.drop_all()

    # **Feature: parking-enhancements, Property 4: Delete Success for Inactive Types**
    # **Validates: Requirements 1.4, 1.5**
    @given(rate=rate_data(), plate=st.text(
        alphabet=string.ascii_uppercase + string.digits,
        min_size=3,
        max_size=10
    ).filter(lambda x: len(x) >= 3))
    @settings(max_examples=100, deadline=None)
    def test_delete_succeeds_when_only_completed_sessions(self, rate, plate):
        """
        For any vehicle type that has only completed sessions (exit_time IS NOT NULL),
        deleting that type SHALL succeed.
        """
        with app.app_context():
            db.create_all()
            try:
                with app.test_client() as client:
                    # Create vehicle type
                    create_response = client.post(
                        '/api/vehicle-types',
                        json=rate,
                        content_type='application/json'
                    )
                    assert create_response.status_code == 201
                    created_id = create_response.get_json()['id']
                    
                    # Create a completed session for this vehicle type
                    import uuid
                    from datetime import datetime, timedelta
                    now = datetime.now()
                    completed_session = Session(
                        token=str(uuid.uuid4()),
                        plate=plate,
                        vehicle_type=rate['vehicle_type'],
                        entry_time=now - timedelta(hours=2),
                        exit_time=now,  # Completed session
                        amount_paid=20.0
                    )
                    db.session.add(completed_session)
                    db.session.commit()
                    
                    # Delete - should succeed (no active sessions)
                    delete_response = client.delete(f'/api/vehicle-types/{created_id}')
                    assert delete_response.status_code == 200
                    
                    # Verify type no longer exists
                    list_response = client.get('/api/vehicle-types')
                    data = list_response.get_json()
                    found = any(item['id'] == created_id for item in data)
                    assert not found, "Vehicle type should not exist after successful delete"
            finally:
                db.session.rollback()
                db.drop_all()


# Import string for strategies
import string
