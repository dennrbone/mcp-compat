# Воспроизводимость

Ядро и научные опыты используют Python **3.11.4** и зависимости из
requirements.lock. Наборы данных и исследовательские артефакты поставляются
репозиторием; библиотечный wheel содержит Python-модули.

## Установка и инженерные проверки

Из корня полного clone с историей Git:

```sh
uv venv --python 3.11.4 .venv
uv pip sync --python .venv/bin/python --require-hashes requirements.lock
uv pip install --python .venv/bin/python --no-deps -e .
.venv/bin/python -m pytest -q --cov=mcp_compat --cov-branch --cov-report=term-missing --cov-fail-under=100
.venv/bin/ruff check src tests examples
.venv/bin/mypy src
.venv/bin/python -m build
```

Для pip используйте `pip install --require-hashes -r requirements.lock` и
затем `pip install --no-deps -e .`. Offline установка требует доступных wheels
или подготовленного кеша; lock сам по себе их не поставляет. В build isolation
backend setuptools может потребовать отдельной загрузки.

Политика покрытия относится к исходному пакету mcp_compat, statements и
branches. Примеры/документные сборщики не включаются в этот процент. Coverage
содержит стандартные исключения объявлений Protocol; новых исключений ради
прохождения gate не добавлялось.

## Анализ внешних результатов без новых вызовов

```sh
PYTHONPATH=examples .venv/bin/python -c 'from pathlib import Path; from external_results import audit; print([len(x) for x in audit(Path("experiments/external-admission-2026-11-04-v2"))])'
.venv/bin/python examples/admission_comparison.py --output /tmp/mcp-final-comparison-replica
MPLCONFIGDIR=/tmp/mcp-plots .venv/bin/python examples/final_publication_figures.py --output /tmp/mcp-final-figures-replica
```

Первая команда ожидает `[63, 441, 1453]`. Анализ сравнения читает V2 и отдельную
абляцию, проверяет первичные трассы и создаёт новые JSON/CSV. Каталог вывода
анализа должен отсутствовать. Серверы и модели не вызываются. Исходные оценки
не переписываются. Определения FAR и исторических метрик разделены в RESULTS.md.

## Точные экспериментальные исходники

`docs/validation/source-snapshots.json` содержит шесть полных commits и
контрольные хеши ядра/манифестов. Экспорт проверяет каждый выбранный снимок:

```sh
.venv/bin/python examples/export_research_sources.py external-v2 /tmp/mcp-source-v2
.venv/bin/python examples/export_research_sources.py final-admission /tmp/mcp-source-final
```

Доступны phase16/phase17/phase18/external-v1/external-v2/final-admission.
Экспортируются код, examples, зависимости и benchmark; текущие результаты
остаются в исходном clone. Нужна полная история Git, без переписывания старых
коммитов. Экспортированный код не выполняется автоматически.

Завершённый внешний V2 можно прочитать его собственным runner:

```sh
PYTHONPATH=/tmp/mcp-source-v2/src .venv/bin/python /tmp/mcp-source-v2/examples/external_study.py --output "$PWD/experiments/external-admission-2026-11-04-v2"
PYTHONPATH=/tmp/mcp-source-final/src .venv/bin/python /tmp/mcp-source-final/examples/admission_ablation.py --output "$PWD/experiments/final-admission-ablation-2026-11-05"
```

Ожидаются 441 и 126 записей. Совпадающие source/config fingerprints приводят
только к проверке хешей завершённого опыта, без новых вызовов. Исторические
модельные результаты пересчитываются отдельно:

```sh
PYTHONPATH=examples .venv/bin/python -c 'from pathlib import Path; from mcp_compat.analysis import read_results; from mcp_compat.experiments import summaries; print({regime:summaries(read_results(Path("experiments/terra-2026-11-03/runs")/regime)[1]) for regime in ("with-rules","without-rules")})'
```

Этот анализ не означает повторную генерацию ответов непрозрачных моделей.
Точные данные можно пересчитать; новые ответы сервиса не обязаны совпасть.

## Новое исполнение внешнего стенда

Нужны macOS с sandbox-exec, Node 26.9.0, SDK1 из lock и Node dependencies
из examples/external-filesystem/package-lock.json. На другой OS нужна отдельно
проверенная эквивалентная изоляция; иначе исполнение NOT RUN.

```sh
mkdir -p /private/tmp/mcp-external-filesystem
cp examples/external-filesystem/package*.json /private/tmp/mcp-external-filesystem/
(cd /private/tmp/mcp-external-filesystem && NODE_TLS_REJECT_UNAUTHORIZED=1 npm ci --ignore-scripts --no-audit --no-fund)
node examples/prepare_external_filesystem.mjs benchmark/external-mcp/vendor/fs /private/tmp/mcp-external-filesystem
PYTHONPATH=src .venv/bin/python examples/external_runtime.py
PYTHONPATH=src .venv/bin/python examples/admission_ablation.py --output /private/tmp/mcp-new-admission-run
```

Три isolation preflight должны явно сообщить `denied: true` и PermissionError.
Серверы запускаются с вымышленными файлами/строками базы и запрещённой сетью;
это не гарантия для произвольного враждебного кода. Новый выходной каталог
сохраняет отдельный manifest. Старые V1/V2 не продолжаются новой версией.

## SDK2 и документы

[Отдельное окружение MCP 2026-07-28](MCP_2026_COMPATIBILITY.md) сохраняет SDK1.
[Сборка и визуальная проверка DOCX](publication/README.md) используют отдельные
зависимости. Официальный schema source и внешние источники имеют сохранённые
MIT notices и pinned commits.
