class MasterConfigError(Exception):
    """Base exception for all Master Config Client errors."""
    pass

class AuthenticationError(MasterConfigError):
    """Raised when API authentication fails (401)."""
    pass

class AuthorizationError(MasterConfigError):
    """Raised when the user lacks required permissions (403)."""
    pass

class FileTooLargeError(MasterConfigError):
    """Raised when an uploaded file exceeds the maximum allowed size (413)."""
    pass

class SchemaValidationError(MasterConfigError):
    """Raised when a file fails schema validation (422)."""
    pass

class FileNotFoundError(MasterConfigError):
    """Raised when a requested file or component is not found (404)."""
    pass

class ApiError(MasterConfigError):
    """Raised for general API errors (500+)."""
    pass
