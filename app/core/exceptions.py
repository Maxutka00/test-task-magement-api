class AppError(Exception):
    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class BadRequestError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(message, 400)


class UnauthorizedError(AppError):
    def __init__(self, message: str = "Could not validate credentials") -> None:
        super().__init__(message, 401)


class ForbiddenError(AppError):
    def __init__(self, message: str = "Insufficient permissions") -> None:
        super().__init__(message, 403)


class NotFoundError(AppError):
    def __init__(self, message: str = "Resource not found") -> None:
        super().__init__(message, 404)


class ConflictError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(message, 409)
