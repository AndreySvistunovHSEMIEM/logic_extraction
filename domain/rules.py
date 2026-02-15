"""Доменные правила (эвристики) для резюме в области разработки ПО.

Каждое правило — кортеж (метка, строка_формулы).
Метки используются Z3 assert_and_track для извлечения unsat core.
"""

DOMAIN_RULES: list[tuple[str, str]] = [
    # Быстрые изменения ведут к росту багов
    ("rule_fast_bugs", "fastChanges -> moreBugs"),
    # Улучшение стабильности подразумевает меньше изменений
    ("rule_stability_less_changes", "improvedStability -> lessChanges"),
    # Нельзя одновременно: больше багов и меньше изменений
    ("rule_bugs_changes_conflict", "~(moreBugs & lessChanges)"),
    # Качественная архитектура требует тщательного проектирования
    ("rule_quality_design", "qualityArch -> thoroughDesign"),
    # Быстрые изменения ведут к упрощённой архитектуре
    ("rule_fast_shortcut", "fastChanges -> shortcutArch"),
    # Упрощённая и тщательная архитектура несовместимы
    ("rule_shortcut_thorough_conflict", "~(shortcutArch & thoroughDesign)"),
    # SDUI влечёт проблемы совместимости, необходимость отката и мониторинга
    ("rule_sdui_concerns", "sdui -> compatibility & rollback & monitoring"),
]

# Словарь доменных переменных с описаниями.
# LLM ОБЯЗАН использовать именно эти имена при извлечении утверждений,
# чтобы Z3 мог связать утверждения с правилами.
DOMAIN_VOCABULARY: dict[str, str] = {
    "fastChanges": "Быстрые изменения, короткие циклы разработки, сокращение цикла запуска/релиза",
    "moreBugs": "Рост количества багов, увеличение ошибок",
    "improvedStability": "Улучшение стабильности, рост crash-free rate, снижение сбоев",
    "lessChanges": "Меньше изменений, реже правки кода",
    "qualityArch": "Качественная архитектура, модульная архитектура, слоистая декомпозиция, чистая архитектура",
    "thoroughDesign": "Тщательное проектирование, продуманный дизайн системы",
    "shortcutArch": "Упрощённая архитектура, архитектурные срезы, быстрые решения",
    "sdui": "Server-Driven UI, динамический UI с сервера, JSON-конфигурации интерфейса",
    "compatibility": "Проблемы совместимости версий",
    "rollback": "Необходимость отката изменений",
    "monitoring": "Необходимость мониторинга",
    "reducedErrors": "Сокращение ошибок в production",
    "highTestCoverage": "Высокое покрытие тестами",
}
