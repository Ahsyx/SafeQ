# ==========================================
# 📋 MOCK VAHAN DATABASE (Simulated API)
# ==========================================

# This simulates the Government's Vehicle Registry
# We map Registration Numbers to Vehicle Categories
VEHICLE_REGISTRY = {
    "KL-07-AW-1234": "Ambulance 🚑 (Responding/Empty)",  # updated to match new dual-mode profile
    "KL-07-AW-5678": "Ambulance 🚑 (Responding/Empty)",  # second ambulance for testing
    "KL-40-Q-9999":  "Two-Wheeler",
    "KL-01-BT-5555": "School Bus",
    "KL-39-Z-1111":  "Heavy Truck",
    "KL-07-CC-0007": "Standard Car"
}

def verify_vehicle(reg_number):
    """
    Simulates a VAHAN API Call to verify vehicle type.
    In production, this would call a real Govt API.
    """
    # Clean the input: remove spaces/dashes and make uppercase
    clean_reg = reg_number.replace(" ", "").replace("-", "").upper()

    # Check our mock database
    for key, v_type in VEHICLE_REGISTRY.items():
        if key.replace("-", "") == clean_reg:
            return v_type

    # Unknown registration → treat as Standard Car
    return "Standard Car"