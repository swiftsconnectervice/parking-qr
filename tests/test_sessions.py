"""
Property-based tests for Session Management.
"""
import pytest
import uuid
from datetime import datetime, timedelta
from hypothesis import given, settings, Phase
from hypothesis import strategies as st

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, get_active_sessions, get_active_session_by_plate
from models import db, Rate, Session
from tests.strategies import vehicle_type_names, hourly_rates, license_plates, rate_data


# Configure app for testing once
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
app.config['TESTING'] = True


class TestActiveSessionsFilter:
    """Tests for active sessions filter functionality."""

    # **Feature: parking-enhancements, Property 7: Active Sessions Filter**
    # **Validates: Requirements 3.2, 4.4**
    @given(
        rate=rate_data(),
        num_active=st.integers(min_value=0, max_value=10),
        num_completed=st.integers(min_value=0, max_value=10)
    )
    @settings(max_examples=100, deadline=None, phases=[Phase.generate])
    def test_get_active_sessions_returns_only_null_exit_time(self, rate, num_active, num_completed):
        """
        For any set of sessions in the database, querying active vehicles SHALL return
        exactly those sessions where exit_time IS NULL.
        """
        with app.app_context():
            db.metadata.create_all(db.engine, checkfirst=True)
            try:
                # Clean up any existing data first
                db.session.query(Session).delete()
                db.session.query(Rate).delete()
                db.session.commit()
                
                # Create vehicle type
                new_rate = Rate(
                    vehicle_type=rate['vehicle_type'],
                    hourly_rate=rate['hourly_rate']
                )
                db.session.add(new_rate)
                db.session.commit()
                
                now = datetime.now()
                active_tokens = set()
                completed_tokens = set()
                
                # Create active sessions (exit_time IS NULL)
                for i in range(num_active):
                    token = str(uuid.uuid4())
                    active_tokens.add(token)
                    session = Session(
                        token=token,
                        plate=f"ACTIVE{i:03d}",
                        vehicle_type=rate['vehicle_type'],
                        entry_time=now - timedelta(hours=i+1),
                        exit_time=None  # Active session
                    )
                    db.session.add(session)
                
                # Create completed sessions (exit_time IS NOT NULL)
                for i in range(num_completed):
                    token = str(uuid.uuid4())
                    completed_tokens.add(token)
                    session = Session(
                        token=token,
                        plate=f"DONE{i:03d}",
                        vehicle_type=rate['vehicle_type'],
                        entry_time=now - timedelta(hours=i+3),
                        exit_time=now - timedelta(hours=1),  # Completed session
                        amount_paid=10.0 * (i + 1)
                    )
                    db.session.add(session)
                
                db.session.commit()
                
                # Query active sessions using helper function
                active_sessions = get_active_sessions().all()
                
                # Verify count matches expected active sessions
                assert len(active_sessions) == num_active, \
                    f"Expected {num_active} active sessions, got {len(active_sessions)}"
                
                # Verify all returned sessions have exit_time IS NULL
                for session in active_sessions:
                    assert session.exit_time is None, \
                        f"Session {session.token} has exit_time {session.exit_time}, expected NULL"
                
                # Verify all active tokens are in the result
                returned_tokens = {s.token for s in active_sessions}
                assert returned_tokens == active_tokens, \
                    f"Returned tokens {returned_tokens} should match active tokens {active_tokens}"
                
                # Verify no completed tokens are in the result
                for token in completed_tokens:
                    assert token not in returned_tokens, \
                        f"Completed session {token} should not be in active sessions"
                
            finally:
                db.session.rollback()
                db.session.query(Session).delete()
                db.session.query(Rate).delete()
                db.session.commit()

    # **Feature: parking-enhancements, Property 7: Active Sessions Filter**
    # **Validates: Requirements 3.2, 4.4**
    @given(
        rate=rate_data(),
        plate=license_plates
    )
    @settings(max_examples=100, deadline=None, phases=[Phase.generate])
    def test_get_active_session_by_plate_returns_correct_session(self, rate, plate):
        """
        For any plate with an active session, get_active_session_by_plate SHALL return
        that session. For plates without active sessions, it SHALL return None.
        """
        with app.app_context():
            db.metadata.create_all(db.engine, checkfirst=True)
            try:
                # Clean up any existing data first
                db.session.query(Session).delete()
                db.session.query(Rate).delete()
                db.session.commit()
                
                # Create vehicle type
                new_rate = Rate(
                    vehicle_type=rate['vehicle_type'],
                    hourly_rate=rate['hourly_rate']
                )
                db.session.add(new_rate)
                db.session.commit()
                
                now = datetime.now()
                
                # Create an active session with the given plate
                active_token = str(uuid.uuid4())
                active_session = Session(
                    token=active_token,
                    plate=plate,
                    vehicle_type=rate['vehicle_type'],
                    entry_time=now - timedelta(hours=2),
                    exit_time=None
                )
                db.session.add(active_session)
                db.session.commit()
                
                # Query by plate - should find the active session
                result = get_active_session_by_plate(plate)
                
                assert result is not None, \
                    f"Should find active session for plate {plate}"
                assert result.token == active_token, \
                    f"Should return correct session token"
                assert result.plate == plate, \
                    f"Should return session with correct plate"
                assert result.exit_time is None, \
                    f"Returned session should have NULL exit_time"
                
            finally:
                db.session.rollback()
                db.session.query(Session).delete()
                db.session.query(Rate).delete()
                db.session.commit()

    # **Feature: parking-enhancements, Property 7: Active Sessions Filter**
    # **Validates: Requirements 3.2, 4.4**
    @given(
        rate=rate_data(),
        plate=license_plates
    )
    @settings(max_examples=100, deadline=None, phases=[Phase.generate])
    def test_get_active_session_by_plate_ignores_completed(self, rate, plate):
        """
        For any plate with only completed sessions, get_active_session_by_plate
        SHALL return None.
        """
        with app.app_context():
            db.metadata.create_all(db.engine, checkfirst=True)
            try:
                # Clean up any existing data first
                db.session.query(Session).delete()
                db.session.query(Rate).delete()
                db.session.commit()
                
                # Create vehicle type
                new_rate = Rate(
                    vehicle_type=rate['vehicle_type'],
                    hourly_rate=rate['hourly_rate']
                )
                db.session.add(new_rate)
                db.session.commit()
                
                now = datetime.now()
                
                # Create a completed session with the given plate
                completed_session = Session(
                    token=str(uuid.uuid4()),
                    plate=plate,
                    vehicle_type=rate['vehicle_type'],
                    entry_time=now - timedelta(hours=3),
                    exit_time=now - timedelta(hours=1),  # Completed
                    amount_paid=20.0
                )
                db.session.add(completed_session)
                db.session.commit()
                
                # Query by plate - should NOT find the completed session
                result = get_active_session_by_plate(plate)
                
                assert result is None, \
                    f"Should not find completed session for plate {plate}"
                
            finally:
                db.session.rollback()
                db.session.query(Session).delete()
                db.session.query(Rate).delete()
                db.session.commit()

    # **Feature: parking-enhancements, Property 7: Active Sessions Filter**
    # **Validates: Requirements 3.2, 4.4**
    @given(plate=license_plates)
    @settings(max_examples=100, deadline=None, phases=[Phase.generate])
    def test_get_active_session_by_plate_returns_none_for_nonexistent(self, plate):
        """
        For any plate that has no sessions at all, get_active_session_by_plate
        SHALL return None.
        """
        with app.app_context():
            db.metadata.create_all(db.engine, checkfirst=True)
            try:
                # Clean up any existing data first
                db.session.query(Session).delete()
                db.session.query(Rate).delete()
                db.session.commit()
                
                # Query by plate with no sessions in database
                result = get_active_session_by_plate(plate)
                
                assert result is None, \
                    f"Should return None for non-existent plate {plate}"
                
            finally:
                db.session.rollback()



class TestSessionCompletionPersistence:
    """Tests for session completion persistence."""

    # **Feature: parking-enhancements, Property 8: Session Completion Persistence**
    # **Validates: Requirements 2.4, 3.1, 3.3**
    @given(
        rate=rate_data(),
        plate=license_plates,
        hours_ago=st.floats(min_value=0.1, max_value=24.0, allow_nan=False, allow_infinity=False)
    )
    @settings(max_examples=100, deadline=None, phases=[Phase.generate])
    def test_session_completion_persists_record(self, rate, plate, hours_ago):
        """
        For any session that is closed via the exit endpoint, the session record
        SHALL remain in the database with non-null exit_time and amount_paid.
        """
        with app.app_context():
            db.metadata.create_all(db.engine, checkfirst=True)
            try:
                # Clean up any existing data first
                db.session.query(Session).delete()
                db.session.query(Rate).delete()
                db.session.commit()
                
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
                    # Close the session via exit endpoint
                    response = client.post('/api/exit', json={'token': token})
                    assert response.status_code == 200
                    
                    exit_data = response.get_json()
                    assert 'amount_paid' in exit_data
                    
                    # Verify session still exists in database
                    persisted_session = Session.query.get(token)
                    
                    assert persisted_session is not None, \
                        f"Session {token} should still exist after exit"
                    
                    # Verify exit_time is set (not NULL)
                    assert persisted_session.exit_time is not None, \
                        f"Session {token} should have non-null exit_time"
                    
                    # Verify amount_paid is set (not NULL)
                    assert persisted_session.amount_paid is not None, \
                        f"Session {token} should have non-null amount_paid"
                    
                    # Verify amount_paid matches what was returned
                    assert persisted_session.amount_paid == exit_data['amount_paid'], \
                        f"Persisted amount {persisted_session.amount_paid} should match returned {exit_data['amount_paid']}"
                    
                    # Verify original data is preserved
                    assert persisted_session.plate == plate, \
                        f"Plate should be preserved"
                    assert persisted_session.vehicle_type == rate['vehicle_type'], \
                        f"Vehicle type should be preserved"
                    
            finally:
                db.session.rollback()
                db.session.query(Session).delete()
                db.session.query(Rate).delete()
                db.session.commit()

    # **Feature: parking-enhancements, Property 8: Session Completion Persistence**
    # **Validates: Requirements 2.4, 3.1, 3.3**
    @given(
        rate=rate_data(),
        plate=license_plates,
        hours_ago=st.floats(min_value=0.1, max_value=24.0, allow_nan=False, allow_infinity=False)
    )
    @settings(max_examples=100, deadline=None, phases=[Phase.generate])
    def test_completed_session_not_in_active_list(self, rate, plate, hours_ago):
        """
        For any session that is closed, it SHALL no longer appear in the active
        sessions list but SHALL remain in the database for historical reporting.
        """
        with app.app_context():
            db.metadata.create_all(db.engine, checkfirst=True)
            try:
                # Clean up any existing data first
                db.session.query(Session).delete()
                db.session.query(Rate).delete()
                db.session.commit()
                
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
                
                # Verify session is in active list before exit
                active_before = get_active_sessions().all()
                active_tokens_before = {s.token for s in active_before}
                assert token in active_tokens_before, \
                    f"Session {token} should be in active list before exit"
                
                with app.test_client() as client:
                    # Close the session
                    response = client.post('/api/exit', json={'token': token})
                    assert response.status_code == 200
                
                # Verify session is NOT in active list after exit
                active_after = get_active_sessions().all()
                active_tokens_after = {s.token for s in active_after}
                assert token not in active_tokens_after, \
                    f"Session {token} should NOT be in active list after exit"
                
                # Verify session still exists in database (for historical reporting)
                persisted_session = Session.query.get(token)
                assert persisted_session is not None, \
                    f"Session {token} should still exist in database for historical reporting"
                
            finally:
                db.session.rollback()
                db.session.query(Session).delete()
                db.session.query(Rate).delete()
                db.session.commit()

    # **Feature: parking-enhancements, Property 8: Session Completion Persistence**
    # **Validates: Requirements 2.4, 3.1, 3.3**
    @given(
        rate=rate_data(),
        plate=license_plates,
        hours_ago=st.floats(min_value=0.1, max_value=24.0, allow_nan=False, allow_infinity=False)
    )
    @settings(max_examples=100, deadline=None, phases=[Phase.generate])
    def test_exit_time_is_after_entry_time(self, rate, plate, hours_ago):
        """
        For any completed session, the exit_time SHALL be after the entry_time.
        """
        with app.app_context():
            db.metadata.create_all(db.engine, checkfirst=True)
            try:
                # Clean up any existing data first
                db.session.query(Session).delete()
                db.session.query(Rate).delete()
                db.session.commit()
                
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
                    # Close the session
                    response = client.post('/api/exit', json={'token': token})
                    assert response.status_code == 200
                
                # Verify exit_time > entry_time
                persisted_session = Session.query.get(token)
                assert persisted_session.exit_time > persisted_session.entry_time, \
                    f"Exit time {persisted_session.exit_time} should be after entry time {persisted_session.entry_time}"
                
            finally:
                db.session.rollback()
                db.session.query(Session).delete()
                db.session.query(Rate).delete()
                db.session.commit()
