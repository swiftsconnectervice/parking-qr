"""
Hypothesis strategies for generating test data for parking system.
"""
from hypothesis import strategies as st
import string


# Vehicle type name strategy - alphanumeric strings between 2-30 chars
vehicle_type_names = st.text(
    alphabet=string.ascii_letters + string.digits + ' ',
    min_size=2,
    max_size=30
).map(str.strip).filter(lambda x: len(x) >= 2)

# Hourly rate strategy - positive floats between 0.01 and 1000
hourly_rates = st.floats(
    min_value=0.01,
    max_value=1000.0,
    allow_nan=False,
    allow_infinity=False
).map(lambda x: round(x, 2))

# License plate strategy - uppercase alphanumeric 3-10 chars
license_plates = st.text(
    alphabet=string.ascii_uppercase + string.digits,
    min_size=3,
    max_size=10
).filter(lambda x: len(x) >= 3)

# Token strategy - UUID-like strings
tokens = st.uuids().map(str)

# Duration in hours strategy - positive floats for parking duration
duration_hours = st.floats(
    min_value=0.01,
    max_value=168.0,  # Max 1 week
    allow_nan=False,
    allow_infinity=False
)


@st.composite
def rate_data(draw):
    """Generate valid Rate data as a dictionary."""
    return {
        'vehicle_type': draw(vehicle_type_names),
        'hourly_rate': draw(hourly_rates)
    }


@st.composite
def session_data(draw, vehicle_types=None):
    """Generate valid Session data as a dictionary."""
    if vehicle_types:
        vtype = draw(st.sampled_from(vehicle_types))
    else:
        vtype = draw(vehicle_type_names)
    
    return {
        'token': draw(tokens),
        'plate': draw(license_plates),
        'vehicle_type': vtype
    }
