class BooruException(Exception):
    """Base exception for booru operations."""

    pass


class SourceNotFound(BooruException):
    """Raised when a booru source is not found."""

    pass


class CredentialsRequired(BooruException):
    """Raised when credentials are required but not provided."""

    pass


class RequestError(BooruException):
    """Raised when a request to a booru site fails."""

    pass


class PostParseError(BooruException):
    """Raised when post data cannot be parsed."""

    pass


class InvalidAPIKey(BooruException):
    """Raised when an invalid API key is provided."""

    pass


class RateLimitExceeded(BooruException):
    """Raised when the rate limit for API requests is exceeded."""

    pass


class InvalidResponse(BooruException):
    """Raised when the response from the server is invalid or malformed."""

    pass


class UnauthorizedAccess(BooruException):
    """Raised when access to a resource is denied due to insufficient permissions."""

    pass


class NetworkError(BooruException):
    """Raised when a network-related error occurs during a request."""

    pass


class TimeoutError(BooruException):
    """Raised when a request times out."""

    pass


class InvalidTag(BooruException):
    """Raised when an invalid tag is provided."""

    pass


class ServerError(BooruException):
    """Raised when the server encounters an internal error."""

    pass
