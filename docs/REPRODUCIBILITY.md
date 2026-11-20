# Воспроизведение проверок Hybrid

Оба набора запускаются на macOS в изолированной среде с Python 3.11 и Node.js
из `/opt/homebrew/bin/node`. Перед вызовами стенд проверяет, что серверы
не могут читать служебные файлы проекта, писать за пределами рабочей папки
или подключаться к сети. Модели подключаются через локальные клиенты.
[Настройка клиентов](PROVIDERS.md).

## Набор из 200 сценариев

Входы и эталон хранятся в `benchmark/external-mcp-200`.
Эталон открывается после записи решений Hybrid. Версии тестовых серверов
закреплены в `benchmark/external-mcp/vendor`.

```sh
runtime=/private/tmp/mcp-external-filesystem
mkdir -p "$runtime"
cp examples/external-filesystem/package.json examples/external-filesystem/package-lock.json "$runtime/"
NODE_TLS_REJECT_UNAUTHORIZED=1 npm ci --prefix "$runtime" --ignore-scripts --no-audit --no-fund
node examples/prepare_external_filesystem.mjs benchmark/external-mcp/vendor/fs "$runtime"

for mode in strict compat; do
  for provider in codeagent terra; do
    MCP_EXTERNAL_NODE_RUNTIME="$runtime" .venv/bin/python examples/hybrid_study.py \
      --dataset external --provider "$provider" --hybrid-mode "$mode" \
      --output "experiments/hybrid/external-$mode-$provider"
  done
done
```

## Набор из 23 исторических изменений

В `tests/fixtures/upstream-catalogs.json` сохранены реальные каталоги
четырёх выпусков Filesystem и Memory и контрольные суммы npm.
В `benchmark/external-mcp-historical` хранятся тестовые аргументы
и lock-файлы для запуска этих выпусков. Стенд выполняет прежние
и новые вызовы на копиях тестовых файлов и графа.

```sh
runtime=/private/tmp/mcp-historical-runtime
fixtures=benchmark/external-mcp-historical
for lock in "$fixtures"/*/*/package-lock.json; do
  target="$runtime/${lock#$fixtures/}"
  work="$(dirname "$target")"
  mkdir -p "$work"
  cp "$lock" "$(dirname "$lock")/package.json" "$work/"
  NODE_TLS_REJECT_UNAUTHORIZED=1 npm ci --prefix "$work" --ignore-scripts --no-audit --no-fund
done

for mode in strict compat; do
  for provider in codeagent terra; do
    MCP_EXTERNAL_NODE_RUNTIME="$runtime" .venv/bin/python examples/hybrid_study.py \
      --dataset historical --provider "$provider" --hybrid-mode "$mode" \
      --output "experiments/hybrid/historical-$mode-$provider"
  done
done
```

У каждой конфигурации свой каталог. `summary.json` содержит число сценариев
с обращением к модели, число попыток и допусков. По каждому сценарию
сохраняются решение и независимая оценка поведения. При повторном запуске
та же конфигурация продолжает сохранённый прогон. Предыдущие запросы
остаются в журнале. В сводной таблице повторным считается каждый запрос
после первого в том же сценарии.

## Локальные тесты

```sh
.venv/bin/python -m pytest -q tests/test_external.py tests/test_external_results.py
.venv/bin/python -m pytest -q tests/test_upstream_contracts.py
```
