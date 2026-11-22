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
и lock-файлы для запуска этих выпусков. Оба режима явно импортируют старую
входную схему без типа `object`. В каждой пробе сервер получает исходные
или преобразованные аргументы и работает с новой копией тестовых файлов
или графа. Абсолютные пути ограничены каталогом тестовых данных.

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

У каждой конфигурации свой каталог. `manifest.json` фиксирует версию
системной инструкции. `summary.json` содержит число сценариев
с обращением к модели, число запросов и допусков. По каждому сценарию
сохраняются решение и независимая оценка поведения. При повторном запуске
та же конфигурация продолжает сохранённый прогон. Предыдущие запросы
остаются в журнале. В сводной таблице повторным считается каждый запрос
после первого в том же сценарии.

## Проверка propertyNames и patternProperties

Синтетический набор запускается без установки внешних серверов.
Флаг `--provider` принимает `none`, `terra` или `codeagent`. Каждый
запуск сравнивает `strict` и `compat` на одних и тех же входах.

```sh
.venv/bin/python examples/schema_keyword_study.py --dataset synthetic --provider terra \
  --output experiments/keywords/synthetic-terra.json
```

Для проверок опубликованных серверов сохраняются исходные каталоги
`tools/list` и контрольные суммы. Firecrawl и Random User запускаются
по MCP. Ответы их внешних API задают локальные тестовые обработчики.
Стенд фиксирует сформированные сервером запросы к API, ответ MCP и
содержимое тестового файла. Сеть дочерних процессов заблокирована.
Две версии DOCX MCP нужны для контроля изменения схемы, обнаруживаемого
до пробного исполнения.

```sh
runtime=/private/tmp/mcp-keywords-release
for version in 3.24.0 3.25.0; do
  target="$runtime/npm/firecrawl-mcp/$version"
  mkdir -p "$target"
  cp "benchmark/schema-keywords/firecrawl/$version/"package*.json "$target/"
  npm ci --ignore-scripts --no-audit --no-fund --prefix "$target"
done
for rev in 531e85abff91c3ecf08cba9ace21b8ff440930dd 28d483c3492dd53bb739fbc499da0d3854e751cd; do
  target="$runtime/source/randomuser/$rev"
  mkdir -p "$target"
  curl -fsSL "https://codeload.github.com/rycid/randomuserMCP/tar.gz/$rev" -o "$target/source.tar.gz"
  tar -xzf "$target/source.tar.gz" --strip-components=1 -C "$target"
  npm ci --ignore-scripts --no-audit --no-fund --prefix "$target"
  "$target/node_modules/.bin/tsc" --project "$target/tsconfig.json"
done
for tag in v0.4.0 v0.5.0; do
  target="$runtime/source/docx/$tag"
  mkdir -p "$target"
  curl -fsSL "https://codeload.github.com/lihongjie0209/docx-mcp/tar.gz/refs/tags/$tag" -o "$target/source.tar.gz"
  tar -xzf "$target/source.tar.gz" --strip-components=1 -C "$target"
  npm ci --ignore-scripts --no-audit --no-fund --prefix "$target"
  "$target/node_modules/.bin/tsc" --project "$target/tsconfig.json"
done
MCP_EXTERNAL_NODE_RUNTIME="$runtime" .venv/bin/python examples/schema_keyword_study.py \
  --dataset published --provider none --output experiments/keywords/published-none.json
```

Запуск `tests/test_schema_keyword_study.py` проверяет сохранённые схемы
и синтетические сценарии. Чтобы включить в него вызовы опубликованных
серверов, задайте `MCP_COMPAT_RUN_PUBLISHED_KEYWORDS=1` и
`MCP_EXTERNAL_NODE_RUNTIME` с путём к установленным пакетам.

## Локальные тесты

```sh
.venv/bin/python -m pytest -q tests/test_external.py tests/test_external_study.py
.venv/bin/python -m pytest -q tests/test_upstream_contracts.py
```
