"""
Property-based tests for Dashboard API.
"""
import pytest
import uuid
from datetime import datetime, timedelta, date
from hypothesis import given, settings, assume, Phase
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


# Strategy for generating a list of sessions with controlled entry/exit dates
@st.composite
def sessions_for_date(draw, target_date):
    """Generate a list of sessions with entries and exits on specific dates."""
    num_sessions = draw(st.integers(min_value=0, max_value=10))
    sessions = []
    
    for _ in range(num_sessions):
        # Decide if entry is on target date or another date
        entry_on_target = draw(st.booleans())
        if entry_on_target:
            entry_hour = draw(st.integers(min_value=0, max_value=23))
            entry_time = datetime.combine(target_date, datetime.min.time()) + timedelta(hours=entry_hour)
        else:
            # Entry on a different date (1-5 days before)
            days_before = draw(st.integers(min_value=1, max_value=5))
            entry_hour = draw(st.integers(min_value=0, max_value=23))
            entry_time = datetime.combine(target_date - timedelta(days=days_before), datetime.min.time()) + timedelta(hours=entry_hour)
        
        # Decide if session is completed or active
        is_completed = draw(st.booleans())
        exit_time = None
        amount_paid = None
        
        if is_completed:
            # Decide if exit is on target date or another date
            exit_on_target = draw(st.booleans())
            if exit_on_target:
                exit_hour = draw(st.integers(min_value=0, max_value=23))
                exit_time = datetime.combine(target_date, datetime.min.time()) + timedelta(hours=exit_hour)
            else:
                # Exit on a different date (0-3 days after entry, but not target date)
                days_after = draw(st.integers(min_value=0, max_value=3))
                exit_date = entry_time.date() + timedelta(days=days_after)
                if exit_date == target_date:
                    exit_date = target_date + timedelta(days=1)
                exit_hour = draw(st.integers(min_value=0, max_value=23))
                exit_time = datetime.combine(exit_date, datetime.min.time()) + timedelta(hours=exit_hour)
            
            # Ensure exit is after entry
            if exit_time <= entry_time:
                exit_time = entry_time + timedelta(hours=1)
            
            amount_paid = round(draw(st.floats(min_value=1.0, max_value=500.0, allow_nan=False, allow_infinity=False)), 2)
        
        sessions.append({
            'entry_time': entry_time,
            'exit_time': exit_time,
            'amount_paid': amount_paid
        })
    
    return sessions


class TestDashboardStatistics:
    """Tests for GET /api/dashboard endpoint."""

    # **Feature: parking-enhancements, Property 9: Dashboard Statistics Accuracy**
    # **Validates: Requirements 4.1, 4.2, 4.3, 4.6**
    @given(
        rate=rate_data(),
        days_offset=st.integers(min_value=-30, max_value=30),
        data=st.data()
    )
    @settings(max_examples=100, deadline=None, phases=[Phase.generate])
    def test_dashboard_statistics_accuracy(self, rate, days_offset, data):
        """
        For any date, the dashboard statistics SHALL correctly report:
        - entries count equals sessions with entry_time on that date
        - exits count equals sessions with exit_time on that date
        - total revenue equals sum of amount_paid for sessions exited on that date
        """
        target_date = date.today() + timedelta(days=days_offset)
        sessions_data = data.draw(sessions_for_date(target_date))
        
        with app.app_context():
            db.metadata.create_all(db.engine, checkfirst=True)
            try:
                # Create vehicle type
                new_rate = Rate(
                    vehicle_type=rate['vehicle_type'],
                    hourly_rate=rate['hourly_rate']
                )
                db.session.add(new_rate)
                db.session.commit()
                
                # Create sessions
                created_sessions = []
                for i, s_data in enumerate(sessions_data):
                    session = Session(
                        token=str(uuid.uuid4()),
                        plate=f"TEST{i:03d}",
                        vehicle_type=rate['vehicle_type'],
                        entry_time=s_data['entry_time'],
                        exit_time=s_data['exit_time'],
                        amount_paid=s_data['amount_paid']
                    )
                    db.session.add(session)
                    created_sessions.append(session)
                db.session.commit()
                
                # Calculate expected values
                expected_entries = sum(
                    1 for s in sessions_data 
                    if s['entry_time'].date() == target_date
                )
                expected_exits = sum(
                    1 for s in sessions_data 
                    if s['exit_time'] is not None and s['exit_time'].date() == target_date
                )
                expected_revenue = round(sum(
                    s['amount_paid'] for s in sessions_data 
                    if s['exit_time'] is not None and s['exit_time'].date() == target_date
                ), 2)
                
                with app.test_client() as client:
                    # Query dashboard for target date
                    response = client.get(f'/api/dashboard?date={target_date.isoformat()}')
                    assert response.status_code == 200
                    
                    data_resp = response.get_json()
                    
                    # Verify date
                    assert data_resp['date'] == target_date.isoformat()
                    
                    # Verify entries count
                    assert data_resp['entries_count'] == expected_entries, \
                        f"Expected {expected_entries} entries, got {data_resp['entries_count']}"
                    
                    # Verify exits count
                    assert data_resp['exits_count'] == expected_exits, \
                        f"Expected {expected_exits} exits, got {data_resp['exits_count']}"
                    
                    # Verify total revenue
                    assert abs(data_resp['total_revenue'] - expected_revenue) < 0.01, \
                        f"Expected revenue {expected_revenue}, got {data_resp['total_revenue']}"
                    
            finally:
                db.session.rollback()
                db.session.query(Session).delete()
                db.session.query(Rate).delete()
                db.session.commit()

    # **Feature: parking-enhancements, Property 9: Dashboard Statistics Accuracy**
    # **Validates: Requirements 4.4**
    @given(
        rate=rate_data(),
        num_active=st.integers(min_value=0, max_value=5),
        num_completed=st.integers(min_value=0, max_value=5)
    )
    @settings(max_examples=100, deadline=None, phases=[Phase.generate])
    def test_dashboard_active_vehicles_list(self, rate, num_active, num_completed):
        """
        The dashboard SHALL display a list of currently parked vehicles
        (sessions where exit_time IS NULL).
        """
        with app.app_context():
            db.metadata.create_all(db.engine, checkfirst=True)
            try:
                # Create vehicle type
                new_rate = Rate(
                    vehicle_type=rate['vehicle_type'],
                    hourly_rate=rate['hourly_rate']
                )
                db.session.add(new_rate)
                db.session.commit()
                
                now = datetime.now()
                active_plates = []
                
                # Create active sessions
                for i in range(num_active):
                    plate = f"ACTIVE{i:03d}"
                    active_plates.append(plate)
                    session = Session(
                        token=str(uuid.uuid4()),
                        plate=plate,
                        vehicle_type=rate['vehicle_type'],
                        entry_time=now - timedelta(hours=i+1),
                        exit_time=None
                    )
                    db.session.add(session)
                
                # Create completed sessions
                for i in range(num_completed):
                    session = Session(
                        token=str(uuid.uuid4()),
                        plate=f"DONE{i:03d}",
                        vehicle_type=rate['vehicle_type'],
                        entry_time=now - timedelta(hours=i+3),
                        exit_time=now - timedelta(hours=1),
                        amount_paid=10.0 * (i + 1)
                    )
                    db.session.add(session)
                
                db.session.commit()
                
                with app.test_client() as client:
                    response = client.get('/api/dashboard')
                    assert response.status_code == 200
                    
                    data_resp = response.get_json()
                    
                    # Verify active vehicles count
                    assert len(data_resp['active_vehicles']) == num_active, \
                        f"Expected {num_active} active vehicles, got {len(data_resp['active_vehicles'])}"
                    
                    # Verify all active plates are in the list
                    returned_plates = [v['plate'] for v in data_resp['active_vehicles']]
                    for plate in active_plates:
                        assert plate in returned_plates, \
                            f"Active plate {plate} not found in response"
                    
                    # Verify completed sessions are NOT in active list
                    for i in range(num_completed):
                        assert f"DONE{i:03d}" not in returned_plates, \
                            f"Completed session DONE{i:03d} should not be in active list"
                    
            finally:
                db.session.rollback()
                db.session.query(Session).delete()
                db.session.query(Rate).delete()
                db.session.commit()

    # **Feature: parking-enhancements, Property 9: Dashboard Statistics Accuracy**
    # **Validates: Requirements 4.6**
    @given(date_str=st.text(
        alphabet=st.sampled_from('0123456789-/abcdefghijklmnopqrstuvwxyz'),
        min_size=1, 
        max_size=20
    ))
    @settings(max_examples=50, deadline=None, phases=[Phase.generate])
    def test_dashboard_invalid_date_format(self, date_str):
        """
        When an invalid date format is provided, the dashboard SHALL return an error.
        """
        # Skip valid date formats
        try:
            datetime.strptime(date_str, '%Y-%m-%d')
            assume(False)  # Skip this test case if it's a valid date
        except ValueError:
            pass  # Continue with invalid date
        
        with app.app_context():
            db.metadata.create_all(db.engine, checkfirst=True)
            try:
                with app.test_client() as client:
                    response = client.get(f'/api/dashboard?date={date_str}')
                    assert response.status_code == 400
                    
                    data_resp = response.get_json()
                    assert 'error' in data_resp
                    assert 'Invalid date format' in data_resp['error']
            finally:
                db.session.rollback()



class TestDashboardStatsByVehicleType:
    """Tests for dashboard stats grouped by vehicle type."""

    # **Feature: parking-enhancements, Property 10: Dashboard Stats by Vehicle Type**
    # **Validates: Requirements 4.5**
    @given(
        rates=st.lists(rate_data(), min_size=1, max_size=3, unique_by=lambda x: x['vehicle_type']),
        days_offset=st.integers(min_value=-10, max_value=10),
        data=st.data()
    )
    @settings(max_examples=100, deadline=None, phases=[Phase.generate])
    def test_dashboard_stats_by_vehicle_type(self, rates, days_offset, data):
        """
        For any date and vehicle type, the grouped statistics SHALL correctly
        aggregate entries, exits, and revenue for that specific vehicle type on that date.
        """
        target_date = date.today() + timedelta(days=days_offset)
        
        with app.app_context():
            db.metadata.create_all(db.engine, checkfirst=True)
            try:
                # Create vehicle types
                for rate in rates:
                    new_rate = Rate(
                        vehicle_type=rate['vehicle_type'],
                        hourly_rate=rate['hourly_rate']
                    )
                    db.session.add(new_rate)
                db.session.commit()
                
                # Track expected stats per vehicle type
                expected_stats = {rate['vehicle_type']: {'entries': 0, 'exits': 0, 'revenue': 0.0} for rate in rates}
                
                # Generate sessions for each vehicle type
                session_counter = 0
                for rate in rates:
                    vtype = rate['vehicle_type']
                    num_sessions = data.draw(st.integers(min_value=0, max_value=5))
                    
                    for _ in range(num_sessions):
                        # Decide if entry is on target date
                        entry_on_target = data.draw(st.booleans())
                        if entry_on_target:
                            entry_hour = data.draw(st.integers(min_value=0, max_value=23))
                            entry_time = datetime.combine(target_date, datetime.min.time()) + timedelta(hours=entry_hour)
                            expected_stats[vtype]['entries'] += 1
                        else:
                            days_before = data.draw(st.integers(min_value=1, max_value=5))
                            entry_hour = data.draw(st.integers(min_value=0, max_value=23))
                            entry_time = datetime.combine(target_date - timedelta(days=days_before), datetime.min.time()) + timedelta(hours=entry_hour)
                        
                        # Decide if session is completed
                        is_completed = data.draw(st.booleans())
                        exit_time = None
                        amount_paid = None
                        
                        if is_completed:
                            exit_on_target = data.draw(st.booleans())
                            if exit_on_target:
                                exit_hour = data.draw(st.integers(min_value=0, max_value=23))
                                exit_time = datetime.combine(target_date, datetime.min.time()) + timedelta(hours=exit_hour)
                            else:
                                days_after = data.draw(st.integers(min_value=0, max_value=3))
                                exit_date = entry_time.date() + timedelta(days=days_after)
                                if exit_date == target_date:
                                    exit_date = target_date + timedelta(days=1)
                                exit_hour = data.draw(st.integers(min_value=0, max_value=23))
                                exit_time = datetime.combine(exit_date, datetime.min.time()) + timedelta(hours=exit_hour)
                            
                            # Ensure exit is after entry
                            if exit_time <= entry_time:
                                exit_time = entry_time + timedelta(hours=1)
                            
                            amount_paid = round(data.draw(st.floats(min_value=1.0, max_value=100.0, allow_nan=False, allow_infinity=False)), 2)
                            
                            # Track expected exits and revenue
                            if exit_time.date() == target_date:
                                expected_stats[vtype]['exits'] += 1
                                expected_stats[vtype]['revenue'] += amount_paid
                        
                        session = Session(
                            token=str(uuid.uuid4()),
                            plate=f"TEST{session_counter:04d}",
                            vehicle_type=vtype,
                            entry_time=entry_time,
                            exit_time=exit_time,
                            amount_paid=amount_paid
                        )
                        db.session.add(session)
                        session_counter += 1
                
                db.session.commit()
                
                with app.test_client() as client:
                    response = client.get(f'/api/dashboard?date={target_date.isoformat()}')
                    assert response.status_code == 200
                    
                    data_resp = response.get_json()
                    
                    # Verify stats_by_type is present
                    assert 'stats_by_type' in data_resp
                    
                    # Build a map of returned stats
                    returned_stats = {s['vehicle_type']: s for s in data_resp['stats_by_type']}
                    
                    # Verify each vehicle type's stats
                    for vtype, expected in expected_stats.items():
                        if expected['entries'] > 0 or expected['exits'] > 0:
                            assert vtype in returned_stats, \
                                f"Vehicle type {vtype} should be in stats_by_type"
                            
                            actual = returned_stats[vtype]
                            
                            assert actual['entries'] == expected['entries'], \
                                f"Type {vtype}: expected {expected['entries']} entries, got {actual['entries']}"
                            
                            assert actual['exits'] == expected['exits'], \
                                f"Type {vtype}: expected {expected['exits']} exits, got {actual['exits']}"
                            
                            expected_revenue = round(expected['revenue'], 2)
                            assert abs(actual['revenue'] - expected_revenue) < 0.01, \
                                f"Type {vtype}: expected revenue {expected_revenue}, got {actual['revenue']}"
                    
            finally:
                db.session.rollback()
                db.session.query(Session).delete()
                db.session.query(Rate).delete()
                db.session.commit()

    # **Feature: parking-enhancements, Property 10: Dashboard Stats by Vehicle Type**
    # **Validates: Requirements 4.5**
    @given(
        rate=rate_data(),
        num_entries_today=st.integers(min_value=0, max_value=5),
        num_exits_today=st.integers(min_value=0, max_value=5)
    )
    @settings(max_examples=100, deadline=None, phases=[Phase.generate])
    def test_stats_by_type_sums_match_totals(self, rate, num_entries_today, num_exits_today):
        """
        The sum of entries/exits/revenue across all vehicle types SHALL equal
        the total entries/exits/revenue in the dashboard.
        """
        target_date = date.today()
        
        with app.app_context():
            db.metadata.create_all(db.engine, checkfirst=True)
            try:
                # Create vehicle type
                new_rate = Rate(
                    vehicle_type=rate['vehicle_type'],
                    hourly_rate=rate['hourly_rate']
                )
                db.session.add(new_rate)
                db.session.commit()
                
                now = datetime.now()
                total_revenue = 0.0
                
                # Create sessions with entries today
                for i in range(num_entries_today):
                    entry_time = datetime.combine(target_date, datetime.min.time()) + timedelta(hours=i)
                    session = Session(
                        token=str(uuid.uuid4()),
                        plate=f"ENTRY{i:03d}",
                        vehicle_type=rate['vehicle_type'],
                        entry_time=entry_time,
                        exit_time=None
                    )
                    db.session.add(session)
                
                # Create sessions with exits today (entered yesterday)
                for i in range(num_exits_today):
                    entry_time = datetime.combine(target_date - timedelta(days=1), datetime.min.time()) + timedelta(hours=i)
                    exit_time = datetime.combine(target_date, datetime.min.time()) + timedelta(hours=i+1)
                    amount = round(10.0 * (i + 1), 2)
                    total_revenue += amount
                    session = Session(
                        token=str(uuid.uuid4()),
                        plate=f"EXIT{i:03d}",
                        vehicle_type=rate['vehicle_type'],
                        entry_time=entry_time,
                        exit_time=exit_time,
                        amount_paid=amount
                    )
                    db.session.add(session)
                
                db.session.commit()
                
                with app.test_client() as client:
                    response = client.get(f'/api/dashboard?date={target_date.isoformat()}')
                    assert response.status_code == 200
                    
                    data_resp = response.get_json()
                    
                    # Sum stats from stats_by_type
                    sum_entries = sum(s['entries'] for s in data_resp['stats_by_type'])
                    sum_exits = sum(s['exits'] for s in data_resp['stats_by_type'])
                    sum_revenue = sum(s['revenue'] for s in data_resp['stats_by_type'])
                    
                    # Verify sums match totals
                    assert sum_entries == data_resp['entries_count'], \
                        f"Sum of entries by type ({sum_entries}) should equal total entries ({data_resp['entries_count']})"
                    
                    assert sum_exits == data_resp['exits_count'], \
                        f"Sum of exits by type ({sum_exits}) should equal total exits ({data_resp['exits_count']})"
                    
                    assert abs(sum_revenue - data_resp['total_revenue']) < 0.01, \
                        f"Sum of revenue by type ({sum_revenue}) should equal total revenue ({data_resp['total_revenue']})"
                    
            finally:
                db.session.rollback()
                db.session.query(Session).delete()
                db.session.query(Rate).delete()
                db.session.commit()
