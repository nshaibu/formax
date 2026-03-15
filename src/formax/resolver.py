import collections
from enum import Enum
from dataclasses import is_dataclass
from typing import (
    Any,
    Dict,
    Optional,
    Type,
    ForwardRef,
    get_args,
    Union,
    List,
    Tuple,
    Generator,
    Callable,
)

from .typing import (
    get_origin,
    NoneType,
    ResolverGenerator,
    is_any_type,
    resolve_and_cache_forward_ref,
    ModelConfigWrapper,
)
from .exceptions import ValidationError
from .utils import (
    make_private_field,
    process_validator_errors,
    PYDANTIC_MINI_MODEL_CONFIG,
    PYDANTIC_MINI_SIGNATURE_MATCHER,
    PYDANTIC_MINI_MODEL_CONTEXT,
)
from .fields import _ClassSignatureMatcher


MatchResult = Tuple[Optional["_TypeAdapter"], Optional["_TypeAdapter"]]


_BUILTIN_TYPES = frozenset(
    {
        int,
        float,
        str,
        bool,
        bytes,
        bytearray,
        list,
        dict,
        set,
        tuple,
        frozenset,
        complex,
        range,
        memoryview,
        NoneType,
    }
)


class _TypeAdapter:
    __slots__ = (
        "type",
        "is_null",
        "is_builtin",
        "is_enum",
        "is_model",
        "is_class",
        "is_forward_ref",
        "is_any",
        "signature_matcher",
        "_resolved",
    )

    def __init__(self, typ_: Type[Any]) -> None:
        # Early normalization
        if typ_ is None:
            typ_ = NoneType

        self.type: type = typ_
        self.signature_matcher: Optional[_ClassSignatureMatcher] = None

        self.is_forward_ref = isinstance(typ_, (ForwardRef, str))
        self._resolved = not self.is_forward_ref

        self.is_any = is_any_type(typ_)

        if self.is_any:
            self._set_any_defaults()
        elif self.is_forward_ref:
            self._set_forward_ref_defaults()
        else:
            # Full introspection
            self._introspect_type()

    def is_null_type(self) -> bool:
        if self.is_class:
            name = getattr(self.type, "__name__", None)
            if name is None:
                return False
            return name == "NoneType"
        return self.type is NoneType

    def isinstance_of(self, value: Any) -> bool:
        if self.is_any:
            return True
        return isinstance(value, self.type)

    def _set_any_defaults(self) -> None:
        """Set defaults for Any type"""
        self.is_null = False
        self.is_builtin = True
        self.is_enum = False
        self.is_model = False
        self.is_class = False
        self._resolved = True

    def _set_forward_ref_defaults(self) -> None:
        """Set defaults for forward references"""
        self.is_null = False
        self.is_builtin = False
        self.is_enum = False
        self.is_model = False
        self.is_class = False

    def _introspect_type(self) -> None:
        """Perform full type introspection."""
        typ_ = self.type

        # Check for the None type first
        self.is_null = typ_ is NoneType

        if self.is_null:
            self.is_builtin = True
            self.is_enum = False
            self.is_model = False
            self.is_class = False
            return

        is_type_class = isinstance(typ_, type)
        self.is_class = is_type_class

        # Fast builtin check
        if typ_ in _BUILTIN_TYPES:
            self.is_builtin = True
        else:
            origin = get_origin(typ_)
            self.is_builtin = origin in _BUILTIN_TYPES if origin else False

        # Enum check
        if is_type_class:
            try:
                self.is_enum = issubclass(typ_, Enum)
            except TypeError:
                self.is_enum = False
        else:
            self.is_enum = False

        self.is_model = PYDANTIC_MINI_MODEL_CONFIG in getattr(
            typ_, "__dict__", {}
        ) or is_dataclass(typ_)

    def deferred(self):
        return self

    def resolve(
        self,
        global_ns: Optional[Dict[str, Any]] = None,
        local_ns: Optional[Dict[str, Any]] = None,
    ) -> "_TypeAdapter":
        """Resolve forward references to concrete types.

        Args:
            global_ns: Global namespace for type resolution
            local_ns: Local namespace for type resolution

        Returns:
            Self with resolved type information
        """
        if self._resolved:
            return self

        forward_type = self.type
        if isinstance(forward_type, str):
            forward_type = ForwardRef(forward_type)

        resolved_type = resolve_and_cache_forward_ref(
            forward_type, globalns=global_ns, localns=local_ns
        )

        self._update_from_resolved_type(resolved_type)
        self._resolved = True
        self.is_forward_ref = False

        return self

    def _update_from_resolved_type(self, resolved_type: Any) -> None:
        """Update instance attributes based on the resolved type."""
        temp_type = _TypeAdapter(resolved_type)

        self.type = resolved_type
        self.is_builtin = temp_type.is_builtin
        self.is_enum = temp_type.is_enum
        self.is_model = temp_type.is_model
        self.is_class = temp_type.is_class

    def get_signature_matcher(self) -> _ClassSignatureMatcher:
        if getattr(self, "signature_matcher", None) is None:
            self.signature_matcher = getattr(
                self.type, PYDANTIC_MINI_SIGNATURE_MATCHER, None
            )
            if self.signature_matcher is None:
                self.signature_matcher = _ClassSignatureMatcher(self.type)
        return self.signature_matcher

    def matches(self, data: Dict[str, Any]) -> bool:
        if self.is_null_type():
            return False

        matcher = self.get_signature_matcher()

        if not matcher:
            return False

        if self.is_model:
            # Dataclasses don't support **kwargs in the standard sense unless
            # custom __init__ is defined, so we stick to field names.
            return matcher.required.issubset(data.keys()) and set(data.keys()).issubset(
                matcher.allowed
            )
        else:
            # All required parameters MUST be in the dict.
            if not matcher.required.issubset(data.keys()):
                return False

            # If the class DOES NOT have **kwargs, keys must be a subset of field names.
            # If the class DOES have **kwargs, any extra keys are allowed.
            if not matcher.has_kwargs and not set(data.keys()).issubset(
                matcher.allowed
            ):
                return False

            return True

    def __str__(self) -> str:
        return self.type.__name__

    def __repr__(self) -> str:
        return repr(self.type)

    def __call__(self, *args, **kwargs):
        try:
            return self.type(*args, **kwargs)
        except TypeError as e:
            raise TypeError(f"Failed to instantiate {str(self.type)} from dict: {e}")

    def __hash__(self) -> int:
        return hash(
            (self.type, self.is_builtin, self.is_enum, self.is_model, self.is_class)
        )


# None Type Adapter
NoneAdapter = _TypeAdapter(NoneType)


class TypeNode:
    __slots__ = ("order", "model_context")

    def __init__(self, order: int):
        self.order = order
        self.model_context: Dict[str, Any] = {}

    def __str__(self) -> str:
        return self.type_string()

    def is_null(self) -> bool:
        return False

    def is_builtin(self) -> bool:
        return False

    def is_enum(self) -> bool:
        return False

    def is_model(self) -> bool:
        return False

    def is_class(self) -> bool:
        return False

    def is_forward_ref(self) -> bool:
        return False

    def is_any(self) -> bool:
        return False

    def type_string(self) -> str:
        raise NotImplementedError

    def match(self, value: Any) -> MatchResult:
        raise NotImplementedError

    def validate(self, value: Any) -> bool:
        raise NotImplementedError

    def coerce(self, value: Any) -> Any:
        raise NotImplementedError


def _type_resolver_generator(
    types_tuple: Union[Tuple[TypeNode, ...], List[TypeNode]],
    model_context: Dict[str, Any],
) -> ResolverGenerator:
    """Generator that yields type nodes in the order they were passed in"""
    for node in types_tuple:
        yield node


def _forward_type_resolver_generator(
    types_tuple: Union[Tuple[TypeNode, ...], List[TypeNode]],
    model_context: Dict[str, Any],
) -> ResolverGenerator:
    """Generator that yields type nodes in the order they were passed in"""
    for node in types_tuple:
        if isinstance(node, ScalarNode) and node.is_forward_ref():
            node.adapter.resolve(global_ns=model_context)
        yield node


def resolve_nodes(
    types_tuple: Union[Tuple[TypeNode, ...], List[TypeNode]],
    model_context: Dict[str, Any],
) -> ResolverGenerator:
    """Resolve forward references in a list of type nodes"""
    has_forward_ref = any(node.is_forward_ref() for node in types_tuple)
    if has_forward_ref:
        return _forward_type_resolver_generator(types_tuple, model_context)
    return _type_resolver_generator(types_tuple, model_context)


class ScalarNode(TypeNode):
    __slots__ = ("adapter", "model_context")

    def __init__(
        self, adapter: _TypeAdapter, *, order: int = 0, forward_ref_to_any: bool = False
    ):
        super().__init__(order)

        if adapter.is_forward_ref and forward_ref_to_any:
            adapter.type = Any
            adapter.is_forward_ref = False
            adapter._resolved = True

        self.adapter = adapter

    def is_null(self) -> bool:
        return self.adapter.is_null

    def is_builtin(self) -> bool:
        return self.adapter.is_builtin

    def is_enum(self) -> bool:
        return self.adapter.is_enum

    def is_model(self) -> bool:
        return self.adapter.is_model

    def is_class(self) -> bool:
        return self.adapter.is_class

    def is_any(self) -> bool:
        return self.adapter.is_any

    def is_forward_ref(self) -> bool:
        return self.adapter.is_forward_ref

    def __repr__(self) -> str:
        return f"ScalarNode(adapter={self.adapter})"

    def type_string(self) -> str:
        return str(self.adapter.type)

    def match(self, value: Any) -> MatchResult:

        if self.is_any():
            return None, self.adapter

        if self.validate(value):
            return None, self.adapter

        # dict → class coercion
        if isinstance(value, dict) and self.is_class():
            if self.adapter.matches(value):
                return None, self.adapter

        # builtin / enum coercion
        if self.is_builtin() or self.is_enum():
            try:
                self.adapter(value)
                return None, self.adapter
            except (ValueError, TypeError):
                return None, None

        return None, None

    def validate(self, value: Any) -> bool:
        return self.adapter.isinstance_of(value)

    def coerce(self, value):
        if self.adapter.isinstance_of(value):
            return value

        try:
            return self.adapter(value)
        except Exception:
            pass

        raise TypeError(f"Expected {self.adapter}, got {type(value)}")


class UnionNode(TypeNode):
    __slots__ = (
        "has_any",
        "typed_branches",
        "forward_ref_branches",
        "_selected_match_type",
    )

    def __init__(
        self,
        branches: List[TypeNode],
        forward_ref_branches: List[TypeNode],
        *,
        has_any: bool = False,
        order: int = 0,
    ):
        super().__init__(order)

        self.typed_branches: List[TypeNode] = branches or []
        self.forward_ref_branches: List[TypeNode] = forward_ref_branches or []

        self.has_any: bool = has_any
        self._selected_match_type: MatchResult = None, None

    def type_string(self) -> str:
        format_str_lt = set()
        for branch in self.typed_branches:
            format_str_lt.add(branch.type_string())
        for branch in self.forward_ref_branches:
            format_str_lt.add(branch.type_string())
        return " | ".join(format_str_lt)

    def is_forward_ref(self) -> bool:
        return len(self.forward_ref_branches) > 0

    def is_any(self) -> bool:
        return self.has_any

    def __repr__(self) -> str:
        return f"UnionNode(typed_branches={self.typed_branches}, forward_ref_branches={self.forward_ref_branches})"

    def match(self, value: Any) -> MatchResult:
        """
        Attempt to match the given value against the union type.
        Returns a MatchResult indicating whether a match was found and the inner type adapter.
        """
        # Resolve real type annotation
        container, inner = self.get_matching_type(
            value,
            resolver=_type_resolver_generator(self.typed_branches, self.model_context),
        )
        if container or inner:
            return container, inner

        # Resolve forward types
        container, inner = self.get_matching_type(
            value,
            resolver=_forward_type_resolver_generator(
                self.forward_ref_branches, self.model_context
            ),
        )
        if container or inner:
            return container, inner

        return None, None

    @staticmethod
    def get_matching_type(value: Any, resolver: ResolverGenerator) -> MatchResult:
        """
        Determine which type best matches the value
        Args:
            value: The value to match against
            resolver: The resolver generator to use for type resolution
        Returns: A tuple containing the matching container type adapter and the inner type adapter
        """

        fallback_any = None

        for node in resolver:
            container, inner = node.match(value)
            if inner is not None:
                if node.__class__.__name__ == "ScalarNode" and node.is_any():
                    fallback_any = inner
                    continue

                return container, inner

        if fallback_any:
            return None, fallback_any

        return None, None

    def validate(self, value: Any) -> bool:
        self._selected_match_type = self.match(value)
        if any(self._selected_match_type):
            return True
        return False

    def coerce(self, value):
        if not any(self._selected_match_type):
            self._selected_match_type = self.match(value)

        if not any(self._selected_match_type):
            raise TypeError(
                f"Cannot coerce {type(value).__name__!r} to any of the type(s) {self.type_string()!r}"
            )

        container, inner = self._selected_match_type
        if container and not container.isinstance_of(value):
            value = container.coerce(value)

        if inner:
            # we can use functools or itertools util function to modify the content of container without make compy of the container
            pass

        raise TypeError("No matching union branch")


class DictNode(TypeNode):
    __slots__ = ("key_node", "value_node")

    def __init__(self, key_node: TypeNode, value_node: TypeNode, order: int = 0):
        super().__init__(order)
        self.key_node = key_node
        self.value_node = value_node

    def match(self, value: Any) -> MatchResult:
        if not isinstance(value, dict):
            return None, None

        _, key_adapter = self.key_node.match(next(iter(value.keys())))
        _, value_adapter = self.value_node.match(next(iter(value.values())))

        return key_adapter, value_adapter

    def validate(self, value) -> bool:
        if not isinstance(value, dict):
            return False

        for key, val in value.items():
            if not self.key_node.validate(key):
                return False
            if not self.value_node.validate(val):
                return False
        return True

    def coerce(self, value):
        if not isinstance(value, dict):
            try:
                value = dict(value)
            except Exception:
                raise TypeError("Invalid dict type")

        new_items = []
        for key, val in value.items():
            new_items.append((self.key_node.coerce(key), self.value_node.coerce(val)))

        return dict(new_items)

    def __repr__(self) -> str:
        return f"DictNode(key_node={self.key_node}, value_node={self.value_node})"


class ContainerNode(TypeNode):
    __slots__ = ("container_adapter", "inner")

    def __init__(
        self, container_adapter: _TypeAdapter, inner_node: TypeNode, order: int = 0
    ):
        super().__init__(order)
        self.container_adapter = container_adapter
        self.inner = inner_node

    def __repr__(self) -> str:
        return f"ContainerNode(container_adapter={self.container_adapter}, inner={self.inner})"

    def is_null(self) -> bool:
        return self.inner.is_null()

    def is_builtin(self) -> bool:
        return self.inner.is_builtin()

    def is_enum(self) -> bool:
        return self.inner.is_enum()

    def is_model(self) -> bool:
        return self.inner.is_model()

    def is_class(self) -> bool:
        return self.inner.is_class()

    def is_any(self) -> bool:
        return self.inner.is_any()

    def type_string(self) -> str:
        return f"{self.container_adapter}[{self.inner.type_string()}]"

    def match(self, value: Any) -> MatchResult:

        # if value is not the expected container
        if not self.container_adapter.isinstance_of(value):
            return None, None

        # determine inner type
        _, inner = UnionNode.get_matching_type(
            value,
            resolver=resolve_nodes([self.inner], self.model_context),
        )

        return self.container_adapter, inner

    def validate(self, value) -> bool:
        if not self.container_adapter.isinstance_of(value):
            return False

        for item in value:
            if not self.inner.validate(item):
                return False
        return True

    def coerce(self, value):
        try:
            new_items = list(map(lambda item: self.inner.coerce(item), value))
        except (KeyError, TypeError, ValueError):
            raise TypeError("Coercion of inner type(s) failed")

        try:
            return self.container_adapter(new_items)
        except Exception:
            raise TypeError("Coercion of container type failed")


class OptionalNode(TypeNode):
    __slots__ = ("inner",)

    def __init__(self, inner: TypeNode, order: int = 0):
        self.inner = inner
        super().__init__(order)

    def __repr__(self) -> str:
        return f"OptionalNode(inner={self.inner})"

    def is_null(self) -> bool:
        return self.inner.is_null()

    def is_builtin(self) -> bool:
        return self.inner.is_builtin()

    def is_enum(self) -> bool:
        return self.inner.is_enum()

    def is_model(self) -> bool:
        return self.inner.is_model()

    def is_class(self) -> bool:
        return self.inner.is_class()

    def is_any(self) -> bool:
        return self.inner.is_any()

    def is_forward_ref(self) -> bool:
        return self.inner.is_forward_ref()

    def type_string(self) -> str:
        return f"Optional[{self.inner.type_string()}]"

    def match(self, value: Any) -> MatchResult:
        if value is None:
            return NoneAdapter, NoneAdapter

        _, inner = UnionNode.get_matching_type(
            value, resolver=resolve_nodes([self.inner], self.model_context)
        )

        if inner:
            return NoneAdapter, inner

        return None, None

    def validate(self, value) -> bool:
        if value is None:
            return True
        return self.inner.validate(value)

    def coerce(self, value):
        if value is None:
            return None
        return self.inner.coerce(value)


class TypeTreeBuilder:
    __slots__ = ("model_config", "model_context")

    def __init__(self, model_config: ModelConfigWrapper, model_context: Dict[str, Any]):
        self.model_config = model_config
        self.model_context = model_context

    def build_container_type(self, _type: Type[Any], args: Tuple[Any, ...]) -> TypeNode:
        if args:
            return ContainerNode(_TypeAdapter(_type), self.build(args[0]))
        return ScalarNode(_TypeAdapter(_type))

    def build(self, annotation) -> TypeNode:
        origin = get_origin(annotation)
        args = get_args(annotation)

        # Optional[T]
        if origin is Union and NoneType in args:
            non_none = tuple(a for a in args if a is not NoneType)
            if len(non_none) == 1:
                return OptionalNode(self.build(non_none[0]))

        # Union
        if origin is Union:
            branches = []
            forward_ref_branches = []
            has_any = False
            for order, arg in enumerate(args):
                node = self.build(arg)
                node.order = order
                if isinstance(node, UnionNode):
                    if not has_any:
                        has_any = node.has_any
                    branches.extend(node.typed_branches)  # flatten
                    forward_ref_branches.extend(node.forward_ref_branches)
                elif isinstance(node, ScalarNode) and node.is_forward_ref():
                    forward_ref_branches.append(node)
                else:
                    branches.append(node)
            return UnionNode(branches, forward_ref_branches, has_any=has_any)

        # List[T]
        if origin is list:
            return self.build_container_type(list, args)

        # Set[T]
        if origin is set:
            return self.build_container_type(set, args)

        # FrozenSet[T]
        if origin is frozenset:
            return self.build_container_type(frozenset, args)

        # Tuple[T]
        if origin is tuple:
            return self.build_container_type(tuple, args)

        # Dict[KT, VT] or Dict
        if origin is dict:
            if not args:
                args = (str, Any)
            return DictNode(self.build(args[0]), self.build(args[1]))

        # Any
        if annotation is Any:
            return ScalarNode(_TypeAdapter(Any))

        # Scalar fallback
        if isinstance(annotation, (type, str)):
            return ScalarNode(
                _TypeAdapter(annotation),
                forward_ref_to_any=self.model_config.forward_refs_as_any,
            )

        raise TypeError(f"Unsupported annotation: {annotation}")
