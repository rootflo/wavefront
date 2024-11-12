class FloException(Exception):
    def __init__(self, message: str, error_code: int = -1):
        """
        Initialize the FloException with a message and optional error code.

        :param message: Error message to be displayed.
        :param error_code: Optional error code to be associated with the exception.
        """
        self.message = message
        self.error_code = error_code
        super().__init__(message)

    def __str__(self):
        if self.error_code is not None:
            return f'[Error {self.error_code}] {self.message}'
        return self.message
