import json
import typing


class ValidationError(Exception):

    def __init__(
        self,
        message: str = None,
        errors: typing.List[typing.Dict[str, typing.Any]] = None,
        field: typing.Optional[str] = None,
        value: typing.Any = None,
        params: typing.Dict[str, typing.Any] = None,
    ):
        if errors:
            # Multi-error mode
            self._errors = errors
            self.fail_fast = False
            message = self._format_multi_error()
        else:
            if params is None:
                params = {}
            self._errors = [
                {"field": field, "message": message, "input": value, **params}
            ]
            self.fail_fast = True

        super().__init__(message)

    def _format_multi_error(self) -> str:
        lines = [f"Validation failed with {len(self._errors)} errors:"]
        for err in self._errors:
            lines.append(f"  {err['field']}: {err['message']}")
        return "\n".join(lines)

    def errors(self) -> typing.List[typing.Dict[str, typing.Any]]:
        return self._errors

    def error_count(self) -> int:
        return len(self._errors)

    def json(self) -> str:
        return json.dumps({"detail": "Validation failed", "errors": self._errors})

    def dict(self) -> typing.Dict[str, typing.Any]:
        return {"detail": "Validation failed", "errors": self._errors}


class ValidationErrorCollector:
    """Collects validation errors during schema mode validation."""

    def __init__(self):
        self.errors: typing.List[typing.Dict[str, typing.Any]] = []

    def add_error(
        self,
        field: str,
        message: str,
        value: typing.Any,
        location: typing.List[str] = None,
        params: typing.Optional[typing.Dict[str, typing.Any]] = None,
    ):
        if params is None:
            params = {}

        self.errors.append(
            {
                "field": field,
                "message": message,
                "input": value,
                "location": location or [field],
                **params,
            }
        )

    def has_errors(self) -> bool:
        """Check if any errors were collected."""
        return len(self.errors) > 0

    def raise_if_errors(self):
        """Raise ValidationError if any errors collected."""
        if self.has_errors():
            raise ValidationError(errors=self.errors)
