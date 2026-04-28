class WahaError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class WahaAuthError(WahaError):
    """Invalid or missing WAHA API key."""


class WahaSessionNotFoundError(WahaError):
    """Session does not exist in WAHA."""


class WahaSessionNotReadyError(WahaError):
    """Session exists but did not reach WORKING state in time."""
    def __init__(self, session_name: str, current_status: str):
        self.session_name = session_name
        self.current_status = current_status
        super().__init__(f"Session '{session_name}' not ready: status={current_status}")


class WahaRePairingRequiredError(WahaError):
    """Session reached SCAN_QR_CODE during a sync — user must re-scan QR."""
    def __init__(self, session_name: str):
        self.session_name = session_name
        super().__init__(f"Re-pairing required for session '{session_name}'")
