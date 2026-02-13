import json
import typing

# class ValidationError(Exception):
#
#     def __init__(self, message, code=None, params=None):
#         super().__init__(message)
#         self.message = message
#         self.code = code
#         self.params = params
#
#     def to_dict(self):
#         return {
#             "error_class": self.__class__.__name__,
#             "message": self.message,
#             "code": self.code,
#             "params": self.params,
#         }


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

    def errors(self) -> list[dict]:
        return self._errors

    def error_count(self) -> int:
        return len(self._errors)

    def json(self) -> str:
        return json.dumps({"detail": "Validation failed", "errors": self._errors})

    def dict(self) -> dict:
        return {"detail": "Validation failed", "errors": self._errors}
