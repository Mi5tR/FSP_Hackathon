"""Проверка ИНН по контрольной сумме (алгоритм ФНС). Это добровольная метка доверия,
а не верификация компании: сверка с ЕГРЮЛ — следующий этап (docs/01-concept.md, раздел 5)."""

_W10 = (2, 4, 10, 3, 5, 9, 4, 6, 8)
_W11 = (7, 2, 4, 10, 3, 5, 9, 4, 6, 8)
_W12 = (3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8)


def _check(digits: list[int], weights: tuple[int, ...]) -> int:
    return sum(d * w for d, w in zip(digits, weights)) % 11 % 10


def inn_valid(inn: str | None) -> bool:
    if not inn or not inn.isdigit() or len(inn) not in (10, 12):
        return False
    d = [int(x) for x in inn]
    if len(inn) == 10:
        return _check(d, _W10) == d[9]
    return _check(d, _W11) == d[10] and _check(d, _W12) == d[11]
