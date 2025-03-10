class FloValidationException(Exception):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)


class FloIllegalStateException(Exception):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)
