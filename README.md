# MCP-Compat

Библиотека проверяет, сохранит ли вызов инструмента MCP своё поведение после
обновления сервера. Входом служат старый вызов и контракты обеих версий.
Hybrid ищет преобразование по встроенным правилам и при необходимости
обращается к подключённой языковой модели.

Сначала библиотека сверяет имя инструмента и аргументы с новой схемой.
Оба режима запускают версии на копиях одного состояния и сравнивают
ответы и конечное состояние. Режим `strict` требует полного сравнения схем.
В режиме `compat` проверку можно начать при поддерживаемых изменениях,
которые анализатор разобрал частично. В эксперименте Hybrid в обоих режимах проверял
актуальный снимок и повторял сравнение перед допуском.

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

Наборы эксперимента включают 200 сценариев совместимости, 23 изменения
схем в опубликованных версиях серверов и отдельные проверки
`propertyNames` и `patternProperties`. Данные и команды запуска описаны
в [инструкции воспроизведения](docs/REPRODUCIBILITY.md).

```sh
.venv/bin/python -m pytest -q
.venv/bin/ruff check src tests examples
.venv/bin/mypy src
```

## Документация

- [Как работает строгая проверка](docs/METHOD_FORMALIZATION.md)
- [Подключение CodeAgent и Terra](docs/PROVIDERS.md)
- [Встраивание библиотеки](docs/CLIENT_INTEGRATION.md)
- [Интеграция MCP SDK 1](docs/MCP_INTEGRATION.md)
- [Проверяемый профиль MCP 2026-07-28](docs/MCP_2026_COMPATIBILITY.md)
- [Условия повторного запуска](docs/REPRODUCIBILITY.md)
- [Данные и результаты проверок](docs/RESULTS.md)
