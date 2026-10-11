"""Семейства заданий для мобильной разработки, аналитики и информационной безопасности.

Принцип тот же, что в item_bank.py: каждое семейство — генератор изоморфных вариантов
(числа, имена, порядок и сам правильный ответ пересчитываются от seed варианта).
Знаниевые семейства с малым числом формулировок помечены max_uses=1.
"""

from __future__ import annotations

import math
import random

from app.services.testing.item_bank import ItemVariant, _choice_options, _numeric_options


def _rub(v: float) -> str:
    return f"{v:,.0f} ₽".replace(",", " ")


# ---------------------------------------------------------------- Mobile

def gen_dp_px(rng: random.Random) -> ItemVariant:
    dpi = rng.choice([(160, "mdpi"), (240, "hdpi"), (320, "xhdpi"), (480, "xxhdpi"), (640, "xxxhdpi")])
    dp = rng.choice([8, 12, 16, 24, 36, 48, 56, 72])
    ans = dp * dpi[0] // 160
    opts, c = _numeric_options(rng, ans, [dp, dp * 160 // dpi[0] or dp + 1, dp * dpi[0] // 100], lambda v: f"{v} px")
    return ItemVariant(f"Кнопка шириной {dp}dp на экране плотности {dpi[1]} ({dpi[0]} dpi). Сколько это физических пикселей?",
                       opts, c)


def gen_frame_budget(rng: random.Random) -> ItemVariant:
    hz = rng.choice([60, 90, 120])
    budget = 1000 / hz
    frames = [round(rng.uniform(budget * 0.4, budget * 2.6), 1) for _ in range(rng.randint(6, 9))]
    ans = sum(1 for f in frames if f > budget)
    opts, c = _numeric_options(rng, ans, [len(frames) - ans, sum(1 for f in frames if f > 16.7) if hz != 60 else ans + 1,
                                          sum(1 for f in frames if f > budget * 2)])
    return ItemVariant(f"Экран обновляется с частотой {hz} Гц. Время подготовки кадров (мс): "
                       f"{', '.join(f'{f:g}' for f in frames)}. Сколько кадров не уложатся в бюджет и дадут подтормаживание?",
                       opts, c)


def gen_kt_null_safety(rng: random.Random) -> ItemVariant:
    name = rng.choice(["title", "nick", "city", "label"])
    value = rng.choice([None, "kotlin", "android", "fsp", "mobile"])
    fallback = rng.randint(-3, 9)
    code = (f"val {name}: String? = {'null' if value is None else repr(value).replace(chr(39), chr(34))}\n"
            f"val n = {name}?.length ?: {fallback}\nprintln(n + 1)")
    ans = (len(value) if value else fallback) + 1
    wrong = [fallback, (len(value) if value else 0) + 1, len(value or "") , ans + 1]
    opts, c = _numeric_options(rng, ans, [w for w in wrong if w != ans])
    return ItemVariant("Что выведет код на Kotlin?", opts, c, code)


def gen_kt_collections(rng: random.Random) -> ItemVariant:
    xs = rng.sample(range(1, 30), rng.randint(6, 9))
    k = rng.choice([2, 3, 4])
    m = rng.choice([2, 3, 10])
    code = f"val xs = listOf({', '.join(map(str, xs))})\nprintln(xs.filter {{ it % {k} == 0 }}.map {{ it * {m} }}.sum())"
    ans = sum(x * m for x in xs if x % k == 0)
    wrong = [sum(x for x in xs if x % k == 0), sum(x * m for x in xs if x % k != 0), sum(xs) * m]
    opts, c = _numeric_options(rng, ans, [w for w in wrong if w != ans])
    return ItemVariant("Что выведет код на Kotlin?", opts, c, code)


_LIFECYCLE = [
    ("Пользователь впервые открыл экран (Activity).", "onCreate → onStart → onResume",
     ["onStart → onCreate → onResume", "onCreate → onResume → onStart", "onResume → onStart → onCreate"]),
    ("Пользователь свернул приложение кнопкой «Домой» (экран был на переднем плане).", "onPause → onStop",
     ["onStop → onPause", "onPause → onDestroy", "onStop → onDestroy"]),
    ("Пользователь вернулся в свёрнутое приложение (процесс не был убит).", "onRestart → onStart → onResume",
     ["onCreate → onStart → onResume", "onStart → onRestart → onResume", "onResume → onStart"]),
    ("Пользователь повернул экран, конфигурация не обрабатывается вручную.",
     "onPause → onStop → onDestroy → onCreate → onStart → onResume",
     ["onPause → onResume", "onConfigurationChanged", "onStop → onStart"]),
    ("Поверх экрана показали полупрозрачное диалоговое Activity.", "onPause",
     ["onPause → onStop", "onStop", "колбэки не вызываются"]),
]


def gen_android_lifecycle(rng: random.Random) -> ItemVariant:
    scenario, ans, wrong = rng.choice(_LIFECYCLE)
    opts, c = _choice_options(rng, ans, wrong)
    return ItemVariant(f"{scenario} Какие колбэки жизненного цикла вызовутся и в каком порядке?", opts, c)


def gen_kt_coroutines(rng: random.Random) -> ItemVariant:
    names = rng.sample(["A", "B", "C", "D", "E"], 3)
    delays = rng.sample([0, 10, 20, 30, 50], 2)
    main_name = names[2]
    code = ("runBlocking {\n"
            f"    launch {{ delay({delays[0]}); print(\"{names[0]}\") }}\n"
            f"    launch {{ delay({delays[1]}); print(\"{names[1]}\") }}\n"
            f"    print(\"{main_name}\")\n}}")
    order = [main_name] + [n for _, n in sorted(zip(delays, names[:2]))]
    ans = "".join(order)
    wrong = {"".join(names), "".join(names[:2][::-1] + [main_name]), "".join(order[1:] + order[:1]),
             "".join([names[0], main_name, names[1]])}
    wrong.discard(ans)
    opts, c = _choice_options(rng, ans, list(wrong))
    return ItemVariant("Что напечатает код с корутинами Kotlin?", opts, c, code)


def gen_swift_optional(rng: random.Random) -> ItemVariant:
    var = rng.choice(["count", "score", "level", "page"])
    value = rng.choice([None, rng.randint(1, 9)])
    fb = rng.randint(10, 40)
    mul = rng.choice([2, 3])
    code = f"let {var}: Int? = {'nil' if value is None else value}\nprint(({var} ?? {fb}) * {mul})"
    ans = (value if value is not None else fb) * mul
    opts, c = _numeric_options(rng, ans, [fb * mul if value is not None else mul, fb, (value or 0) * mul])
    return ItemVariant("Что выведет код на Swift?", opts, c, code)


def gen_pagination(rng: random.Random) -> ItemVariant:
    page = rng.choice([10, 20, 25, 30, 50])
    item = rng.randint(page + 1, page * 9)
    ans = math.ceil(item / page)
    opts, c = _numeric_options(rng, ans, [item // page, ans + 1, math.ceil(item / (page * 2))])
    return ItemVariant(f"Лента загружается страницами по {page} элементов (API: ?page=1,2,…). Сколько запросов нужно, "
                       f"чтобы пользователь долистал до элемента №{item}?", opts, c)


# ---------------------------------------------------------------- Аналитика

def gen_funnel(rng: random.Random) -> ItemVariant:
    visits = rng.choice([10_000, 20_000, 40_000, 50_000])
    steps = [visits]
    names = ["Просмотр карточки", "Корзина", "Оформление", "Оплата"]
    for _ in range(3):
        steps.append(int(steps[-1] * rng.uniform(0.2, 0.7)))
    rates = [steps[i + 1] / steps[i] for i in range(3)]
    worst = min(range(3), key=lambda i: rates[i])
    ans = f"{names[worst]} → {names[worst + 1]}"
    wrong = [f"{names[i]} → {names[i + 1]}" for i in range(3) if i != worst] + [f"{names[0]} → {names[3]}"]
    opts, c = _choice_options(rng, ans, wrong)
    table = " → ".join(f"{n}: {v:,}".replace(",", " ") for n, v in zip(names, steps))
    return ItemVariant(f"Воронка за неделю: {table}. На каком переходе самая низкая конверсия?", opts, c)


def gen_ab_uplift(rng: random.Random) -> ItemVariant:
    n = rng.choice([2000, 4000, 5000, 10_000])
    ca = rng.randint(4, 12) / 100
    lift = rng.choice([0.1, 0.15, 0.2, 0.25, 0.3, -0.1])
    a = round(n * ca)
    b = round(a * (1 + lift))
    ans = round((b / n) / (a / n) * 100 - 100)
    fmt = lambda v: f"{v:+d}%"
    opts, c = _numeric_options(rng, ans, [round((b - a) / n * 100), round((b - a) / b * 100), -ans], fmt)
    return ItemVariant(f"A/B-тест: в контроле {a} конверсий из {n}, в тесте {b} из {n}. "
                       "Каков относительный прирост конверсии теста к контролю?", opts, c)


def gen_pp_vs_pct(rng: random.Random) -> ItemVariant:
    before = rng.choice([2, 4, 5, 8, 10, 20])
    after = before + rng.choice([1, 2, 4, 5])
    kind = rng.choice(["pp", "pct"])
    if kind == "pp":
        ans = after - before
        q = f"Конверсия выросла с {before}% до {after}%. На сколько процентных пунктов она выросла?"
        opts, c = _numeric_options(rng, ans, [round((after - before) / before * 100), after, before], lambda v: f"{v} п.п.")
    else:
        ans = round((after - before) / before * 100)
        q = f"Конверсия выросла с {before}% до {after}%. На сколько процентов (относительно) она выросла?"
        opts, c = _numeric_options(rng, ans, [after - before, round((after - before) / after * 100), after], lambda v: f"{v}%")
    return ItemVariant(q, opts, c)


def gen_retention(rng: random.Random) -> ItemVariant:
    cohort = rng.choice([800, 1000, 1200, 2000, 2500])
    d = rng.choice([1, 7, 30])
    back = int(cohort * rng.uniform(0.08, 0.45))
    ans = round(back / cohort * 100)
    opts, c = _numeric_options(rng, ans, [100 - ans, round(back / (cohort - back) * 100), ans // 2], lambda v: f"{v}%")
    return ItemVariant(f"В когорте {cohort} новых пользователей. На {d}-й день вернулись {back}. "
                       f"Каков retention дня {d}?", opts, c)


def gen_arpu(rng: random.Random) -> ItemVariant:
    users = rng.choice([1000, 2000, 5000, 8000])
    payers = int(users * rng.uniform(0.03, 0.2))
    revenue = payers * rng.choice([300, 500, 750, 1200])
    kind = rng.choice(["ARPU", "ARPPU"])
    ans = round(revenue / (users if kind == "ARPU" else payers))
    other = round(revenue / (payers if kind == "ARPU" else users))
    opts, c = _numeric_options(rng, ans, [other, round(revenue / (users + payers)), ans * 2], _rub)
    return ItemVariant(f"За месяц: {users} активных пользователей, из них {payers} платящих, выручка {_rub(revenue)}. "
                       f"Чему равен {kind}?", opts, c)


def gen_bpmn_paths(rng: random.Random) -> ItemVariant:
    xor = [rng.randint(2, 3) for _ in range(rng.randint(2, 3))]
    and_ = rng.randint(2, 3)
    ans = math.prod(xor)
    parts = [f"исключающий шлюз (XOR) на {k} ветки" for k in xor]
    parts.insert(1, f"параллельный шлюз (AND) на {and_} ветки с последующим слиянием")
    opts, c = _numeric_options(rng, ans, [ans * and_, sum(xor) + and_, sum(xor)])
    return ItemVariant("Процесс в BPMN идёт последовательно через: " + "; ".join(parts) +
                       ". Сколько различных сценариев прохождения процесса нужно покрыть тест-кейсами "
                       "(параллельные ветки выполняются все)?", opts, c)


_REQS = [
    ("Система отправляет клиенту SMS с кодом подтверждения при входе", "функциональное"),
    ("Пользователь может выгрузить отчёт о заказах в формате CSV", "функциональное"),
    ("Оператор может заблокировать карту клиента по его звонку", "функциональное"),
    ("Страница каталога открывается не дольше 2 секунд при 1000 одновременных пользователей", "нефункциональное"),
    ("Сервис доступен 99,9% времени в месяц", "нефункциональное"),
    ("Пароли хранятся только в виде соли и хеша", "нефункциональное"),
    ("Интерфейс корректно работает в двух последних версиях Chrome и Firefox", "нефункциональное"),
    ("Нужно увеличить долю повторных покупок на 10% за квартал", "бизнес-требование"),
    ("Компании нужно сократить время обработки заявки до одного дня", "бизнес-требование"),
]


def gen_requirement_type(rng: random.Random) -> ItemVariant:
    text, ans = rng.choice(_REQS)
    opts, c = _choice_options(rng, ans, ["функциональное", "нефункциональное", "бизнес-требование", "ограничение (constraint)"])
    return ItemVariant(f"К какому типу относится требование: «{text}»?", opts, c)


def gen_link_table(rng: random.Random) -> ItemVariant:
    a_name, b_name = rng.choice([("студенты", "курсы"), ("заказы", "товары"), ("сотрудники", "проекты"), ("статьи", "теги")])
    na = rng.randint(20, 200)
    k = rng.randint(2, 6)
    ans = na * k
    opts, c = _numeric_options(rng, ans, [na + k, na, ans // 2])
    return ItemVariant(f"Связь «{a_name} — {b_name}» многие-ко-многим реализована таблицей связи. "
                       f"Есть {na} записей «{a_name}», каждая связана ровно с {k} записями «{b_name}». "
                       "Сколько строк в таблице связи?", opts, c)


# ---------------------------------------------------------------- Информационная безопасность

_CRYPTO = [("AES-256", "симметричное шифрование"), ("ChaCha20", "симметричное шифрование"), ("ГОСТ Р 34.12-2015 «Кузнечик»", "симметричное шифрование"),
           ("RSA", "асимметричное шифрование"), ("ECDH", "асимметричное шифрование"),
           ("SHA-256", "хеш-функция"), ("ГОСТ Р 34.11-2012 «Стрибог»", "хеш-функция"), ("bcrypt", "хеш-функция"),
           ("Base64", "кодирование, не защищает данные")]


def gen_crypto_kind(rng: random.Random) -> ItemVariant:
    name, ans = rng.choice(_CRYPTO)
    opts, c = _choice_options(rng, ans, ["симметричное шифрование", "асимметричное шифрование", "хеш-функция",
                                         "кодирование, не защищает данные"])
    return ItemVariant(f"К какому классу относится {name}?", opts, c)


def gen_bruteforce(rng: random.Random) -> ItemVariant:
    alpha = rng.choice([(10, "только цифры"), (26, "строчные латинские"), (36, "строчные латинские и цифры"),
                        (62, "латиница обоих регистров и цифры")])
    length = rng.randint(4, 8)
    rate, rate_txt = rng.choice([(10**6, "1 млн"), (10**8, "100 млн"), (10**9, "1 млрд")])
    seconds = alpha[0] ** length / rate
    scale = [(60, "меньше минуты"), (3600, "меньше часа"), (86400, "меньше суток"), (86400 * 365, "меньше года")]
    ans = next((t for lim, t in scale if seconds < lim), "больше года")
    opts, c = _choice_options(rng, ans, [t for _, t in scale] + ["больше года"])
    return ItemVariant(f"Пароль из {length} символов, алфавит — {alpha[1]} ({alpha[0]} символов). Атакующий перебирает "
                       f"{rate_txt} вариантов в секунду (офлайн, по утёкшему хешу). За какое время гарантированно "
                       "переберётся всё пространство?", opts, c)


def gen_vuln_class(rng: random.Random) -> ItemVariant:
    var = rng.choice(["user_id", "name", "q", "path", "host"])
    cases = [
        (f'cursor.execute("SELECT * FROM users WHERE id = " + request.args["{var}"])', "SQL-инъекция"),
        (f'element.innerHTML = "Привет, " + params.get("{var}")', "XSS (межсайтовый скриптинг)"),
        (f'open("/var/data/" + request.args["{var}"]).read()', "Path traversal (обход каталогов)"),
        (f'os.system("ping -c 1 " + request.args["{var}"])', "Внедрение команд ОС"),
    ]
    code, ans = rng.choice(cases)
    opts, c = _choice_options(rng, ans, [a for _, a in cases] + ["CSRF"])
    return ItemVariant("Какая уязвимость в этом фрагменте?", opts, c, code)


_PORTS = [(22, "SSH"), (53, "DNS"), (443, "HTTPS"), (3389, "RDP"), (5432, "PostgreSQL"), (25, "SMTP"), (3306, "MySQL"), (6379, "Redis")]


def gen_port_service(rng: random.Random) -> ItemVariant:
    port, ans = rng.choice(_PORTS)
    opts, c = _choice_options(rng, ans, [s for _, s in _PORTS])
    return ItemVariant(f"Сканирование показало открытый TCP-порт {port}. Какой сервис на нём обычно работает?", opts, c)


def gen_auth_log(rng: random.Random) -> ItemVariant:
    ips = [f"10.0.{rng.randint(0, 9)}.{rng.randint(2, 250)}" for _ in range(4)]
    ips = list(dict.fromkeys(ips))
    while len(ips) < 4:
        ips.append(f"192.168.1.{rng.randint(2, 250)}")
    threshold = rng.choice([5, 8, 10])
    fails = {ip: rng.randint(1, threshold - 1) for ip in ips}
    bad = rng.choice(ips)
    fails[bad] = threshold + rng.randint(0, 6)
    lines = []
    for ip, n in fails.items():
        lines += [f"Failed password for admin from {ip}"] * n
    lines += [f"Accepted password for dev from {rng.choice(ips)}" for _ in range(rng.randint(1, 3))]
    rng.shuffle(lines)
    opts, c = _choice_options(rng, bad, [ip for ip in ips if ip != bad] + ["ни один"])
    return ItemVariant(f"Правило SIEM: блокировать IP, с которого {threshold} и более неудачных входов за 5 минут. "
                       "Ниже — auth.log за последние 5 минут. Какой адрес должен быть заблокирован?",
                       opts, c, "\n".join(lines))


def gen_xor(rng: random.Random) -> ItemVariant:
    p = rng.randint(16, 250)
    k = rng.randint(16, 250)
    ans = p ^ k
    fmt = lambda v: f"0x{v:02X}"
    opts, c = _numeric_options(rng, ans, [(p + k) % 256, p & k, p | k], fmt)
    return ItemVariant(f"Однобайтовый XOR-шифр: открытый байт 0x{p:02X}, ключ 0x{k:02X}. Какой получится шифробайт?",
                       opts, c)
