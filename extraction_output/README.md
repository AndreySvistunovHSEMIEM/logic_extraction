# Pipeline извлечения словаря подозрительных паттернов из IT-резюме

Async-pipeline, который обрабатывает ~4400 IT-резюме через Claude CLI, извлекая подозрительные паттерны и правила противоречий для системы фактчекинга.

## Запуск

```bash
# Все оставшиеся файлы, 10 параллельных сессий (по умолчанию)
python3 extract_pipeline.py

# Только 50 файлов
python3 extract_pipeline.py -n 50

# 100 файлов, 5 параллельных сессий
python3 extract_pipeline.py -n 100 -c 5
```

Требования: Claude CLI (`claude`) в PATH, подписка Claude Code.

## Алгоритм

```
1. Инициализация
   └─ Если accumulated_results.json не существует:
      └─ Создать с baseline из domain/rules.py (13 vocab + 7 rules)

2. Сбор файлов
   ├─ Обход 4 папок в HRom_resume_fabricated/
   ├─ Фильтр по расширению: .pdf, .docx, .txt
   ├─ Пропуск уже обработанных (есть в processed_files)
   └─ Применение лимита -n (если указан)

3. Параллельная обработка (asyncio, семафор на -c сессий)
   Для каждого файла:
   ├─ Сборка промпта: шаблон + текущий vocab + текущие rules
   ├─ Вызов: claude -p "$prompt" --allowedTools Read --output-format json --model sonnet
   ├─ Парсинг JSON-ответа (с извлечением из markdown-обёрток)
   ├─ Мерж результатов в accumulated_results.json (под asyncio.Lock):
   │   ├─ Новые переменные → дедупликация по имени
   │   ├─ Новые правила → дедупликация по формуле
   │   └─ Запись source-файла для трекинга
   └─ При ошибке: до 2 ретраев, затем record-error

4. Возобновляемость
   └─ Повторный запуск пропускает файлы из processed_files
```

## Что извлекает Claude

Claude анализирует каждое резюме как **неблагонадёжное** и ищет:

- **Раздутые метрики** — «ускорил на 400%» без описания методологии
- **Buzzword-наполнение** — 15 технологий за 1 год без контекста
- **Несовместимые утверждения** — «руководил командой» при 2 годах опыта
- **Масштаб vs ресурсы** — «внедрил микросервисы» командой из 2 человек
- **Голословные заявления** — метрики без упоминания инструментов/процессов

Результат — переменные (паттерны) и правила (логические связи), которые потом использует Z3-фактчекер в `logic_extraction/`.

## Файлы

| Файл | Назначение |
|---|---|
| `extract_pipeline.py` | Главный async-скрипт |
| `merge_results.py` | Хелпер: init / merge / record-error (CLI + используется pipeline) |
| `prompt_template.txt` | Шаблон промпта для Claude с подстановкой `$RESUME_PATH`, `$CURRENT_VOCAB_JSON`, `$CURRENT_RULES_JSON` |
| `accumulated_results.json` | Накопительный JSON с vocab, rules, processed_files |
| `pipeline.log` | Лог выполнения |

## Структура accumulated_results.json

```json
{
  "metadata": {
    "last_updated": "2026-03-07T...",
    "total_processed": 142,
    "total_errors": 3
  },
  "vocabulary": {
    "inflatedMetrics": {
      "description": "Нереалистичные метрики улучшений (>200%)",
      "sources": ["Flood_resume_CV_done/file.pdf"],
      "is_baseline": false
    }
  },
  "rules": [
    {
      "label": "rule_lead_vs_experience",
      "formula": "leadsClaim & ~thoroughDesign -> shortcutArch",
      "sources": ["CV_mostly_English_done/cv_mostly_english/file.pdf"],
      "is_baseline": false
    }
  ],
  "processed_files": {
    "Flood_resume_CV_done/file.pdf": {
      "status": "success",
      "timestamp": "...",
      "vocab_added": 2,
      "rules_added": 1,
      "claims_found": 5
    }
  }
}
```
