"""Melipayamak session manager for 2FA login"""

import os
import pickle
from datetime import datetime, timedelta
from zeep import Client
from zeep.transports import Transport
from requests import Session


class MelipayamakSession:
    """Manage Melipayamak session with 2FA"""

    def __init__(self, session_file="melipayamak_session.pkl"):
        # Put session file in the same directory as the script or a known path
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.session_file = os.path.join(base_dir, session_file)
        self.session = None
        self.client = None
        self.session_data = None
        self.load_session()

    def load_session(self):
        """Load existing session if available"""
        try:
            if os.path.exists(self.session_file):
                with open(self.session_file, "rb") as f:
                    self.session_data = pickle.load(f)

                # Check if session is still valid (24 hours)
                if self.is_session_valid():
                    self.session = Session()
                    if self.session_data.get("session_cookies"):
                        self.session.cookies.update(self.session_data["session_cookies"])
                    
                    self.client = Client(
                        "https://api.payamak-panel.com/post/Send.asmx?wsdl",
                        transport=Transport(session=self.session),
                    )
                    print(f"Session loaded from cache: {self.session_file}")
                    return True
                else:
                    print("Session expired, will need new login")
                    self.session_data = None
                    return False
        except Exception as e:
            print(f"Error loading session: {e}")
            self.session_data = None
            return False

        return False

    def is_session_valid(self):
        """Check if session is still valid"""
        if not self.session_data:
            return False

        created_at = self.session_data.get("created_at")
        if not created_at:
            return False

        # Session valid for 24 hours
        return datetime.now() - created_at < timedelta(hours=24)

    def save_session(self, username, session_cookies=None):
        """Save session data"""
        try:
            self.session_data = {
                "username": username,
                "created_at": datetime.now(),
                "session_cookies": session_cookies or {},
            }

            with open(self.session_file, "wb") as f:
                pickle.dump(self.session_data, f)

            print("Session saved successfully")
            return True
        except Exception as e:
            print(f"Error saving session: {e}")
            return False

    def login_with_code(self, username, password, code=None):
        """Login with 2FA code"""
        try:
            # Create new session
            self.session = Session()

            # First attempt without code
            transport = Transport(session=self.session)
            temp_client = Client(
                "https://api.payamak-panel.com/post/Send.asmx?wsdl", transport=transport
            )

            # Try to get credit (this will trigger 2FA if needed)
            try:
                temp_client.service.GetCredit(username=username, password=password)

                # If we get here, no 2FA needed
                self.client = temp_client
                self.save_session(username, self.session.cookies.get_dict())
                return True, "Login successful (no 2FA needed)"

            except Exception as e:
                error_str = str(e)
                print(f"First login attempt error: {error_str}")

                # Check if 2FA is required
                if (
                    "code" in error_str.lower()
                    or "verification" in error_str.lower()
                    or "2fa" in error_str.lower()
                ):
                    if not code:
                        return False, "2FA code required. Please provide the code."

                    # Try again with code
                    try:
                        # Add code to session or headers
                        # Note: The implementation of how 2FA code is sent might vary
                        # This follows the user's provided logic
                        self.session.headers.update({"X-2FA-Code": code})

                        # Create new client with code
                        transport = Transport(session=self.session)
                        self.client = Client(
                            "https://api.payamak-panel.com/post/Send.asmx?wsdl",
                            transport=transport,
                        )

                        # Test with code
                        self.client.service.GetCredit(
                            username=username, password=password
                        )

                        # If successful, save session
                        self.save_session(username, self.session.cookies.get_dict())
                        return True, "Login successful with 2FA"

                    except Exception as e2:
                        return False, f"2FA login failed: {str(e2)}"
                else:
                    return False, f"Login failed: {error_str}"

        except Exception as e:
            return False, f"Session creation failed: {str(e)}"

    def get_client(self):
        """Get the authenticated client"""
        return self.client

    def clear_session(self):
        """Clear saved session"""
        try:
            if os.path.exists(self.session_file):
                os.remove(self.session_file)
            self.session_data = None
            self.client = None
            self.session = None
            print("Session cleared")
            return True
        except Exception as e:
            print(f"Error clearing session: {e}")
            return False


# Global session manager
session_manager = MelipayamakSession()


def setup_melipayamak_session(username, password, code=None):
    """Setup Melipayamak session with 2FA support"""
    global session_manager

    # Try to use existing session
    if session_manager.is_session_valid() and session_manager.get_client():
        return True, session_manager.get_client()

    # Need new login
    success, message = session_manager.login_with_code(username, password, code)

    if success:
        return True, session_manager.get_client()
    else:
        return False, message


def clear_melipayamak_session():
    """Clear Melipayamak session"""
    global session_manager
    return session_manager.clear_session()
