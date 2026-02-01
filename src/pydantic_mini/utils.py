import typing
import logging
import inspect
from dataclasses import MISSING

from pydantic_mini.typing import is_builtin_type

logger = logging.getLogger(__name__)


T = typing.TypeVar("T")


def get_function_call_args(
    func, params: typing.Union[typing.Dict[str, typing.Any], object]
) -> typing.Dict[str, typing.Any]:
    """
    Extracts the arguments for a function call from the provided parameters.

    Args:
        func: The function for which arguments are to be extracted.
        params: A dictionary of parameters containing
                the necessary arguments for the function.

    Returns:
        A dictionary where the keys are the function argument names
        and the values are the corresponding argument values.
    """
    params_dict = {}
    try:
        sig = inspect.signature(func)
        for param in sig.parameters.values():
            if param.name != "self":
                value = (
                    params.get(param.name, param.default)
                    if isinstance(params, dict)
                    else getattr(params, param.name, param.default)
                )
                if value is not MISSING and value is not inspect.Parameter.empty:
                    params_dict[param.name] = value
                else:
                    params_dict[param.name] = None
    except (ValueError, KeyError) as e:
        logger.warning(f"Parsing {func} for call parameters failed {str(e)}")

    for key in ["args", "kwargs"]:
        if key in params_dict and params_dict[key] is None:
            params_dict.pop(key, None)
    return params_dict


def init_class(
    klass: typing.Type[T],
    params: typing.Union[typing.Dict[str, typing.Any], object],
    *,
    strict: bool = False,
    allow_extra_attrs: bool = False,
) -> T:
    """
    Initialize a class instance with parameters, handling both constructor args and extra attributes.

    Args:
        klass: The class to instantiate
        params: Parameters as dictionary or object with attributes
        strict: If True, raise error when extra parameters don't match constructor signature
        allow_extra_attrs: If True, set extra parameters as instance attributes

    Returns:
        Initialized instance of the class

    Raises:
        TypeError: If class instantiation fails
        ValueError: If strict mode is enabled and extra parameters are found
        AttributeError: If params cannot be converted to dictionary
    """
    if not inspect.isclass(klass):
        raise TypeError(f"Expected a class, got {type(klass)}")

    try:
        if hasattr(params, "__dict__"):
            param_dict = params.__dict__.copy()
        elif isinstance(params, dict):
            allow_extra_attrs = False
            param_dict = params.copy()
        else:
            param_dict = vars(params)
    except (TypeError, AttributeError) as e:
        raise AttributeError(f"Cannot extract parameters from {type(params)}: {e}")

    if is_builtin_type(klass):
        return param_dict

    try:
        constructor_kwargs = get_function_call_args(klass.__init__, param_dict)
    except ValueError as e:
        raise ValueError(f"Failed to analyse constructor for {klass.__name__}: {e}")

    extra_params = {
        key: value for key, value in param_dict.items() if key not in constructor_kwargs
    }

    if strict and extra_params:
        extra_keys = ", ".join(extra_params.keys())
        raise ValueError(f"Extra parameters not allowed in strict mode: {extra_keys}")

    try:
        instance = klass(**constructor_kwargs)
    except TypeError as e:
        logger.error(e, exc_info=True)
        raise TypeError(f"Failed to instantiate {klass.__name__}: {e}") from e

    if allow_extra_attrs and extra_params:
        for key, value in extra_params.items():
            try:
                setattr(instance, key, value)
            except AttributeError as e:
                # Some classes may not allow arbitrary attribute setting
                raise AttributeError(
                    f"Cannot set attribute '{key}' on {klass.__name__}: {e}"
                )

    return instance
