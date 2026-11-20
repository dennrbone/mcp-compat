# Воспроизведение проверок

## Локальные тесты

```sh
.venv/bin/python -m pytest -q tests/test_upstream_contracts.py
.venv/bin/python -m pytest -q tests/test_external.py tests/test_external_results.py
```

`tests/fixtures/upstream-catalogs.json` содержит исходные каталоги `tools/list`,
записанные ответы на выбранные вызовы, версии пакетов, ссылки на npm и
контрольные суммы архивов. Тесты проверяют 50 изменений схем, происхождение
набора и пять пар записанных вызовов Filesystem и Memory.

## Проверки на 200 сценариях

Замороженные входы и эталон хранятся в `benchmark/external-mcp-200`.
Для записи копии в новый каталог используйте функцию `freeze` из
`examples/external_200_dataset.py`. Она читает первоначальный набор
`benchmark/external-mcp`.

Для локального запуска Filesystem подготовьте точные зависимости.
Пример предполагает macOS и текущий каталог проекта.

```sh
runtime=/private/tmp/mcp-external-filesystem
mkdir -p "$runtime"
cp examples/external-filesystem/package.json examples/external-filesystem/package-lock.json "$runtime/"
NODE_TLS_REJECT_UNAUTHORIZED=1 npm ci --prefix "$runtime" --ignore-scripts --no-audit --no-fund
node examples/prepare_external_filesystem.mjs benchmark/external-mcp/vendor/fs "$runtime"
```

Проверка фиксированных кандидатов

```sh
.venv/bin/python examples/external_200_evaluate.py fixed --output experiments/external-mcp-200/fixed
```

Для оценки результатов генераторов сначала сохраните ответы по
[инструкции подключения](PROVIDERS.md), затем укажите соответствующий каталог.

```sh
.venv/bin/python examples/external_200_evaluate.py terra \
  --proposals experiments/external-mcp-200/terra \
  --output experiments/external-mcp-200/evaluation-terra
```

На macOS проверка изоляции выполняется до запуска инструментов. Сводные
показатели сохраняются в `summary.json`, а решения и исходные наблюдения —
в папках сценариев. Первичные данные завершённых исследований хранятся отдельно
от рабочей ветки.
