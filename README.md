# MCP-Compat

MCP-Compat — исследовательский прототип восстановления вызовов после изменения
контрактов MCP. Включает типизированные модели, консервативный diff C1–C8,
контролируемые адаптеры, независимую проверку локальных реализаций и отказ при
недостатке оснований. Реальные тесты выполняются только установленным GigaCode
CodeAgent; интерфейс LLMClient и стандартный MCP позволяют подключать других
клиентов без привязки ядра к конкретному поставщику.

Завершены один полный исходный прогон, детерминированные контроли и отдельная
прикладная проверка с тремя повторами в двух условиях. Первоначальный план с
несколькими семействами моделей целиком не выполнен. Результаты, включая
невыгодные для полного гибрида сравнения: [подтверждённое состояние](docs/RESULTS_STATUS.md),
[рукопись](docs/ARTICLE_DRAFT.md), [отчёты фаз](docs/PHASE_REPORTS.md).
Прототип не объявляется готовым для production; ограничения проверки — в статье.

## Setup

Use Python 3.11.4:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install --require-hashes -r requirements.lock
python -m pip install --no-deps -e .
```

## Validation example

`ToolCall.validate_against` returns `None` for a valid call and raises `ToolCallValidationError` for a wrong tool name or invalid arguments.

```python
from mcp_compat import ToolCall, ToolCallValidationError, ToolContract

contract = ToolContract(
    name="reserve_stock",
    input_schema={
        "type": "object",
        "properties": {"quantity": {"type": "integer", "minimum": 1}},
        "required": ["quantity"],
    },
)

ToolCall(tool_name="reserve_stock", arguments={"quantity": 2}).validate_against(contract)

try:
    ToolCall(tool_name="reserve_stock", arguments={}).validate_against(contract)
except ToolCallValidationError as error:
    print(error)
```

Models use Pydantic's `model_dump_json` and `model_validate_json` for JSON round trips. Pass `model_dump(mode="json")` to `canonical_json` or `canonical_bytes` when deterministic serialization is required.

## Tests

Run the tests:

```bash
pytest -q
```

Run the full quality gate:

```bash
pytest -q --cov=mcp_compat --cov-branch --cov-report=term-missing --cov-report=xml --cov-fail-under=100
```

All source modules retain the Phase 2 requirement of 100% statement and branch
coverage. GitHub Actions includes tests, lint, types, packaging and offline e2e.
Real provider smoke tests are opt-in and otherwise report SKIP / NOT RUN.
The installed GigaCode uses CodeAgent; other models and agents connect through
the generic model interface and standard MCP. See [provider setup and test commands](docs/PROVIDERS.md).

Development and recovery improvements use separate stacked branches; no merge into main has
been performed. Review dependencies are listed in docs/IMPLEMENTATION_PLAN.md.

## Offline demo

```bash
mcp-compat-demo --output /tmp/mcp-offline-demo
mcp-compat-analyze --run /tmp/mcp-offline-demo --output /tmp/mcp-offline-analysis
```

This runs 45 frozen cases for B0–B3/M1/A1–A4 using an explicitly fake provider.
It tests the pipeline, not model quality. Main studies need actual model versions,
authorized access/resources and independently supplied runtime verification;
unbound M1 cases abstain. Active data: `benchmark/manifest.json` (evobench-1.2).


## Deterministic schema diff

```python
from mcp_compat import SchemaDiffEngine, canonical_bytes

diff = SchemaDiffEngine.compare(old_contract, new_contract)
print(diff.has_changes, diff.is_complete)
print(canonical_bytes(diff.model_dump(mode="json")))
```

The engine reports typed changes with stable schema paths and ordering. It handles
properties, required membership, nested objects, array items, types/nullable unions,
formats, enums and acyclic local `$defs` references. Parameter renames require
unique unchanged reference identity; matching names/types alone never suffice.
C8 uses explicit `semantic_unit` markers only. Nesting/flattening may appear as
primitive additions/removals. Unsupported constructs appear in `diff.opaque`;
`has_changes=False` does not imply a complete comparison when `is_complete=False`.
The engine makes no EXECUTE/ABSTAIN decision. See
[implementation conventions and limitations](docs/IMPLEMENTATION_NOTES.md).

## Материалы исследования на русском

- [Рукопись](docs/ARTICLE_DRAFT.md) и [обзор первичных источников](docs/LITERATURE_REVIEW.md).
- [Данные, протокол и команды](docs/PUBLICATION_SUPPLEMENT.md).
- [Подтверждённые результаты и ограничения](docs/RESULTS_STATUS.md).

Завершены исходные 19440 решений CodeAgent, 4320 детерминированных контролей
и отдельный прикладной опыт из 5760 решений с тремя повторами в двух условиях.
Контроли не подтверждают универсального превосходства полного гибрида.
Репозиторий приватный; публикация статьи и merge в main не выполнялись.
