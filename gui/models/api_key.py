"""
Secure API key management using the OS credential store.

Uses the `keyring` library which maps to:
  - Windows: Credential Manager
  - macOS: Keychain
  - Linux: Secret Service (GNOME Keyring / KWallet)

Falls back to a simple obfuscated file if keyring is unavailable.
"""

import base64
import json
from pathlib import Path
from typing import Optional

SERVICE_NAME = "BudgetBuddy"
KEY_NAME = "anthropic_api_key"


def _get_fallback_path() -> Path:
    """Return path for the fallback credential file."""
    return Path.home() / ".budgetbuddy" / "credentials"


def save_api_key(api_key: str) -> bool:
    """Save the API key securely. Returns True on success."""
    try:
        import keyring
        keyring.set_password(SERVICE_NAME, KEY_NAME, api_key)
        return True
    except Exception:
        # Fallback: base64-encoded file in user home (not great, but better than plaintext config.json)
        try:
            path = _get_fallback_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            encoded = base64.b64encode(api_key.encode()).decode()
            path.write_text(json.dumps({"k": encoded}))
            return True
        except Exception:
            return False


def load_api_key() -> Optional[str]:
    """Load the API key from secure storage. Returns None if not set."""
    # Try keyring first
    try:
        import keyring
        key = keyring.get_password(SERVICE_NAME, KEY_NAME)
        if key:
            return key
    except Exception:
        pass

    # Fallback file
    try:
        path = _get_fallback_path()
        if path.exists():
            data = json.loads(path.read_text())
            return base64.b64decode(data["k"]).decode()
    except Exception:
        pass

    # Legacy: try config.json in common locations
    return None


def delete_api_key() -> bool:
    """Remove the stored API key. Returns True on success."""
    removed = False

    try:
        import keyring
        keyring.delete_password(SERVICE_NAME, KEY_NAME)
        removed = True
    except Exception:
        pass

    try:
        path = _get_fallback_path()
        if path.exists():
            path.unlink()
            removed = True
    except Exception:
        pass

    return removed


def mask_api_key(api_key: str) -> str:
    """Return a masked version of the key for display: sk-ant-...xxxx"""
    if not api_key or len(api_key) < 12:
        return "***"
    return api_key[:7] + "..." + api_key[-4:]


def has_api_key() -> bool:
    """Quick check whether an API key is configured."""
    return load_api_key() is not None
