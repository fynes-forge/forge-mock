"""Mapping from normalised SQL base types to Faker provider callables."""

from __future__ import annotations

import datetime
from typing import Any, Callable
from faker import Faker

# Each entry is a factory: given a Faker instance + type_params, returns a zero-arg callable.
TypeGeneratorFactory = Callable[[Faker, list[int]], Callable[[], Any]]

# Fixed reference for absolute determinism in CI/CD environments.
# We use a fixed UTC datetime object.
REFERENCE_DATE = datetime.datetime(
    2026, 1, 1, 0, 0, 0, tzinfo=datetime.timezone.utc)
# Number of seconds in 5 years.
FIVE_YEARS_S = 5 * 365 * 24 * 60 * 60


def _varchar(fk: Faker, params: list[int]) -> Callable[[], str]:
    max_len = params[0] if params else 255
    if max_len <= 10:
        return fk.lexify
    elif max_len <= 50:
        return fk.name
    else:
        return fk.sentence


def _char(fk: Faker, params: list[int]) -> Callable[[], str]:
    length = params[0] if params else 1
    return lambda: fk.lexify("?" * length)


def _text(fk: Faker, _params: list[int]) -> Callable[[], str]:
    return fk.paragraph


def _int_gen(fk: Faker, _params: list[int]) -> Callable[[], int]:
    return lambda: fk.random_int(min=1, max=2_147_483_647)


def _bigint_gen(fk: Faker, _params: list[int]) -> Callable[[], int]:
    return lambda: fk.random_int(min=1, max=9_223_372_036_854_775_807)


def _smallint_gen(fk: Faker, _params: list[int]) -> Callable[[], int]:
    return lambda: fk.random_int(min=1, max=32_767)


def _float_gen(fk: Faker, _params: list[int]) -> Callable[[], float]:
    # Set right_digits to avoid randrange errors in Python 3.14
    return lambda: round(
        fk.pyfloat(min_value=-1_000_000.0,
                   max_value=1_000_000.0, right_digits=4), 4
    )


def _double_gen(fk: Faker, _params: list[int]) -> Callable[[], float]:
    # Capped at 1e12 for Faker stability
    return lambda: round(
        fk.pyfloat(min_value=-1_000_000_000_000.0,
                   max_value=1_000_000_000_000.0, right_digits=4),
        8
    )


def _decimal_gen(fk: Faker, params: list[int]) -> Callable[[], float]:
    precision = params[0] if len(params) > 0 else 18
    scale = params[1] if len(params) > 1 else 2
    max_val = min(10 ** (precision - scale), 1_000_000_000_000)
    return lambda: round(fk.pyfloat(min_value=0, max_value=max_val, right_digits=scale), scale)


def _bool_gen(fk: Faker, _params: list[int]) -> Callable[[], bool]:
    return fk.pybool


def _date_gen(fk: Faker, _params: list[int]) -> Callable[[], Any]:
    # Uses seeded integer days to prevent drift
    def gen():
        days_offset = fk.generator.random.randint(0, 365 * 5)
        return (REFERENCE_DATE - datetime.timedelta(days=days_offset)).date()
    return gen


def _time_gen(fk: Faker, _params: list[int]) -> Callable[[], str]:
    return fk.time


def _datetime_gen(fk: Faker, _params: list[int]) -> Callable[[], Any]:
    # Deterministic generation using independent second/microsecond integers.
    # This bypasses Faker's internal float math which drifts across OS/interpreters.
    def gen():
        seconds = fk.generator.random.randint(0, FIVE_YEARS_S)
        micros = fk.generator.random.randint(0, 999999)
        dt = REFERENCE_DATE - \
            datetime.timedelta(seconds=seconds, microseconds=micros)
        # strftime ensures the microsecond padding is consistent (.f)
        return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")
    return gen


def _timestamp_gen(fk: Faker, _params: list[int]) -> Callable[[], Any]:
    return _datetime_gen(fk, _params)


def _uuid_gen(fk: Faker, _params: list[int]) -> Callable[[], str]:
    return lambda: str(fk.uuid4())


def _binary_gen(fk: Faker, _params: list[int]) -> Callable[[], bytes]:
    return lambda: fk.binary(length=16)


def _json_gen(fk: Faker, _params: list[int]) -> Callable[[], str]:
    return lambda: str(
        {
            fk.word(): fk.word(),
            fk.word(): fk.random_int(0, 100),
        }
    )


TYPE_GENERATOR_MAP: dict[str, TypeGeneratorFactory] = {
    "VARCHAR": _varchar,
    "CHAR": _char,
    "TEXT": _text,
    "INT": _int_gen,
    "BIGINT": _bigint_gen,
    "SMALLINT": _smallint_gen,
    "FLOAT": _float_gen,
    "DOUBLE": _double_gen,
    "DECIMAL": _decimal_gen,
    "BOOLEAN": _bool_gen,
    "DATE": _date_gen,
    "TIME": _time_gen,
    "DATETIME": _datetime_gen,
    "TIMESTAMP": _timestamp_gen,
    "UUID": _uuid_gen,
    "BINARY": _binary_gen,
    "JSON": _json_gen,
}
