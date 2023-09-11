#!/usr/bin/env python3
from __future__ import annotations

import enum
import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from functools import cached_property
from types import NoneType
from typing import Literal, Self, TextIO, assert_never, cast


class TypeEnum(enum.Enum):
    STRING = "string"
    INT = "int"
    FLOAT = "float"
    BOOL = "bool"
    NONE = "none"

    OBJECT = "object"
    ARRAY = "array"

    ONE_OF = "one_of"
    NEVER = "never"

    @classmethod
    def from_type(cls, t: type) -> Self:
        map = {
            str: cls.STRING,
            int: cls.INT,
            float: cls.FLOAT,
            bool: cls.BOOL,
            NoneType: cls.NONE,
        }
        if t not in map:
            raise TypeError(f"Cannot convert {t=} to {cls=}")
        return map[t]


@dataclass(kw_only=True)
class TypeDef:
    name: str = field(repr=False)
    type: TypeEnum

    def as_type_str(self) -> str:
        print(repr(self))
        raise NotImplementedError()


@dataclass(kw_only=True)
class LiteralTypeDef(TypeDef):
    type: Literal[
        TypeEnum.STRING, TypeEnum.INT, TypeEnum.FLOAT, TypeEnum.BOOL, TypeEnum.NONE
    ]

    @classmethod
    def from_type(cls, t: type, name: str) -> Self:
        # Constructing a dict with a list of tuples allows pytight to infer a narrower type
        # for the dict keys and values
        type_map = dict(
            (
                (str, TypeEnum.STRING),
                (int, TypeEnum.INT),
                (float, TypeEnum.FLOAT),
                (bool, TypeEnum.BOOL),
                (NoneType, TypeEnum.NONE),
            )
        )
        return cls(name=name, type=type_map[t])

    def as_type_str(self) -> str:
        map = {
            TypeEnum.STRING: "str",
            TypeEnum.INT: "int",
            TypeEnum.FLOAT: "float",
            TypeEnum.BOOL: "bool",
            TypeEnum.NONE: "None",
        }
        return map[self.type]


@dataclass(kw_only=True)
class MaybeStringEnumDef(LiteralTypeDef):
    type: Literal[TypeEnum.STRING] = field(
        init=False, default=TypeEnum.STRING, repr=False
    )
    values: Counter[str]

    def merge(self, other: MaybeStringEnumDef) -> Self:
        self.values.update(other.values)
        return self

    def as_type_str(self) -> str:
        # Treat as a Literal if:
        # - There are less than 10 distinct values
        if len(self.values) < 10:
            return f"t.Literal[{', '.join(map(repr, self.values.keys()))}]"
        return "str"


@dataclass(kw_only=True)
class ObjectDef(TypeDef):
    properties: dict[str, TypeDef]
    type: Literal[TypeEnum.OBJECT] = field(
        init=False, default=TypeEnum.OBJECT, repr=False
    )
    not_required_keys: set[str] = field(default_factory=set, repr=False, init=False)
    keys_statistic: Counter[str] = field(
        default_factory=Counter, repr=False, init=False
    )
    merge_count: int = field(default=0, repr=False, init=False)

    def __post_init__(self) -> None:
        self.keys_statistic.update(self.keys)

    def merge(self, other: ObjectDef) -> Self:
        self.keys_statistic.update(other.keys)
        self.merge_count += 1
        for other_key, other_value in other.properties.items():
            if other_key in self.properties:
                self.properties[other_key] = merge_types(
                    other_value, self.properties[other_key]
                )
            else:
                self.not_required_keys.add(other_key)
                self.properties[other_key] = other_value
        for key in self.keys:
            if key not in other.keys:
                self.not_required_keys.add(key)
        return self

    @cached_property
    def keys(self) -> set[str]:
        return set(self.properties.keys())

    def as_type_str(self) -> str:
        if not self.properties:
            return "dict[str, t.Any]"

        lines = list[str]()
        name = self.name.removeprefix("$").replace("/", "_").strip("_").replace("*", "")
        if name == "":
            name = "Root"
        else:
            name = "".join(map(str.capitalize, name.split("_")))
        name = f"{name}Dict"
        lines.append(f"class {name}(t.TypedDict):")
        for key, value in self.properties.items():
            if key in self.not_required_keys:
                lines.append(f"    {key}: t.NotRequired[{value.as_type_str()}]")
            else:
                lines.append(f"    {key}: {value.as_type_str()}")
        print("\n".join(lines))
        print()
        return name


@dataclass(kw_only=True)
class ArrayDef(TypeDef):
    items: TypeDef
    type: Literal[TypeEnum.ARRAY] = field(
        init=False, default=TypeEnum.ARRAY, repr=False
    )

    def __hash__(self) -> int:
        return hash((self.name, self.type, self.items))

    def as_type_str(self) -> str:
        return f"list[{self.items.as_type_str()}]"


@dataclass(kw_only=True)
class OneOfDef(TypeDef):
    items: list[ArrayDef | LiteralTypeDef | ObjectDef]
    type: TypeEnum = field(init=False, default=TypeEnum.ONE_OF, repr=False)

    @property
    def needs_union(self) -> bool:
        types = [item.type for item in self.items]
        return TypeEnum.NONE in types and len(types) == 2

    def as_type_str(self) -> str:
        items = list[TypeDef]()
        for item in self.items:
            if isinstance(item, LiteralTypeDef) and item.type == TypeEnum.NONE:
                continue
            items.append(item)

        if len(items) == 1:
            return f"t.Optional[{items[0].as_type_str()}]"
        else:
            return f"Union[{', '.join([item.as_type_str() for item in items])}]"


@dataclass(kw_only=True)
class NeverDef(TypeDef):
    name: str = "__never__"
    type: Literal[TypeEnum.NEVER] = TypeEnum.NEVER

    def as_type_str(self) -> str:
        return "t.Never"


def merge_types(a: TypeDef, b: TypeDef) -> TypeDef:
    if a.name != b.name and not isinstance(a, NeverDef) and not isinstance(b, NeverDef):
        raise TypeError(f"Cannot merge {a.name=} and {b.name=}")

    match (a, b):
        case [NeverDef(), value] | [value, NeverDef()]:
            return value
        case [MaybeStringEnumDef(), MaybeStringEnumDef()]:
            return a.merge(b)
        case [LiteralTypeDef(), LiteralTypeDef()]:
            if a.type == b.type:
                return LiteralTypeDef(
                    name=a.name,
                    type=a.type,
                )
            elif {a.type, b.type} == {TypeEnum.INT, TypeEnum.FLOAT}:
                return LiteralTypeDef(name=a.name, type=TypeEnum.FLOAT)
            else:
                return OneOfDef(items=[a, b], name=a.name)
        case (
            [OneOfDef() as one_of, other]
            | [
                other,
                OneOfDef() as one_of,
            ]
        ) if not isinstance(other, OneOfDef):
            if isinstance(other, MaybeStringEnumDef):
                for item in one_of.items:
                    if isinstance(item, MaybeStringEnumDef):
                        item.merge(other)
                        return one_of
            elif isinstance(other, LiteralTypeDef):
                for item in one_of.items:
                    if item == other:
                        return one_of
            elif isinstance(other, ObjectDef):
                for item in one_of.items:
                    if isinstance(item, ObjectDef):
                        item.merge(other)
                        return one_of
            elif isinstance(other, ArrayDef):
                for item in one_of.items:
                    if isinstance(item, ArrayDef):
                        item.items = merge_types(item.items, other.items)
                        return one_of
            elif isinstance(
                other, TypeDef
            ):  # pyright: ignore [reportUnnecessaryIsInstance]
                raise NotImplementedError()
            else:
                assert_never(other)

            return OneOfDef(items=[*one_of.items, other], name=one_of.name)
        case [ObjectDef(), LiteralTypeDef()] | [LiteralTypeDef(), ObjectDef()]:
            return OneOfDef(items=[a, b], name=a.name)
        case [ArrayDef(), ArrayDef()]:
            return ArrayDef(
                name=a.name,
                items=merge_types(a.items, b.items),
            )
        case [ObjectDef(), ObjectDef()]:
            return a.merge(b)
        case [OneOfDef(), OneOfDef()]:
            result = a
            for item in b.items:
                result = merge_types(result, item)
            return result
        case _:
            raise SystemExit(f'Cannot merge "{a.type}" and "{b.type}"')


def process_obj(obj: object, name: str = "$") -> TypeDef:
    match obj:
        case str():
            return MaybeStringEnumDef(name=name, values=Counter([obj]))
        case int() | float() | bool() | None:
            return LiteralTypeDef.from_type(type(obj), name)
        case dict():
            return ObjectDef(
                name=name,
                properties={
                    key: process_obj(value, f"{name}/{key}")
                    for key, value in cast(dict[str, object], obj).items()
                },
            )
        case list():
            items = NeverDef()
            for value in cast(list[object], obj):
                items = merge_types(items, process_obj(value, f"{name}/*"))
            return ArrayDef(
                name=name,
                items=items,
            )
        case _:
            raise NotImplementedError()


def json_line_generator(input: TextIO):
    for line in input:
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            print(f"Invalid JSON: {line}", file=sys.stderr)


def build_type_def(obj: TypeDef) -> str:
    return obj.as_type_str()


def main() -> int:
    final_type = NeverDef()
    for i, line in enumerate(json_line_generator(sys.stdin)):
        print("Processing line:", i, file=sys.stderr, end="\r")
        final_type = merge_types(final_type, process_obj(line))
    print("import typing as t")
    print()
    print(f"RootType = {build_type_def(final_type)}", end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
