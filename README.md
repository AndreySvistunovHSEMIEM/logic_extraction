# Resume Fact-Checker: LLM + Z3

Прототип системы логического фактчекинга резюме. Извлекает утверждения из текста резюме с помощью LLM, формализует их в пропозициональную логику и проверяет на непротиворечивость с доменными правилами через Z3 SMT-солвер.

## Архитектура

```
Резюме (txt/pdf)
      |
      v
+--------------+
| LLM Extract  |  LLM: текст -> claims (label + formula + цитата)
+------+-------+
       v
+--------------+
| Lark Parse   |  Строки формул -> типизированный AST
+------+-------+
       v
+--------------+
|  Z3 Check    |  AST -> Z3 BoolRef, assert_and_track, SAT/UNSAT + unsat core
+------+-------+
       v
+--------------+
| LLM Analyze  |  Unsat core -> человекочитаемый анализ противоречий
+------+-------+
       v
   JSON-отчёт
```

## Структура проекта

```
logic_extraction/
├── main.py                      # CLI, 4-стадийный пайплайн
├── config.py                    # Загрузка .env, API ключи
├── pyproject.toml               # Зависимости и метаданные проекта
├── grammar/
│   └── logic.lark               # Lark-грамматика пропозициональной логики
├── parser/
│   ├── ast_nodes.py             # Dataclasses: Var, Pred, Not, And, Or, Implies, Bicond, Const
│   └── logic_parser.py          # Lark parser + LogicTransformer
├── prover/
│   └── z3_checker.py            # AST -> Z3, sat check, unsat core extraction
├── llm/
│   ├── extractor.py             # Резюме -> предикаты + формулы
│   ├── analyzer.py              # Unsat core -> анализ противоречий
│   └── prompts.py               # Системные промпты (на русском)
├── domain/
│   └── rules.py                 # Доменные правила + словарь переменных
├── web/
│   └── app.py                   # Flask web UI
├── examples/
│   ├── resume_contradictory.txt # Резюме с противоречиями (iOS-разработчик)
│   └── resume_good.txt          # Согласованное резюме (C#-разработчик)
├── tests/
│   ├── test_parser.py           # 17 тестов
│   └── test_z3_checker.py       # 6 тестов
├── .env                         # API ключи (не коммитить)
└── .env.example                 # Шаблон .env
```

## Установка

Проект использует [uv](https://docs.astral.sh/uv/) для управления зависимостями и виртуальным окружением.

```bash
uv sync
cp .env.example .env
# Вписать OPENAI_API_KEY в .env
```

## Запуск

```bash
# Резюме с противоречиями (ожидается UNSAT)
uv run python main.py --resume examples/resume_contradictory.txt --verbose

# Согласованное резюме (ожидается SAT)
uv run python main.py --resume examples/resume_good.txt --verbose

# Сохранить отчёт в файл
uv run python main.py --resume examples/resume_contradictory.txt -o report.json

# PDF-резюме
uv run python main.py --resume /path/to/resume.pdf

# Web UI
uv run python -m web.app
```

## Тесты

```bash
uv run pytest tests/ -v
```

## Web UI

Браузерный интерфейс для проверки резюме без командной строки.

```bash
uv run python -m web.app
# Сервер запустится на http://localhost:8080
```

### API

| Метод | Эндпоинт | Описание |
|-------|----------|----------|
| `GET` | `/` | HTML-страница с формой загрузки |
| `GET` | `/api/health` | Статус сервера и используемая LLM-модель |
| `POST` | `/api/check` | Загрузка резюме и запуск пайплайна |

### POST /api/check

Принимает `multipart/form-data` с полем `file` (`.txt` или `.pdf`, до 5 МБ). Возвращает JSON-отчёт — тот же формат, что и CLI с флагом `-o`.

Пример через curl:
```bash
curl -X POST http://localhost:8080/api/check \
  -F "file=@examples/resume_contradictory.txt"
```

## Как работает Z3 Checker

### Что такое Z3

[Z3](https://github.com/Z3Prover/z3) — SMT-солвер (Satisfiability Modulo Theories) от Microsoft Research. SMT-солвер решает задачу выполнимости: дан набор логических формул, существует ли такое присвоение значений переменным, при котором **все** формулы одновременно истинны?

В нашем случае Z3 работает в теории пропозициональной логики (булевы переменные + связки `~`, `&`, `|`, `->`, `<->`). Это частный случай SMT, эквивалентный задаче [SAT](https://en.wikipedia.org/wiki/Boolean_satisfiability_problem).

### Claims (утверждения из резюме)

Claims — это формулы, извлечённые LLM из текста резюме. Каждый claim содержит:

| Поле | Описание | Пример |
|------|----------|--------|
| `label` | Уникальная метка | `claim_1` |
| `original_text` | Цитата из резюме | *«сократил цикл запуска с 5 дней до 1 часа»* |
| `formula` | Формула пропозициональной логики | `fastChanges` |

LLM использует доменный словарь (`DOMAIN_VOCABULARY`), чтобы маппить факты из текста на фиксированные имена переменных. Например, фраза *«модульная архитектура с четкой слоистой декомпозицией»* превращается в формулу `qualityArch`.

### Rules (доменные правила)

Rules — экспертные эвристики из `domain/rules.py`, кодирующие инженерные закономерности. Каждое правило — пара `(метка, формула)`:

| Метка | Формула | Смысл |
|-------|---------|-------|
| `rule_fast_bugs` | `fastChanges -> moreBugs` | Быстрые изменения ведут к росту багов |
| `rule_stability_less_changes` | `improvedStability -> lessChanges` | Стабильность подразумевает меньше изменений |
| `rule_bugs_changes_conflict` | `~(moreBugs & lessChanges)` | Больше багов и меньше изменений несовместимы |
| `rule_quality_design` | `qualityArch -> thoroughDesign` | Качественная архитектура требует тщательного проектирования |
| `rule_fast_shortcut` | `fastChanges -> shortcutArch` | Быстрые изменения ведут к упрощённой архитектуре |
| `rule_shortcut_thorough_conflict` | `~(shortcutArch & thoroughDesign)` | Упрощённая и тщательная архитектура несовместимы |
| `rule_sdui_concerns` | `sdui -> compatibility & rollback & monitoring` | SDUI влечёт проблемы совместимости |

Правила не берутся из резюме — их пишет эксперт предметной области. Они выражают общеизвестные инженерные trade-off'ы.

### Как Z3 проверяет непротиворечивость

Процесс проверки (`Z3Checker.check`) состоит из трёх шагов:

**1. Конвертация AST -> Z3 BoolRef**

Каждая формула (claim или rule) рекурсивно преобразуется из нашего AST в выражение Z3:

```
AST Var("fastChanges")       ->  z3.Bool("fastChanges")
AST Implies(Var("a"), Var("b"))  ->  z3.Implies(z3.Bool("a"), z3.Bool("b"))
AST Not(And(Var("x"), Var("y"))) ->  z3.Not(z3.And(z3.Bool("x"), z3.Bool("y")))
```

**2. assert_and_track — добавление формул с метками**

Каждая Z3-формула добавляется в солвер через [`assert_and_track(formula, label)`](https://z3prover.github.io/api/html/classz3py_1_1_solver.html#a5765c8e445370f5b1a4c8ce19d852587). Это аналог обычного `assert`, но с привязкой к маркеру — булевой переменной `label_<имя>`. Маркер нужен для того, чтобы при обнаружении противоречия Z3 мог указать, **какие именно формулы** в нём участвуют.

```python
for label, formula in labeled_formulas:
    z3_formula = self.to_z3(formula)
    p = z3.Bool(f"label_{label}")
    solver.assert_and_track(z3_formula, p)
```

**3. solver.check() — SAT или UNSAT**

Z3 пытается найти модель — набор значений `True`/`False` для всех переменных, при котором все формулы истинны одновременно:

- **SAT** (satisfiable) — модель найдена, все claims и rules совместимы. Противоречий нет. Z3 возвращает конкретную модель (например: `fastChanges = False, qualityArch = True, ...`).

- **UNSAT** (unsatisfiable) — модели не существует, формулы логически несовместимы. Z3 дополнительно извлекает **unsat core** — минимальное подмножество формул, которое уже само по себе противоречиво.

### Unsat core — ядро противоречия

Unsat core — ключевая возможность Z3 для диагностики. Из всех добавленных формул (7 rules + 5–15 claims) Z3 выделяет **минимальный** набор, достаточный для противоречия. Например:

```
Unsat core: [rule_fast_bugs, rule_fast_shortcut, rule_shortcut_thorough_conflict,
             rule_quality_design, claim_1, claim_3]
```

Это означает: если убрать любую из этих формул, оставшиеся станут непротиворечивы. Именно этот набор передаётся LLM для анализа на человеческом языке.

### Пример: почему UNSAT

Допустим, резюме заявляет `fastChanges` (claim_1) и `qualityArch` (claim_3). По цепочке правил:

```
fastChanges                          (claim_1)
fastChanges -> shortcutArch          (rule_fast_shortcut)
∴ shortcutArch                       (modus ponens)

qualityArch                          (claim_3)
qualityArch -> thoroughDesign        (rule_quality_design)
∴ thoroughDesign                     (modus ponens)

~(shortcutArch & thoroughDesign)     (rule_shortcut_thorough_conflict)
```

Получаем `shortcutArch = True`, `thoroughDesign = True`, но правило запрещает их одновременную истинность. Противоречие — UNSAT.

## Примеры резюме

### resume_contradictory.txt (с противоречиями)

iOS-разработчик (Плавов Савелий). Содержит утверждения, которые вступают в конфликт с доменными правилами:

- *«сократил цикл запуска с 5 дней до 1 часа»* -- подразумевает `fastChanges`
- *«модульная архитектура с четкой слоистой декомпозицией»* -- подразумевает `qualityArch`
- *«сократил ошибки в production на 35%»* + *«crash-free rate 99.6%»* -- подразумевает `improvedStability`

Z3 находит UNSAT: быстрые изменения по доменным правилам ведут к упрощённой архитектуре и росту багов, что несовместимо с заявленным качеством и стабильностью.

### resume_good.txt (согласованное)

C#-разработчик (Шигапов Камиль). Утверждения не конфликтуют: стабильность, retry-механизмы, Outbox pattern, рефакторинг -- всё согласуется без логических напряжений. Z3 ожидаемо возвращает SAT.

## Грамматика логики

Приоритет операций (от низшего к высшему):

| Приоритет | Оператор | Значение |
|-----------|----------|----------|
| 1 | `<->` | Бикондиционал |
| 2 | `->` | Импликация (правоассоциативная) |
| 3 | `\|` | Дизъюнкция |
| 4 | `&` | Конъюнкция |
| 5 | `~` | Отрицание |

Атомы: `variable`, `predicate(args)`, `true`, `false`, `(formula)`.

## Доменный словарь и связывание LLM с Z3

Ключевая проблема архитектуры: LLM и Z3 — два независимых компонента, которые должны "говорить на одном языке". Доменные правила жёстко используют конкретные имена переменных (`fastChanges`, `qualityArch`), и LLM при извлечении утверждений из резюме **обязан использовать те же имена**, иначе Z3 не сможет связать утверждения с правилами.

### Что произойдёт без словаря

Без явного словаря LLM придумает свои имена переменных:
- `reducedCycle("5d","1h")` вместо `fastChanges`
- `modularArch` вместо `qualityArch`
- `crashFreeRate` вместо `improvedStability`

Z3 увидит два непересекающихся набора переменных — правила про `fastChanges`, утверждения про `reducedCycle`. Они никак не связаны, поэтому Z3 тривиально найдёт модель, где всё совместимо. Противоречие останется невидимым, и результат будет SAT даже на заведомо противоречивом резюме.

### Как работает словарь

Файл `domain/rules.py` содержит `DOMAIN_VOCABULARY` — словарь, где ключ — имя переменной, значение — описание на русском:

```python
DOMAIN_VOCABULARY = {
    "fastChanges": "Быстрые изменения, короткие циклы разработки, сокращение цикла запуска/релиза",
    "qualityArch": "Качественная архитектура, модульная архитектура, слоистая декомпозиция",
    ...
}
```

При построении промпта (`llm/prompts.py: build_extraction_prompt`) этот словарь вставляется в системное сообщение с инструкцией: *«Используй ИМЕННО эти доменные переменные, не придумывай свои»*. Это гарантирует, что формулы LLM и доменные правила ссылаются на одни и те же переменные → Z3 может обнаружить реальные противоречия.

### Разделение ответственности

| Компонент | Роль | Почему именно он |
|-----------|------|-----------------|
| **LLM** | Извлекает факты из текста | Хорош в NLU, плох в формальной логике |
| **Эксперт** | Пишет доменные правила и словарь | Знает предметную область |
| **Словарь** | Связывает LLM и правила | Контракт/онтология между компонентами |
| **Z3** | Проверяет непротиворечивость | Математически точен, без галлюцинаций |

### Альтернативные подходы (и почему они хуже)

- **LLM сама генерирует правила** — нестабильно (разный результат при каждом запуске), подвержено галлюцинациям, замкнутый круг (LLM сама решает, что считать противоречием).
- **Маппинг после извлечения** — дополнительный LLM-вызов для сопоставления `reducedCycle` ↔ `fastChanges`, ещё один источник ошибок.
- **Без доменных правил** — Z3 проверяет только внутреннюю непротиворечивость утверждений, без экспертных эвристик. Для большинства резюме результат будет тривиально SAT.

## Материалы

- [Z3 GitHub](https://github.com/Z3Prover/z3) — исходный код и документация Z3
- [Z3 Python API (z3-solver)](https://z3prover.github.io/api/html/namespacez3py.html) — справочник Python API
- [Z3 Guide (rise4fun)](https://microsoft.github.io/z3guide/) — интерактивный учебник по Z3 от Microsoft
- [SAT problem (Wikipedia)](https://en.wikipedia.org/wiki/Boolean_satisfiability_problem) — задача булевой выполнимости
- [SMT (Wikipedia)](https://en.wikipedia.org/wiki/Satisfiability_modulo_theories) — Satisfiability Modulo Theories
- [Lark parser](https://github.com/lark-parser/lark) — парсер, используемый для разбора формул
- [Programming Z3 (tutorial)](https://theory.stanford.edu/~nikolaj/programmingz3.html) — подробный туториал от одного из авторов Z3
