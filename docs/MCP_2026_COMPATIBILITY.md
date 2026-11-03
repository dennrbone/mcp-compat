# Проверенный профиль MCP 2026-07-28

Дата: 04.11.2026. Это минимальный проверенный профиль, не декларация полной
совместимости со всеми возможностями спецификации.

Первичные источники: [официальная спецификация](https://modelcontextprotocol.io/specification/2026-07-28),
[объявление изменения протокола](https://blog.modelcontextprotocol.io/posts/2026-07-28/),
[TypeScript source](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/271ecc9accafdd9b83a3c869fa67c22953b2af80/schema/2026-07-28/schema.ts).
TS и JSON Schema сохранены вместе с MIT в `protocol/mcp-2026-07-28/`,
коммит `271ecc9accafdd9b83a3c869fa67c22953b2af80`, контрольные хеши — provenance.json.

## Разделение версий

| Профиль | SDK / установка | Слой проекта | Объём |
|---|---|---|---|
| Исторический | `mcp==1.30.0`, requirements.lock, extra `mcp` | mcp_integration.py | прежний 2025-11-25, initialize, in-memory/stdio proxy |
| Новый | `mcp==2.3.0`, requirements-mcp2026.lock, extra `mcp2026` | examples/mcp2026_server.py | stateless tools/list, tools/call, meta, схемы, in-memory wire и stdio |

Extras `mcp` и `mcp2026` устанавливаются в **разные** окружения. Два SDK не
подменяются одним пакетом в исторических опытах. Новая прослойка использует
официальные обработчики SDK 2.x и те же RecoveryInput/Hybrid/валидатор ядра;
собственный альтернативный JSON-RPC/handshake не изобретён.

## Изменения и фактическая проверка

| Требование | Что проверено | Граница |
|---|---|---|
| Отсутствие обязательного handshake | Записаны настоящие JSON-RPC сообщения через memory transport; tools/list/call выполняются без initialize/initialized | Client закреплён на 2026-07-28 |
| `_meta` каждого запроса | protocolVersion, clientCapabilities; clientInfo присутствует у SDK-клиента; запросы проверены официальной JSON Schema | clientInfo рекомендован, а не сделан нами обязательным |
| Недостаточные meta / неизвестная версия | Сырые сообщения без meta и без clientCapabilities, версия 2099-01-01 отклонены | Не выводится успех из позитивного happy path |
| tools/list | Имя, полные inputSchema/outputSchema, стабильный единственный tool | Пагинация/большой каталог не исследованы |
| tools/call | Структурная проверка, structured output, независимый verifier и proxy | Null structured output явно вне профиля |
| Ошибки | Неизвестный tool → protocol invalid-params; исключение инструмента/невалидный результат → isError без приватного текста | HTTP-коды/авторизация не проверялись |
| structuredContent | Объект и массив в новой редакции; массив не приписывается старому профилю | Полный набор JSON-типов и output-adapter не заявлены |
| Версии и старые клиенты | SDK 2.3.0 в legacy mode; настоящий SDK 1.30.0 → новый stdio server; SDK 2.3.0 auto → настоящий старый server | Старые клиенты используют прежний протокол через поддержку двух редакций в SDK |
| Header-based routing, version header | Изучены TS source и документация | **NOT RUN:** Streamable HTTP, Mcp-Method/Mcp-Name, mismatch headers |
| MRTR, extensions, subscriptions, auth | Не входят в минимальный tools-профиль | **NOT RUN**; полная совместимость не заявляется |

Официальная редакция позволяет произвольный JSON в structuredContent; прежняя
редакция ограничивала его объектом. При указанной outputSchema проверяется
соответствие результата этой схеме. Успешная проверка нового провайдера
не означает проверку нового транспортного протокола: эти тесты независимы.

## Четыре разных уровня схемы

1. **Валидация схемы:** Draft 2020-12, включая combinators, not, if/then/else,
   локальные refs/defs/anchors. Сетевое получение внешних refs отключено.
2. **Сравнение изменения:** консервативный SchemaDiffEngine распознаёт свой
   ограниченный набор. Составные/неизвестные конструкции остаются opaque.
3. **Миграция:** opaque в полном Hybrid ведёт к ABSTAIN даже у валидного JSON.
4. **Проверка семантики:** требуется независимое поведение/состояние;
   валидатор не устанавливает прикладную эквивалентность.

Один тест совмещает allOf/anyOf/oneOf/not, условные ветви и локальный anchor,
проверяет положительный/отрицательные вызовы через SDK и отдельно opaque diff.
Существующие тесты валидатора и Hybrid сохраняются. Универсальный перевод
произвольного JSON Schema не реализован и не требуется для этого профиля.

## Команды независимой проверки

```sh
python3.11 -m venv /tmp/mcp2026
/tmp/mcp2026/bin/python -m pip install --require-hashes -r requirements-mcp2026.lock
/tmp/mcp2026/bin/python -m pip install --no-deps -e .
MCP_COMPAT_LEGACY_PYTHON="$PWD/.venv/bin/python" /tmp/mcp2026/bin/python -m pytest -q tests/mcp2026
```

Указанный legacy interpreter должен иметь SDK 1.30.0 из requirements.lock.
Без него двусторонний cross-SDK тест отмечается NOT RUN, а не PASS. В основном
окружении 1.30.0 весь каталог tests/mcp2026 явно пропускается с этой причиной.
В CI добавлен отдельный job и ветки research/**; удалённый запуск до push
не считается состоявшимся.

Новый stdio endpoint для стандартного клиента:
`/tmp/mcp2026/bin/python examples/mcp2026_server.py`.
Это демонстрационный echo; произвольные внешние эффекты он не разрешает.
Перенос свидетельства допуска на реальное исполнение по-прежнему требует
контроля состояния/TOCTOU, как описано в METHOD_FORMALIZATION.md.
