import csv
import json
import typing
from dataclasses import asdict
from abc import ABC, abstractmethod

try:
    from StringIO import StringIO
except ImportError:
    from io import StringIO

from .fields import _ExpectedTypeResolver

if typing.TYPE_CHECKING:
    from .base import BaseModel


_BLOCK_SIZE = 1024

T = typing.TypeVar("T", typing.List["BaseModel"], "BaseModel")
D = typing.TypeVar(
    "D", typing.Dict[str, typing.Any], typing.List[typing.Dict[str, typing.Any]]
)


_registry: dict[str, typing.Type["BaseModelFormatter"]] = {}


class BaseModelFormatter(ABC):
    format_name: str = None

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if cls.format_name:
            names = (
                cls.format_name
                if isinstance(cls.format_name, (list, tuple))
                else [cls.format_name]
            )
            for name in names:
                _registry[name] = cls

    @classmethod
    def get_formatter(cls, format_name: str, **config: typing.Any) -> "BaseModelFormatter":
        try:
            formatter_cls = _registry[format_name]
        except KeyError:
            raise KeyError(f"Format {format_name} not found")
        return formatter_cls(**config) # type: ignore

    @abstractmethod
    def encode(self, _type: typing.Type["BaseModel"], obj: D) -> T:
        pass

    @abstractmethod
    def decode(self, instance: "BaseModel") -> typing.Any:
        pass


class DictModelFormatter(BaseModelFormatter):
    format_name = "dict"

    @staticmethod
    def _encode(
        _type: typing.Type["BaseModel"], obj: typing.Dict[str, typing.Any]
    ) -> "BaseModel":
        # model_config = _type.get_pydantic_mini_config()
        # resolver = _ExpectedTypeResolver(
        #     actual_types=(_type,), model_config=model_config
        # )
        instance = _type.__pydantic_model_resolver__.coerce(obj)
        return instance

    def encode(self, _type: typing.Type["BaseModel"], obj: D) -> T:
        if isinstance(obj, dict):
            return self._encode(_type, obj)
        elif isinstance(obj, list):
            return [self._encode(_type, item) for item in obj]
        else:
            raise TypeError("Object must be dict or list")

    def decode(self, instance: T) -> D:
        if isinstance(instance, list):
            return [asdict(val) for val in instance]
        return asdict(instance)


class JSONModelFormatter(DictModelFormatter):
    format_name = "json"

    def encode(self, _type: typing.Type["BaseModel"], obj: str) -> T:
        return super().encode(_type, json.loads(obj))

    def decode(self, instance: T) -> str:
        return json.dumps(super().decode(instance), default=str)


class CSVModelFormatter(DictModelFormatter):
    format_name = "csv"

    def encode(self, _type: typing.Type["BaseModel"], file: str) -> T:
        with open(file, "r", newline="") as f:
            sample = f.read(_BLOCK_SIZE)
            dialect = csv.Sniffer().sniff(sample)
            has_header = csv.Sniffer().has_header(sample)
            f.seek(0)
            if not has_header:
                raise FileExistsError(f"File {file} does not have header")
            reader = csv.DictReader(f, dialect=dialect)
            return [super().encode(_type, row) for row in reader]

    def decode(self, instance: T) -> str:
        instances = instance if isinstance(instance, (list, tuple)) else [instance]
        with StringIO() as f:
            writer = csv.DictWriter(f, dialect=csv.excel, fieldnames=[])
            for index, obj in enumerate(instances):
                instance_dict = super().decode(obj)
                if index == 0:
                    writer.fieldnames = list(instance_dict.keys())
                    writer.writeheader()
                writer.writerow(instance_dict)

            context = f.getvalue()

        return context
