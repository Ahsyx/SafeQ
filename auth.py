import json, os, hashlib

USERS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "users.json")

def _hash(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def _load() -> dict:
    if not os.path.exists(USERS_FILE):
        return {}
    try:
        with open(USERS_FILE) as f:
            return json.load(f)
    except Exception:
        return {}

def _save(users: dict):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)

def signup(username: str, password: str, reg_number: str, vehicle_type: str) -> tuple[bool, str]:
    """
    Register a new user.
    Returns (success, message)
    """
    users = _load()
    username = username.strip().lower()

    if not username or not password or not reg_number:
        return False, "All fields are required."
    if len(password) < 6:
        return False, "Password must be at least 6 characters."
    if username in users:
        return False, "Username already exists. Please log in."

    users[username] = {
        "password":     _hash(password),
        "reg_number":   reg_number.upper(),
        "vehicle_type": vehicle_type,
        "name":         username
    }
    _save(users)
    return True, "Account created successfully!"

def login(username: str, password: str) -> tuple[bool, dict | str]:
    """
    Authenticate a user.
    Returns (success, user_data or error_message)
    """
    users = _load()
    username = username.strip().lower()

    if username not in users:
        return False, "Username not found."
    if users[username]["password"] != _hash(password):
        return False, "Incorrect password."

    return True, users[username]