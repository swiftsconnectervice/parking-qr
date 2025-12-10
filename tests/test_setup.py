"""
Basic tests to verify test infrastructure is working.
"""
import pytest
from hypothesis import given, settings
from models import Rate, Session
from tests.strategies import vehicle_type_names, hourly_rates, license_plates


def test_app_fixture_works(test_app):
    """Verify the test app fixture creates a working Flask app."""
    assert test_app is not None
    assert test_app.config['TESTING'] is True


def test_client_fixture_works(client):
    """Verify the test client can make requests."""
    response = client.get('/')
    assert response.status_code == 200


def test_sample_rate_fixture(test_app, sample_rate):
    """Verify sample_rate fixture creates a Rate record."""
    with test_app.app_context():
        rate = Rate.query.filter_by(vehicle_type='Auto').first()
        assert rate is not None
        assert rate.hourly_rate == 10.0


def test_sample_rates_fixture(test_app, sample_rates):
    """Verify sample_rates fixture creates multiple Rate records."""
    with test_app.app_context():
        rates = Rate.query.all()
        assert len(rates) == 3


def test_sample_session_fixture(test_app, sample_session):
    """Verify sample_session fixture creates a Session record."""
    with test_app.app_context():
        session = Session.query.get('test-token-123')
        assert session is not None
        assert session.plate == 'ABC123'
        assert session.exit_time is None  # Active session


@given(vehicle_type_names)
@settings(max_examples=10)
def test_vehicle_type_strategy_generates_valid_names(name):
    """Verify vehicle_type_names strategy generates valid strings."""
    assert isinstance(name, str)
    assert len(name) >= 2
    assert len(name) <= 30


@given(hourly_rates)
@settings(max_examples=10)
def test_hourly_rate_strategy_generates_valid_rates(rate):
    """Verify hourly_rates strategy generates valid floats."""
    assert isinstance(rate, float)
    assert rate >= 0.01
    assert rate <= 1000.0


@given(license_plates)
@settings(max_examples=10)
def test_license_plate_strategy_generates_valid_plates(plate):
    """Verify license_plates strategy generates valid strings."""
    assert isinstance(plate, str)
    assert len(plate) >= 3
    assert len(plate) <= 10
