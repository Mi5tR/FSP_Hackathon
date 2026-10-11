"""Банк семейств заданий (item families).

Каждое семейство — это шаблон задачи с параметрами, который детерминированно
разворачивается в конкретный вариант по variant_seed. Свойства:

* Утечка конкретного варианта бесполезна: числа, имена и порядок вариантов
  ответа меняются, правильный ответ вычисляется заново.
* Сложность сопоставима между кандидатами: все варианты семейства — изоморфы
  (одна и та же когнитивная операция), поэтому у семейства одни IRT-параметры
  (a — дискриминативность, b — трудность), откалиброванные на пилотных данных.
* Генерация нейросетью допустима только офлайн, на уровне новых *семейств*:
  они проходят калибровку как pretest-задания, прежде чем начнут влиять на грейд.
"""

from __future__ import annotations

import math
import random
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable

LOW_VARIETY = 250         # меньше уникальных формулировок (из 300 сидов) — ответ легко слить (подбор по валидации, раздел 4)
LOW_VARIETY_WEIGHT = 0.5  # множитель дискриминативности таких семейств в оценке θ


@dataclass
class ItemVariant:
    prompt: str
    options: list[str]
    correct: int
    code: str | None = None


@dataclass
class ItemFamily:
    id: str
    title: str
    skill: str
    specs: tuple[str, ...]
    a: float  # дискриминативность (2PL)
    b: float  # трудность (шкала theta)
    generate: Callable[[random.Random], ItemVariant] = field(repr=False)
    time_limit_s: int = 120
    # Знаниевые семейства с малым числом формулировок показываются не более раза за тест
    max_uses: int = 2
    variety: int = 0  # число уникальных формулировок (считается при загрузке банка)

    @property
    def a_score(self) -> float:
        """Дискриминативность, с которой ответ входит в оценку грейда. У семейств с малым числом
        формулировок ответ легко слить, поэтому их вес снижен: утёкший ключ почти не поднимает θ."""
        return self.a * (LOW_VARIETY_WEIGHT if self.variety < LOW_VARIETY else 1.0)

    def render(self, variant_seed: int) -> ItemVariant:
        return self.generate(random.Random(variant_seed))


def _numeric_options(rng: random.Random, answer: int | float, distractors: list, fmt=str) -> tuple[list[str], int]:
    """Собирает 4 уникальных варианта: правильный + правдоподобные ошибки."""
    pool = []
    for d in distractors:
        if d != answer and d not in pool:
            pool.append(d)
    step = 1
    while len(pool) < 3:
        cand = answer + step * rng.choice([-1, 1])
        if cand != answer and cand not in pool and (not isinstance(answer, int) or cand >= 0):
            pool.append(cand)
        step += 1
    values = [answer] + rng.sample(pool, 3)
    rng.shuffle(values)
    return [fmt(v) for v in values], values.index(answer)


_GENERIC_WRONG = ["Ошибка выполнения", "None", "[]", "Результат не определён"]


def _choice_options(rng: random.Random, answer: str, wrong: list[str]) -> tuple[list[str], int]:
    pool = list(dict.fromkeys(w for w in wrong if w != answer))
    for g in _GENERIC_WRONG:
        if len(pool) >= 3:
            break
        if g != answer and g not in pool:
            pool.append(g)
    values = [answer] + rng.sample(pool, 3)
    rng.shuffle(values)
    return values, values.index(answer)


# ---------------------------------------------------------------- Python / общие

def gen_py_slice(rng):
    xs = rng.sample(range(1, 60), rng.randint(6, 9))
    i = rng.randint(0, 2)
    j = rng.randint(i + 2, len(xs) - 1)
    step = rng.choice([1, 2])
    res = xs[i:j:step]
    code = f"xs = {xs}\nprint(xs[{i}:{j}:{step}])" if step != 1 else f"xs = {xs}\nprint(xs[{i}:{j}])"
    wrong = [xs[i:j + 1:step], xs[i + 1:j:step], xs[i:j - 1:step], xs[i + 1:j + 1:step], xs[i:j][::-1]]
    opts, c = _choice_options(rng, str(res), list({str(w) for w in wrong if w != res}) + ["[]", str(xs[i:j:3])])
    return ItemVariant("Что выведет код?", opts, c, code)


def gen_py_mutable_default(rng):
    base = rng.randint(1, 20)
    fname = rng.choice(["add", "push", "collect", "track"])
    name = rng.choice(["acc", "bucket", "items", "store"])
    calls = []
    shared = 0
    for k in range(rng.randint(2, 6)):
        explicit = rng.random() < 0.3
        calls.append(f"r = {fname}({k * rng.randint(1, 9)}{', []' if explicit else ''})")
        if not explicit:
            shared += 1
        last = 1 if explicit else shared
    ans = last + base
    code = (f"def {fname}(v, {name}=[]):\n    {name}.append(v)\n    return len({name}) + {base}\n\n"
            + "\n".join(calls) + "\nprint(r)")
    opts, c = _numeric_options(rng, ans, [base + 1, len(calls) + base, shared + base, base])
    return ItemVariant("Что выведет код?", opts, c, code)


def gen_py_dict_comp(rng):
    n = rng.randint(6, 14)
    mod = rng.randint(2, 5)
    mul = rng.randint(1, 4)
    var = rng.choice(["i", "x", "k", "v"])
    name = rng.choice(["d", "index", "seen", "groups"])
    d = {(i * mul) % mod: i for i in range(n)}
    key = rng.choice(sorted(d))
    first = min(i for i in range(n) if (i * mul) % mod == key)
    ans = f"{len(d)} {d[key]}"
    code = f"{name} = {{({var} * {mul}) % {mod}: {var} for {var} in range({n})}}\nprint(len({name}), {name}[{key}])"
    wrong = [f"{n} {d[key]}", f"{len(d)} {first}", f"{mod} {d[key]}", f"{len(d) + 1} {d[key]}", f"{n} {first}"]
    opts, c = _choice_options(rng, ans, wrong)
    return ItemVariant("Что выведет код?", opts, c, code)


def gen_async_order(rng):
    names = rng.sample(["alpha", "beta", "gamma", "delta", "omega", "sigma"], 3)
    delays = rng.sample([1, 2, 3, 4, 5], 3)
    lines = ",\n        ".join(f"job('{n}', 0.0{d})" for n, d in zip(names, delays))
    code = ("import asyncio\n\nasync def job(name, delay):\n    await asyncio.sleep(delay)\n    print(name, end=' ')\n\n"
            f"async def main():\n    await asyncio.gather(\n        {lines}\n    )\n\nasyncio.run(main())")
    order = [n for _, n in sorted(zip(delays, names))]
    ans = " ".join(order)
    wrong = {" ".join(names), " ".join(reversed(order)), " ".join(order[1:] + order[:1]), " ".join(names[::-1])}
    wrong.discard(ans)
    while len(wrong) < 3:
        p = names[:]
        rng.shuffle(p)
        if " ".join(p) != ans:
            wrong.add(" ".join(p))
    opts, c = _choice_options(rng, ans, list(wrong))
    return ItemVariant("В каком порядке будут напечатаны имена?", opts, c, code)


# ---------------------------------------------------------------- Алгоритмы

def gen_binary_search(rng):
    n = rng.randint(50, 3_000_000)
    ans = math.ceil(math.log2(n + 1))
    opts, c = _numeric_options(rng, ans, [ans - 1, ans + 1, len(str(n)), ans + 3])
    return ItemVariant(
        f"Какое максимальное число сравнений нужно бинарному поиску в отсортированном массиве из {n:,} элементов?".replace(",", " "),
        opts, c)


def _big_o(n_pow: int, log_pow: int) -> str:
    if n_pow == 0 and log_pow == 0:
        return "O(1)"
    n_part = "" if n_pow == 0 else "n" if n_pow == 1 else f"n{'²' if n_pow == 2 else '³'}"
    log_part = "" if log_pow == 0 else "log n" if log_pow == 1 else "log² n"
    return f"O({' '.join(p for p in (n_part, log_part) if p)})"


_ALL_BIG_O = [_big_o(a, b) for a in range(4) for b in range(3) if a + b <= 3]


def gen_complexity(rng):
    """Генерирует вложенность из 1–3 циклов разных типов и вычисляет асимптотику."""
    depth = rng.randint(1, 3)
    names = rng.sample(["i", "j", "t", "p", "q", "m"], depth)
    lines: list[str] = []
    n_pow = log_pow = 0
    prev_linear = None
    for level, v in enumerate(names):
        pad = "    " * level
        kinds = ["lin", "step", "log", "const"] + (["dep"] if prev_linear else [])
        kind = rng.choice(kinds)
        k = rng.randint(2, 7)
        if kind == "lin":
            lines.append(f"{pad}for {v} in range(n):")
            n_pow += 1
            prev_linear = v
        elif kind == "step":
            lines.append(f"{pad}for {v} in range(0, n, {k}):")
            n_pow += 1
            prev_linear = v
        elif kind == "dep":
            lines.append(f"{pad}for {v} in range({prev_linear}, n):")
            n_pow += 1
            prev_linear = v
        elif kind == "log":
            lines.append(f"{pad}{v} = 1")
            lines.append(f"{pad}while {v} < n:")
            log_pow += 1
        else:
            lines.append(f"{pad}for {v} in range({k}):")
    lines.append("    " * depth + rng.choice(["work()", "process()", "step()"]))
    # Хвостовые инкременты while-циклов, от внутреннего к внешнему
    for level in range(depth - 1, -1, -1):
        header = [ln for ln in lines if ln.startswith("    " * level + "while " + names[level] + " ")]
        if header:
            lines.append("    " * (level + 1) + f"{names[level]} *= {rng.randint(2, 5)}")
    if log_pow > 2:
        return gen_complexity(rng)
    ans = _big_o(n_pow, log_pow)
    opts, c = _choice_options(rng, ans, _ALL_BIG_O)
    return ItemVariant("Какова асимптотическая сложность фрагмента по числу вызовов функции в теле?", opts, c, "\n".join(lines))


def gen_lru(rng):
    cap = rng.randint(2, 3)
    keys = rng.sample("ABCDEFG", 4)
    seq = [rng.choice(keys) for _ in range(rng.randint(8, 10))]
    cache: list[str] = []
    hits = 0
    for k in seq:
        if k in cache:
            hits += 1
            cache.remove(k)
        elif len(cache) >= cap:
            cache.pop(0)
        cache.append(k)
    # Типичная ошибка — посчитать как FIFO
    fifo: list[str] = []
    fifo_hits = 0
    for k in seq:
        if k in fifo:
            fifo_hits += 1
        else:
            if len(fifo) >= cap:
                fifo.pop(0)
            fifo.append(k)
    opts, c = _numeric_options(rng, hits, [fifo_hits, hits + 1, max(hits - 1, 0)])
    return ItemVariant(
        f"LRU-кэш вместимостью {cap}. Последовательность обращений: {' '.join(seq)}. Сколько будет попаданий (hit)?",
        opts, c)


def gen_fib_calls(rng):
    n = rng.randint(5, 13)
    k = rng.randint(1, n - 2)
    fname = rng.choice(["fib", "f", "calc", "rec", "go", "seq"])
    counts = Counter()

    def fib(m):
        counts[m] += 1
        if m < 2:
            return m
        return fib(m - 1) + fib(m - 2)

    fib(n)
    ans = counts[k]
    code = (f"def {fname}(n):\n    if n < 2:\n        return n\n"
            f"    return {fname}(n - 1) + {fname}(n - 2)\n\n{fname}({n})")
    opts, c = _numeric_options(rng, ans, [counts.get(k + 1, ans + 1), counts.get(k - 1, ans + 2), n - k, sum(counts.values())])
    return ItemVariant(f"Сколько раз будет вызвана {fname}({k}) при вычислении {fname}({n})?", opts, c, code)


# ---------------------------------------------------------------- SQL

def gen_sql_left_join(rng):
    na = rng.randint(4, 6)
    mult = [rng.choice([0, 0, 1, 1, 2, 3]) for _ in range(na)]
    orphan = rng.randint(0, 2)  # строки orders без пары в users
    ans = sum(max(1, m) for m in mult)
    inner = sum(mult)
    users = ", ".join(str(i + 1) for i in range(na))
    orders = []
    for i, m in enumerate(mult):
        orders += [str(i + 1)] * m
    orders += [str(na + 10 + k) for k in range(orphan)]
    rng.shuffle(orders)
    code = (f"-- users.id: {users}\n-- orders.user_id: {', '.join(orders) or '(пусто)'}\n"
            "SELECT COUNT(*)\nFROM users u\nLEFT JOIN orders o ON o.user_id = u.id;")
    opts, c = _numeric_options(rng, ans, [inner, inner + orphan, na, ans + orphan])
    return ItemVariant("Что вернёт запрос?", opts, c, code)


def gen_sql_having(rng):
    customers = rng.sample(["anna", "boris", "vera", "gleb", "dina", "egor"], 4)
    rows = []
    for cst in customers:
        for _ in range(rng.randint(1, 3)):
            rows.append((cst, rng.choice([100, 200, 300, 500])))
    rng.shuffle(rows)
    threshold = rng.choice([300, 400, 500])
    totals = {}
    for cst, amt in rows:
        totals[cst] = totals.get(cst, 0) + amt
    ans = sum(1 for v in totals.values() if v > threshold)
    by_row = sum(1 for _, amt in rows if amt > threshold)
    ge = sum(1 for v in totals.values() if v >= threshold)
    table = "\n".join(f"-- ('{cst}', {amt})" for cst, amt in rows)
    code = (f"-- orders(customer, amount):\n{table}\n"
            f"SELECT COUNT(*) FROM (\n  SELECT customer FROM orders\n  GROUP BY customer\n  HAVING SUM(amount) > {threshold}\n) t;")
    opts, c = _numeric_options(rng, ans, [by_row, ge, len(customers)])
    return ItemVariant("Что вернёт запрос?", opts, c, code)


# ---------------------------------------------------------------- HTTP / системный дизайн

_HTTP_CASES = [
    ("Клиент отправил JSON, не прошедший валидацию схемы", "422 Unprocessable Content"),
    ("Запрос без токена к защищённому ресурсу", "401 Unauthorized"),
    ("Токен валиден, но у роли нет прав на ресурс", "403 Forbidden"),
    ("Ресурс успешно создан методом POST", "201 Created"),
    ("Клиент превысил лимит запросов", "429 Too Many Requests"),
    ("Попытка создать пользователя с уже занятым email", "409 Conflict"),
    ("Успешное удаление без тела ответа", "204 No Content"),
    ("Сервис-зависимость не ответила вовремя (шлюз)", "504 Gateway Timeout"),
]
_HTTP_ALL = sorted({c for _, c in _HTTP_CASES} | {"400 Bad Request", "500 Internal Server Error", "200 OK"})


def gen_http_status(rng):
    case, ans = rng.choice(_HTTP_CASES)
    opts, c = _choice_options(rng, ans, _HTTP_ALL)
    return ItemVariant(f"Какой код ответа наиболее корректен? Ситуация: {case}.", opts, c)


def gen_capacity(rng):
    users = rng.randint(2, 60) * 100_000
    req = rng.randint(10, 150)
    peak = rng.randint(2, 12)
    avg = users * req / 86_400
    ans = round(avg * peak)
    fmt = lambda v: f"≈ {int(v):,}".replace(",", " ")
    opts, c = _numeric_options(rng, ans, [round(avg), round(ans * 24), round(ans / 10)], fmt)
    return ItemVariant(
        f"DAU = {users:,}, каждый пользователь делает в среднем {req} запросов в сутки, пиковая нагрузка в {peak} раз выше средней. Оцените пиковый RPS.".replace(",", " "),
        opts, c)


# ---------------------------------------------------------------- Frontend

def gen_js_event_loop(rng):
    labels = rng.sample(list("ABCDEFGH"), 5)
    kinds = ["sync", "sync", "micro", "macro", "micro"]
    rng.shuffle(kinds)
    lines = []
    for lab, k in zip(labels, kinds):
        if k == "sync":
            lines.append(f"console.log('{lab}');")
        elif k == "micro":
            lines.append(f"Promise.resolve().then(() => console.log('{lab}'));")
        else:
            lines.append(f"setTimeout(() => console.log('{lab}'), 0);")
    order = ([lab for lab, k in zip(labels, kinds) if k == "sync"]
             + [lab for lab, k in zip(labels, kinds) if k == "micro"]
             + [lab for lab, k in zip(labels, kinds) if k == "macro"])
    ans = " ".join(order)
    naive = " ".join(labels)
    macro_first = " ".join([lab for lab, k in zip(labels, kinds) if k == "sync"]
                           + [lab for lab, k in zip(labels, kinds) if k == "macro"]
                           + [lab for lab, k in zip(labels, kinds) if k == "micro"])
    wrong = {naive, macro_first, " ".join(order[::-1])}
    wrong.discard(ans)
    while len(wrong) < 3:
        p = labels[:]
        rng.shuffle(p)
        if " ".join(p) != ans:
            wrong.add(" ".join(p))
    opts, c = _choice_options(rng, ans, list(wrong))
    return ItemVariant("В каком порядке выведутся буквы?", opts, c, "\n".join(lines))


_JS_EXPR = [
    ("typeof null", "'object'"), ("typeof NaN", "'number'"), ("[] + []", "''"),
    ("0 == ''", "true"), ("null == undefined", "true"), ("null === undefined", "false"),
    ("[1, 2, 3] + ''", "'1,2,3'"), ("'5' - 2", "3"), ("'5' + 2", "'52'"), ("Boolean([])", "true"),
]
_JS_VALUES = sorted({v for _, v in _JS_EXPR} | {"'undefined'", "NaN", "'null'", "0", "7"})


def gen_js_coercion(rng):
    expr, ans = rng.choice(_JS_EXPR)
    opts, c = _choice_options(rng, ans, _JS_VALUES)
    return ItemVariant("Чему равно выражение в JavaScript?", opts, c, expr)


def gen_css_specificity(rng):
    def selector():
        ids, classes, tags = rng.randint(0, 1), rng.randint(0, 3), rng.randint(0, 2)
        parts = [rng.choice(["div", "p", "section", "li"]) for _ in range(tags)]
        parts += ["#" + rng.choice(["main", "card", "nav"]) for _ in range(ids)]
        parts += ["." + rng.choice(["btn", "active", "item", "big", "dark"]) + str(k) for k in range(classes)]
        return " ".join(parts) or "*", (ids, classes, tags)

    while True:
        (s1, w1), (s2, w2) = selector(), selector()
        if w1 != w2:
            break
    c1, c2 = rng.sample(["red", "green", "blue", "orange"], 2)
    code = f"{s1} {{ color: {c1}; }}\n{s2} {{ color: {c2}; }}"
    ans = c1 if w1 > w2 else c2
    opts, c = _choice_options(rng, ans, [c1, c2, "чёрный (по умолчанию)", "зависит от порядка подключения"])
    return ItemVariant("Оба селектора совпадают с одним элементом. Какой цвет текста он получит?", opts, c, code)


def gen_react_batching(rng):
    start = rng.randint(0, 20)
    ops = []
    for _ in range(rng.randint(2, 5)):
        step = rng.randint(1, 3)
        ops.append(("plain" if rng.random() < 0.5 else "func", step))
    lines = [f"setCount(count + {st});" if kind == "plain" else f"setCount(c => c + {st});" for kind, st in ops]
    # setCount(count + x) берёт значение из замыкания, функциональный апдейтер — из очереди
    value = start
    for kind, st in ops:
        value = start + st if kind == "plain" else value + st
    naive = start + sum(st for _, st in ops)
    code = (f"const [count, setCount] = useState({start});\n\nfunction onClick() {{\n  "
            + "\n  ".join(lines) + "\n}")
    opts, c = _numeric_options(rng, value, [naive, start + ops[-1][1], start])
    return ItemVariant("Чему будет равен count после одного клика (React 18)?", opts, c, code)


# ---------------------------------------------------------------- Data / ML

def gen_median(rng):
    xs = [rng.randint(1, 40) for _ in range(rng.choice([6, 7, 8]))]
    s = sorted(xs)
    m = len(s)
    med = s[m // 2] if m % 2 else (s[m // 2 - 1] + s[m // 2]) / 2
    fmt = lambda v: f"{v:g}"
    mean = round(sum(xs) / m, 1)
    opts, c = _numeric_options(rng, med, [mean, xs[m // 2], s[m // 2]], fmt)
    return ItemVariant(f"Найдите медиану выборки: {', '.join(map(str, xs))}", opts, c)


def gen_precision_recall(rng):
    tp, fp, fn = rng.randint(10, 60), rng.randint(5, 40), rng.randint(5, 40)
    metric = rng.choice(["precision", "recall"])
    p, r = tp / (tp + fp), tp / (tp + fn)
    ans = round(p if metric == "precision" else r, 2)
    other = round(r if metric == "precision" else p, 2)
    fmt = lambda v: f"{v:.2f}"
    opts, c = _numeric_options(rng, ans, [other, round(2 * p * r / (p + r), 2), round(tp / (tp + fp + fn), 2)], fmt)
    return ItemVariant(f"TP = {tp}, FP = {fp}, FN = {fn}. Чему равен {metric}?", opts, c)


def gen_prob_at_least_one(rng):
    n = rng.randint(2, 6)
    p = rng.choice([0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4])
    what = rng.choice(["отказа узла за сутки", "ошибки сборки", "падения теста"])
    ans = round(1 - (1 - p) ** n, 3)
    fmt = lambda v: f"{v:.3f}"
    opts, c = _numeric_options(rng, ans, [round(min(n * p, 0.999), 3), round(p ** n, 3), round((1 - p) ** n, 3)], fmt)
    return ItemVariant(f"Вероятность {what} p = {p}. Независимых попыток {n}. Какова вероятность хотя бы одного такого события?", opts, c)


# ---------------------------------------------------------------- QA

def gen_boundary(rng):
    lo = rng.randint(1, 20)
    hi = lo + rng.randint(10, 80)
    ans = f"{lo - 1}, {lo}, {hi}, {hi + 1}"
    wrong = [f"{lo}, {hi}", f"{lo + 1}, {hi - 1}", f"{lo - 1}, {hi + 1}", f"{lo}, {(lo + hi) // 2}, {hi}"]
    opts, c = _choice_options(rng, ans, wrong)
    return ItemVariant(f"Поле принимает целые числа от {lo} до {hi} включительно. Какой набор — минимальный по методу граничных значений (двухточечный)?", opts, c)


def gen_combinations(rng):
    params = [rng.randint(2, 6) for _ in range(rng.randint(3, 5))]
    ans = math.prod(params)
    opts, c = _numeric_options(rng, ans, [sum(params), max(params) ** 2, ans // 2])
    desc = ", ".join(f"параметр {i + 1}: {v} значения" for i, v in enumerate(params))
    return ItemVariant(f"Сколько тест-кейсов нужно для полного перебора всех комбинаций? {desc}.", opts, c)


# ---------------------------------------------------------------- DevOps

def gen_chmod(rng):
    digits = [rng.randint(0, 7) for _ in range(3)]
    sym = "".join(("r" if d & 4 else "-") + ("w" if d & 2 else "-") + ("x" if d & 1 else "-") for d in digits)
    ans = "".join(map(str, digits))
    wrong = {"".join(str(7 - d) for d in digits), ans[::-1], "".join(str((d + 1) % 8) for d in digits), "755", "644"}
    wrong.discard(ans)
    opts, c = _choice_options(rng, ans, list(wrong))
    return ItemVariant(f"Права файла: -{sym}. Какой восьмеричный код у chmod?", opts, c)


def gen_subnet(rng):
    prefix = rng.randint(20, 29)
    kind = rng.randint(0, 2)
    if kind == 0:
        ans = 2 ** (32 - prefix) - 2
        q = f"Сколько адресов можно назначить хостам в подсети 10.{rng.randint(0, 255)}.0.0/{prefix}?"
        wrong = [ans + 2, 2 ** (31 - prefix), 2 ** (33 - prefix) - 2]
    elif kind == 1:
        big = prefix - rng.randint(2, 4)
        ans = 2 ** (prefix - big)
        q = f"На сколько подсетей /{prefix} можно разбить сеть 172.16.0.0/{big}?"
        wrong = [prefix - big, 2 ** (prefix - big) - 2, 2 ** (prefix - big + 1)]
    else:
        hosts = rng.randint(20, 2000)
        ans = 32 - math.ceil(math.log2(hosts + 2))
        q = f"Какой наибольший префикс (самая маленькая подсеть) вместит {hosts} хостов?"
        wrong = [ans + 1, ans - 1, 32 - math.ceil(math.log2(hosts))]
        opts, c = _numeric_options(rng, ans, wrong, lambda v: f"/{v}")
        return ItemVariant(q, opts, c)
    opts, c = _numeric_options(rng, ans, wrong)
    return ItemVariant(q, opts, c)


def gen_cron(rng):
    m = rng.choice([2, 3, 4, 5, 6, 10, 12, 15, 20, 30])
    h1 = rng.randint(0, 15)
    h2 = h1 + rng.randint(1, 8)
    ans = (h2 - h1 + 1) * (60 // m)
    opts, c = _numeric_options(rng, ans, [(h2 - h1) * (60 // m), 60 // m, 24 * 60 // m])
    return ItemVariant(f"Сколько раз за сутки сработает cron-выражение `*/{m} {h1}-{h2} * * *`?", opts, c)


# ---------------------------------------------------------------- Лёгкие уровни по навыкам
# Без лёгких заданий провал средних не отличает «не знает основ» от «не дотягивает до middle»,
# поэтому у каждого ключевого навыка должны быть задания нескольких уровней сложности.

def gen_sql_where_count(rng):
    names = rng.sample(["anna", "boris", "vera", "gleb", "dina", "egor", "ilya", "kira", "lev"], rng.randint(5, 8))
    rows = [(n, rng.randint(18, 60), rng.choice(["msk", "spb", "kzn"])) for n in names]
    col = rng.choice(["age", "city"])
    if col == "age":
        x = rng.randint(22, 50)
        op = rng.choice([">", ">=", "<"])
        ans = sum(1 for _, a, _ in rows if (a > x if op == ">" else a >= x if op == ">=" else a < x))
        cond = f"age {op} {x}"
        wrong = [sum(1 for _, a, _ in rows if a >= x) if op == ">" else sum(1 for _, a, _ in rows if a > x),
                 len(rows) - ans, len(rows)]
    else:
        city = rng.choice(["msk", "spb", "kzn"])
        ans = sum(1 for _, _, c in rows if c == city)
        cond = f"city = '{city}'"
        wrong = [len(rows) - ans, len(rows), ans + 1]
    table = "\n".join(f"-- ('{n}', {a}, '{c}')" for n, a, c in rows)
    code = f"-- users(name, age, city):\n{table}\nSELECT COUNT(*) FROM users WHERE {cond};"
    opts, c = _numeric_options(rng, ans, wrong)
    return ItemVariant("Что вернёт запрос?", opts, c, code)


def gen_sql_order_limit(rng):
    names = rng.sample(["anna", "boris", "vera", "gleb", "dina", "egor", "ilya", "kira"], rng.randint(5, 7))
    amounts = rng.sample(range(100, 999, 7), len(names))
    rows = list(zip(names, amounts))
    desc = rng.random() < 0.5
    offset = rng.randint(0, 2)
    ordered = sorted(rows, key=lambda r: r[1], reverse=desc)
    ans = ordered[offset][0]
    reverse_pick = sorted(rows, key=lambda r: r[1], reverse=not desc)[offset][0]
    table = "\n".join(f"-- ('{n}', {a})" for n, a in rows)
    code = (f"-- orders(customer, amount):\n{table}\nSELECT customer FROM orders\n"
            f"ORDER BY amount {'DESC' if desc else 'ASC'}\nLIMIT 1 OFFSET {offset};")
    wrong = [reverse_pick, ordered[min(offset + 1, len(ordered) - 1)][0], ordered[max(offset - 1, 0)][0], rows[offset][0]]
    opts, c = _choice_options(rng, ans, [w for w in wrong if w != ans] + [n for n in names if n != ans])
    return ItemVariant("Что вернёт запрос?", opts, c, code)


def gen_http_url(rng):
    host = rng.choice(["api.shop.ru", "example.com", "pay.bank.ru", "fsp-demo.ru"])
    ver = rng.randint(1, 4)
    res = rng.choice(["users", "orders", "teams", "events"])
    rid = rng.randint(10, 9999)
    page, limit = rng.randint(1, 20), rng.choice([10, 20, 50, 100])
    sort = rng.choice(["date", "name", "price"])
    url = f"https://{host}/v{ver}/{res}/{rid}?page={page}&limit={limit}&sort={sort}"
    kind = rng.randint(0, 2)
    if kind == 0:
        q, ans, wrong = "Чему равен query-параметр limit?", str(limit), [str(page), str(rid), str(ver), sort]
    elif kind == 1:
        q, ans = "Какой путь (path) у этого URL?", f"/v{ver}/{res}/{rid}"
        wrong = [f"/{res}/{rid}", f"{host}/v{ver}/{res}/{rid}", f"/v{ver}/{res}/{rid}?page={page}", f"/v{ver}/{res}"]
    else:
        q, ans = "Какой идентификатор ресурса указан в пути?", str(rid)
        wrong = [str(page), str(limit), str(ver), str(rid + 1)]
    opts, c = _choice_options(rng, ans, wrong)
    return ItemVariant(q, opts, c, url)


def gen_js_array(rng):
    xs = [rng.randint(-5, 20) for _ in range(rng.randint(5, 8))]
    k = rng.randint(0, 10)
    m = rng.randint(2, 4)
    op = rng.choice(["length", "sum"])
    kept = [x * m for x in xs if x > k]
    if op == "length":
        expr = f"const xs = {xs};\nconsole.log(xs.filter(x => x > {k}).map(x => x * {m}).length);"
        ans = len(kept)
        wrong = [sum(1 for x in xs if x >= k), len(xs), len(kept) * m]
    else:
        expr = (f"const xs = {xs};\nconsole.log(xs.filter(x => x > {k}).map(x => x * {m})"
                ".reduce((a, b) => a + b, 0));")
        ans = sum(kept)
        wrong = [sum(x for x in xs if x > k), sum(x * m for x in xs), sum(x * m for x in xs if x >= k)]
    opts, c = _numeric_options(rng, ans, wrong)
    return ItemVariant("Что выведет код?", opts, c, expr)


def gen_css_box(rng):
    width = rng.choice([100, 120, 150, 200, 240, 300])
    pad = rng.randint(2, 20)
    border = rng.randint(1, 6)
    margin = rng.randint(0, 20)
    sizing = rng.choice(["content-box", "border-box"])
    ans = width + 2 * pad + 2 * border if sizing == "content-box" else width
    alt = width if sizing == "content-box" else width + 2 * pad + 2 * border
    code = (f".card {{\n  box-sizing: {sizing};\n  width: {width}px;\n  padding: {pad}px;\n"
            f"  border: {border}px solid;\n  margin: {margin}px;\n}}")
    opts, c = _numeric_options(rng, ans, [alt, ans + 2 * margin, width + 2 * pad], lambda v: f"{v}px")
    return ItemVariant("Какова видимая ширина элемента по внешнему краю рамки (без учёта margin)?", opts, c, code)


def gen_cache_latency(rng):
    hit = rng.choice([0.5, 0.6, 0.7, 0.8, 0.9, 0.95])
    t_cache = rng.choice([1, 2, 3, 5])
    t_db = rng.choice([20, 40, 50, 80, 100, 120])
    ans = round(hit * t_cache + (1 - hit) * t_db, 1)
    fmt = lambda v: f"{v:g} мс"
    opts, c = _numeric_options(rng, ans, [round((t_cache + t_db) / 2, 1), round(hit * t_db, 1),
                                          round(t_cache + (1 - hit) * t_db, 1)], fmt)
    return ItemVariant(f"Доля попаданий в кэш {hit:.0%}, ответ из кэша {t_cache} мс, из БД {t_db} мс. "
                       "Какова средняя задержка запроса?", opts, c)


# ---------------------------------------------------------------- Реестр

BANK: list[ItemFamily] = [
    ItemFamily("py_slice", "Срезы списков", "python", ("backend", "data", "qa", "devops"), 1.1, -1.6, gen_py_slice, 90),
    ItemFamily("py_dict_comp", "Dict comprehension", "python", ("backend", "data", "qa"), 1.2, -0.4, gen_py_dict_comp),
    ItemFamily("py_mutable_default", "Изменяемые аргументы по умолчанию", "python", ("backend", "data"), 1.4, 0.3, gen_py_mutable_default),
    ItemFamily("py_async_order", "Порядок выполнения asyncio", "concurrency", ("backend",), 1.3, 0.6, gen_async_order),
    ItemFamily("algo_complexity", "Асимптотика", "algorithms", ("backend", "frontend", "data", "devops"), 1.2, -0.6, gen_complexity),
    ItemFamily("algo_binsearch", "Бинарный поиск", "algorithms", ("backend", "frontend", "data"), 1.0, 0.2, gen_binary_search),
    ItemFamily("algo_lru", "LRU-кэш", "algorithms", ("backend", "frontend", "devops"), 1.5, 1.1, gen_lru, 180),
    ItemFamily("algo_fib_calls", "Дерево рекурсии", "algorithms", ("backend", "frontend", "data"), 1.3, 1.6, gen_fib_calls, 180),
    ItemFamily("sql_left_join", "LEFT JOIN", "sql", ("backend", "data", "qa"), 1.4, 0.4, gen_sql_left_join, 150),
    ItemFamily("sql_having", "GROUP BY / HAVING", "sql", ("backend", "data", "qa"), 1.3, 0.9, gen_sql_having, 150),
    ItemFamily("http_status", "Коды ответа HTTP", "http", ("backend", "frontend", "qa", "devops"), 1.0, -1.1, gen_http_status, 60, max_uses=1),
    ItemFamily("sd_capacity", "Оценка нагрузки", "system_design", ("backend", "devops"), 1.2, 1.4, gen_capacity, 150),
    ItemFamily("js_event_loop", "Event loop", "javascript", ("frontend",), 1.5, 0.8, gen_js_event_loop),
    ItemFamily("js_coercion", "Приведение типов JS", "javascript", ("frontend",), 0.9, -0.7, gen_js_coercion, 60, max_uses=1),
    ItemFamily("css_specificity", "Специфичность CSS", "css", ("frontend",), 1.1, -0.1, gen_css_specificity),
    ItemFamily("react_batching", "Батчинг состояния React", "react", ("frontend",), 1.4, 1.2, gen_react_batching),
    ItemFamily("stat_median", "Медиана", "statistics", ("data",), 0.9, -1.3, gen_median, 90),
    ItemFamily("ml_prec_recall", "Precision / Recall", "ml", ("data",), 1.3, 0.1, gen_precision_recall),
    ItemFamily("prob_at_least_one", "Вероятность хотя бы одного события", "statistics", ("data", "devops"), 1.3, 1.0, gen_prob_at_least_one),
    ItemFamily("qa_boundary", "Граничные значения", "testing", ("qa",), 1.1, -0.9, gen_boundary, 90),
    ItemFamily("qa_combinations", "Комбинаторика тест-кейсов", "testing", ("qa",), 1.0, -0.2, gen_combinations, 90),
    ItemFamily("linux_chmod", "Права доступа Linux", "linux", ("devops", "qa"), 1.1, -0.5, gen_chmod, 90),
    ItemFamily("net_subnet", "Подсети", "networking", ("devops",), 1.3, 0.5, gen_subnet, 90),
    ItemFamily("ci_cron", "Cron-выражения", "ci_cd", ("devops",), 1.2, 0.0, gen_cron, 90),
    ItemFamily("sql_where_count", "WHERE и COUNT", "sql", ("backend", "data", "qa"), 1.2, -1.1, gen_sql_where_count, 90),
    ItemFamily("sql_order_limit", "ORDER BY и LIMIT", "sql", ("backend", "data", "qa"), 1.1, -0.4, gen_sql_order_limit, 90),
    ItemFamily("http_url", "Структура URL", "http", ("backend", "frontend", "qa", "devops"), 1.0, -1.2, gen_http_url, 60),
    ItemFamily("js_array", "filter / map / reduce", "javascript", ("frontend",), 1.2, -0.3, gen_js_array, 90),
    ItemFamily("css_box", "Box model", "css", ("frontend",), 1.1, -0.5, gen_css_box, 90),
    ItemFamily("sd_cache_latency", "Задержка с кэшем", "system_design", ("backend", "devops"), 1.2, 0.3, gen_cache_latency, 120),
]

# Семейства для мобильной разработки, аналитики и ИБ (генераторы — в item_bank_ext.py).
# Импорт внизу модуля: item_bank_ext использует вспомогательные функции этого модуля.
from app.services.testing import item_bank_ext as _x  # noqa: E402

M, AN, SEC = ("mobile",), ("analyst",), ("security",)
BANK += [
    ItemFamily("mob_dp_px", "dp и пиксели", "mobile_ui", M, 1.0, -1.2, _x.gen_dp_px, 90),
    ItemFamily("kt_null_safety", "Null safety в Kotlin", "kotlin", M, 1.1, -0.8, _x.gen_kt_null_safety, 90),
    ItemFamily("swift_optional", "Optional в Swift", "swift", M, 1.0, -0.5, _x.gen_swift_optional, 90),
    ItemFamily("kt_collections", "Коллекции Kotlin", "kotlin", M, 1.2, -0.2, _x.gen_kt_collections, 90),
    ItemFamily("mob_frame_budget", "Бюджет кадра", "mobile_ui", M, 1.2, 0.3, _x.gen_frame_budget, 120),
    ItemFamily("android_lifecycle", "Жизненный цикл Activity", "android", M, 1.3, 0.5, _x.gen_android_lifecycle, 90, max_uses=1),
    ItemFamily("kt_coroutines", "Порядок выполнения корутин", "concurrency", M, 1.4, 0.9, _x.gen_kt_coroutines, 120),
    ItemFamily("mob_pagination", "Пагинация ленты", "http", M + AN, 1.0, -1.0, _x.gen_pagination, 60),
    ItemFamily("an_requirement_type", "Типы требований", "requirements", AN, 0.9, -1.0, _x.gen_requirement_type, 60, max_uses=1),
    ItemFamily("an_retention", "Retention когорты", "product_metrics", AN, 1.0, -0.7, _x.gen_retention, 90),
    ItemFamily("an_funnel", "Узкое место воронки", "product_metrics", AN, 1.1, -0.3, _x.gen_funnel, 120),
    ItemFamily("an_arpu", "ARPU и ARPPU", "product_metrics", AN, 1.2, 0.1, _x.gen_arpu, 120),
    ItemFamily("an_pp_vs_pct", "Проценты и процентные пункты", "product_metrics", AN, 1.3, 0.4, _x.gen_pp_vs_pct, 90),
    ItemFamily("an_ab_uplift", "Прирост в A/B-тесте", "ab_testing", AN + ("data",), 1.3, 0.6, _x.gen_ab_uplift, 120),
    ItemFamily("an_link_table", "Связь многие-ко-многим", "data_modeling", AN, 1.1, 0.0, _x.gen_link_table, 90),
    ItemFamily("an_bpmn_paths", "Сценарии BPMN-процесса", "bpmn", AN, 1.3, 1.1, _x.gen_bpmn_paths, 150),
    ItemFamily("sec_port_service", "Порты и сервисы", "networking", SEC, 0.9, -1.2, _x.gen_port_service, 60, max_uses=1),
    ItemFamily("sec_crypto_kind", "Классы криптоалгоритмов", "cryptography", SEC, 1.0, -0.7, _x.gen_crypto_kind, 60, max_uses=1),
    ItemFamily("sec_vuln_class", "Класс уязвимости", "web_security", SEC, 1.2, -0.3, _x.gen_vuln_class, 90),
    ItemFamily("sec_auth_log", "Разбор журнала входов", "incident_response", SEC, 1.1, 0.2, _x.gen_auth_log, 150),
    ItemFamily("sec_bruteforce", "Стойкость к перебору", "cryptography", SEC, 1.3, 0.8, _x.gen_bruteforce, 150),
    ItemFamily("sec_xor", "XOR-шифрование", "cryptography", SEC, 1.3, 1.2, _x.gen_xor, 120),
]
# Общие семейства, которые подходят и новым специализациям
_SHARED = {"algo_complexity": M, "algo_binsearch": M, "http_status": M + SEC, "http_url": M + SEC,
           "sql_where_count": AN, "sql_order_limit": AN, "sql_left_join": AN, "sql_having": AN, "stat_median": AN,
           "prob_at_least_one": AN, "linux_chmod": SEC, "net_subnet": SEC, "sd_capacity": (), "qa_boundary": AN}
for _f in BANK:
    if _f.id in _SHARED:
        _f.specs = tuple(dict.fromkeys(_f.specs + _SHARED[_f.id]))
for _f in BANK:
    _f.variety = len({(v.prompt, v.code) for v in (_f.render(sd) for sd in range(300))})
BANK_BY_ID = {f.id: f for f in BANK}


def families_for(spec: str) -> list[ItemFamily]:
    return [f for f in BANK if spec in f.specs]
