class AuthError(Exception):
    """Base auth error"""


class UserAlreadyExists(AuthError):
    pass


class InvalidCredentials(AuthError):
    pass


class InactiveUserException(AuthError):
    pass


class IncorrectEmailOrPasswordException(AuthError):
    pass


class AppException(Exception):
    """Базовое доменное исключение"""

    pass


class NotFoundException(AppException):
    pass


class InvalidPageException(AppException):
    pass
