# MCP-Compat

Библиотека проверяет, сохранит ли вызов инструмента MCP своё поведение после
обновления сервера. Входом служат старый вызов и контракты обеих версий.
Кандидат для новой версии можно подготовить по правилам или получить от
языковой модели.

Сначала библиотека сверяет имя инструмента и аргументы с новой схемой.
Строгая проверка запускает обе версии на копиях одного состояния и сравнивает
ответы и конечное состояние. Перед допуском она проверяет актуальный снимок
и повторяет сравнение.

## Установка

Для основного окружения используется Python 3.11.4.

```sh
uv venv --python 3.11.4 .venv
uv pip sync --python .venv/bin/python --require-hashes requirements.lock
uv pip install --python .venv/bin/python --no-deps -e .
```

## Проверка вызова по схеме

```python
from mcp_compat import ToolCall, ToolContract

contract = ToolContract(
    name="reserve_stock",
    input_schema={
        "type": "object",
        "properties": {"quantity": {"type": "integer", "minimum": 1}},
        "required": ["quantity"],
    },
)
call = ToolCall(tool_name="reserve_stock", arguments={"quantity": 2})
call.validate_against(contract)
```

При недопустимом имени или аргументе `validate_against` выбрасывает
`ToolCallValidationError`. Для сравнения версий служит `SchemaDiffEngine`.
`EvidenceVerifier.verify` записывает результат предварительной проверки,
а `admit` принимает окончательное решение по актуальному снимку.

## Тесты

```sh
.venv/bin/python -m pytest -q
.venv/bin/ruff check src tests examples
.venv/bin/mypy src
```

## Документация

- [Как работает строгая проверка](docs/METHOD_FORMALIZATION.md)
- [Подключение клиента](docs/CLIENT_INTEGRATION.md)
- [Интеграция MCP SDK 1](docs/MCP_INTEGRATION.md)
- [Проверяемый профиль MCP 2026-07-28](docs/MCP_2026_COMPATIBILITY.md)
- [Условия повторного запуска](docs/REPRODUCIBILITY.md)
- [Данные и результаты проверок](docs/RESULTS.md)
