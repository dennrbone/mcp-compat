# RESEARCH_SPEC.md

## 1. Статус документа

**Версия:** 1.0  
**Целевая публикация:** журнал ВАК категории К3  
**Предполагаемая специальность:** 2.3.5 — математическое и программное обеспечение вычислительных систем, комплексов и компьютерных сетей  
**Рабочее название проекта:** MCP-Compat  
**Рабочее название benchmark:** MCP-EvoBench  

Документ фиксирует научную постановку исследования. Реализация не должна менять определения, классы сценариев, метрики и критерии безопасности без отдельного обновления версии Research Spec.

---

## 2. Рабочее название статьи

**Русский вариант**

> Метод безопасного автоматического восстановления совместимости LLM-агентов при эволюции контрактов инструментов Model Context Protocol

**Английский вариант**

> Safe Automatic Compatibility Recovery for LLM Agents under Model Context Protocol Tool Contract Evolution

---

## 3. Проблема исследования

LLM-агент может быть построен для работы с определённым контрактом MCP-инструмента. После изменения интерфейса инструмента ранее корректный вызов может:

1. перестать удовлетворять новой JSON Schema;
2. оставаться синтаксически допустимым, но менять смысл;
3. приводить к иному побочному эффекту;
4. требовать новых обязательных параметров;
5. требовать преобразования значений, которое нельзя безопасно вывести только из структуры схемы.

Существующие механизмы versioning/digest pinning способны обнаружить изменение или заблокировать несовместимый вызов, однако исследуемая задача состоит не только в обнаружении, а в **безопасном восстановлении совместимости**.

---

## 4. Объект и предмет исследования

### Объект исследования

Программные системы LLM-агентов, использующие внешние инструменты через Model Context Protocol.

### Предмет исследования

Методы автоматического обнаружения breaking changes контрактов MCP-инструментов, построения преобразования старого вызова в новый формат, проверки семантической эквивалентности и безопасного отказа от автоматической адаптации при недостатке информации.

---

## 5. Цель исследования

Разработать и экспериментально оценить метод автоматического восстановления совместимости LLM-агентов с изменившимися MCP-инструментами, который повышает долю успешно восстановленных задач при ограничении доли опасных семантически неверных адаптаций.

---

## 6. Задачи исследования

1. Формализовать понятие эволюции контракта MCP-инструмента и корректного преобразования вызова.
2. Разработать классификацию типовых изменений MCP Tool Contract.
3. Разработать гибридный алгоритм:
   - структурное сравнение контрактов;
   - формирование кандидатов на соответствие полей;
   - семантическое сопоставление при помощи LLM;
   - построение compatibility adapter;
   - проверка новой JSON Schema;
   - семантическая/динамическая верификация;
   - безопасный `ABSTAIN` при недостаточной уверенности.
4. Разработать воспроизводимый benchmark MCP-EvoBench.
5. Сравнить предложенный метод с baseline-подходами.
6. Исследовать переносимость метода минимум на двух LLM.
7. Выполнить ablation study компонентов метода.
8. Оценить статистическую значимость различий.

---

## 7. Исследовательские вопросы

**RQ1.** Насколько часто breaking changes MCP-инструмента могут быть автоматически восстановлены без изменения исходного LLM-агента?

**RQ2.** Позволяет ли гибридный метод структурного анализа, LLM-сопоставления и верификации получить более высокий Safe Recovery Rate, чем LLM-only и rule-based методы?

**RQ3.** Насколько семантическая верификация уменьшает долю silent semantic failures?

**RQ4.** Насколько результаты метода зависят от используемой LLM?

---

## 8. Гипотезы

### H1

Предлагаемый Verified Hybrid Recovery обеспечивает статистически значимо более высокий Correct Recovery Rate, чем отсутствие восстановления и rule-based baseline.

### H2

Предлагаемый метод обеспечивает статистически значимо меньший Unsafe Healing Rate, чем LLM-only recovery и retry-based recovery.

### H3

Преимущество метода сохраняется минимум для двух различных LLM-провайдеров/семейств моделей.

### H4

Удаление semantic verification из pipeline увеличивает Unsafe Healing Rate сильнее, чем увеличивает Correct Recovery Rate.

---

## 9. Формальная модель

Пусть контракт инструмента задаётся как

\[
T = (n, d, S_{in}, S_{out}, m)
\]

где:

- `n` — имя инструмента;
- `d` — текстовое описание;
- `S_in` — входная JSON Schema;
- `S_out` — выходная JSON Schema, если она задана;
- `m` — дополнительные метаданные/семантические сведения экспериментального стенда.

Пусть:

- `T_old` — старый контракт;
- `T_new` — новый контракт;
- `q_old` — вызов, валидный относительно `T_old`;
- `A` — алгоритм восстановления;
- `q_new = A(T_old, T_new, q_old)` — преобразованный вызов.

Для безопасного исполнения должны выполняться два независимых условия.

### 9.1. Синтаксическая корректность

\[
Valid(q_{new}, S_{in,new}) = 1
\]

### 9.2. Семантическая эквивалентность

Для чистых функций:

\[
Normalize(Result_{old}) = Normalize(Result_{new})
\]

Для side-effect инструментов:

\[
EquivalentState(\sigma_{old}', \sigma_{new}') = 1
\]

где `σ'` — состояние тестовой среды после выполнения операции.

**Ключевое положение:** прохождение JSON Schema validation не является доказательством семантической корректности.

---

## 10. Решение метода

Pipeline MCP-Compat:

```text
T_old + T_new + q_old
          |
          v
  Structural Diff
          |
          v
 Candidate Mapping
          |
          v
  Semantic Mapper
       (LLM)
          |
          v
 Adapter Generator
          |
          v
 Schema Validation
          |
          v
 Semantic Verification
          |
          v
       Risk Gate
       /       \
    EXECUTE   ABSTAIN
```

`ABSTAIN` является корректным результатом алгоритма, а не ошибкой системы.

---

## 11. Классификация эволюции контрактов

Benchmark v1.0 использует 8 основных семейств изменений.

### C1. Identifier evolution

Подтипы:
- rename tool;
- rename parameter.

Пример:

```text
quantity -> amount
```

Базовый класс риска: **CONDITIONAL**.

Автоматическое восстановление допускается при совпадении типов и достаточных структурно-семантических основаниях.

---

### C2. Optional parameter evolution

Подтипы:
- добавление optional parameter;
- удаление optional parameter.

Пример:

```text
discount?: number
```

Базовый класс риска: **SAFE / CONDITIONAL**.

Добавленный optional parameter может быть пропущен, если контракт явно допускает отсутствие значения.

---

### C3. Required parameter evolution

Подтипы:
- добавление required parameter;
- optional -> required.

Пример:

```text
warehouse_id: integer
```

Базовый класс риска: **CONDITIONAL / UNSAFE**.

Автоматическая адаптация допустима только при наличии детерминированного источника значения:
- explicit default;
- однозначная derivation rule;
- разрешённый lookup в симулированной среде.

Если значение приходится угадывать, обязателен `ABSTAIN`.

---

### C4. Parameter removal

Удаление ранее использовавшегося параметра.

Пример:

```text
notify_customer removed
```

Базовый класс риска: **CONDITIONAL / UNSAFE**.

Нужно проверить, не меняется ли семантика/side effect операции после удаления параметра.

---

### C5. Type / format evolution

Подтипы:
- integer -> string;
- number -> string with format;
- scalar -> array;
- nullable changes;
- format changes.

Базовый класс риска: **CONDITIONAL**.

Автоматическое преобразование допускается только для детерминированных и без потери информации преобразований.

---

### C6. Enum / domain evolution

Подтипы:
- rename enum value;
- add/remove enum value;
- merge enum values;
- split enum value.

Пример:

```text
"express" -> "priority"
```

Базовый класс риска: **CONDITIONAL / UNSAFE**.

---

### C7. Structural evolution

Подтипы:
- nesting / un-nesting;
- split one parameter into several;
- merge several parameters;
- array/object restructuring.

Пример:

```text
address: "..."
```

становится

```text
address: {
  city: "...",
  street: "..."
}
```

Базовый класс риска: **CONDITIONAL**.

---

### C8. Semantic / unit / side-effect evolution

Подтипы:
- RUB -> kopecks;
- seconds -> milliseconds;
- gross -> net;
- delete -> deactivate;
- changed side effect.

Пример:

```text
amount_rub -> amount_kopecks
```

Базовый класс риска: **UNSAFE по умолчанию**.

Автоматическая адаптация разрешается только при наличии явного преобразования, подтверждаемого oracle/metadata. Одной похожести имён недостаточно.

---

## 12. Категории решения

Каждый сценарий имеет ground-truth категорию:

### SAFE_AUTO

Существует однозначное детерминированное преобразование, которое можно выполнить автоматически.

### CONDITIONAL

Преобразование возможно только при наличии дополнительного явно заданного знания или успешной семантической проверки.

### MUST_ABSTAIN

Из старого вызова и разрешённого контекста нельзя однозначно получить безопасный новый вызов.

Основная безопасность метода проверяется тем, что `MUST_ABSTAIN` не должен превращаться в уверенный `EXECUTE`.

---

## 13. Benchmark MCP-EvoBench v1.0

### 13.1. Размер

Первая версия:

- **48 базовых tools**;
- **8 mutation families**;
- **5 базовых вариантов на семейство**.

Базовая часть:

\[
48 \times 8 \times 5 = 1920
\]

Дополнительно:

- около **240 composed scenarios** с двумя одновременными изменениями.

Итого целевой размер:

> **≈2160 сценариев**

Допускается небольшое изменение количества при генерации, но итоговая версия benchmark должна быть заморожена до основного эксперимента.

---

## 14. Домены benchmark

Все инструменты являются синтетическими и работают только с контролируемой тестовой средой.

Домены:

1. e-commerce;
2. inventory/logistics;
3. calendar/tasks;
4. document management;
5. messaging/notifications;
6. booking;
7. analytics/reporting;
8. simulated financial/accounting operations без реальных платежей.

Никаких реальных пользовательских данных, денег или внешних side effects.

---

## 15. Формат сценария

```text
scenario_id/
├── old_tool.json
├── new_tool.json
├── old_call.json
├── oracle.json
└── metadata.json
```

`metadata.json` содержит:

```json
{
  "mutation_family": "C8",
  "mutation_subtype": "unit_change",
  "ground_truth": "SAFE_AUTO",
  "recoverable": true
}
```

`oracle.json` задаёт ожидаемую трансформацию или ожидаемый `ABSTAIN`.

---

## 16. Семантический oracle

### Pure tools

Сравниваются нормализованные результаты старой и новой реализации.

### Side-effect tools

Обе реализации запускаются из эквивалентного начального состояния.

Сравнивается конечное каноническое состояние:

```text
initial_state
    |
 old implementation + old_call
    |
 state_old

initial_state
    |
 new implementation + adapted_call
    |
 state_new
```

Условие:

```text
canonical(state_old) == canonical(state_new)
```

Это позволяет автоматически обнаруживать технически валидные, но семантически ошибочные адаптации.

---

## 17. Baseline-методы

### B0 — No Recovery

Старый вызов передаётся новому инструменту без адаптации.

### B1 — Error + Retry

После ошибки LLM получает:
- ошибку;
- новую схему;
- исходный пользовательский intent.

LLM формирует новый вызов.

### B2 — LLM-only Migration

LLM получает:
- `T_old`;
- `T_new`;
- `q_old`.

Задача: напрямую вернуть новый вызов либо `ABSTAIN`.

### B3 — Rule-based Migration

Только детерминированные structural rules. LLM не используется.

### M1 — MCP-Compat Verified Hybrid

Предлагаемый метод:

```text
structural diff
+ deterministic rules
+ LLM semantic mapping
+ adapter generation
+ schema validation
+ semantic verification
+ risk gate
```

---

## 18. LLM-конфигурация эксперимента

В основной статье используются минимум две различные модели/семейства:

- российская API-модель (целевой кандидат: GigaChat);
- локальная/открытая модель (целевой кандидат: Qwen).

Конкретные версии фиксируются непосредственно перед экспериментом и записываются в experimental manifest.

Recovery engine не должен содержать код, специфичный для одной LLM. Используется интерфейс:

```python
class SemanticMapper:
    def propose_mapping(...):
        ...
```

---

## 19. Основные метрики

### 19.1. Correct Recovery Rate (CRR)

Доля recoverable-сценариев, для которых был выполнен семантически корректный новый вызов.

\[
CRR =
\frac{CorrectRecovered}
{RecoverableScenarios}
\]

### 19.2. Unsafe Healing Rate (UHR)

Главная safety-метрика.

\[
UHR =
\frac{UnsafeExecutedAdaptations}
{AllExecutedAdaptations}
\]

К unsafe относится случай, когда система разрешила исполнение, но oracle зафиксировал нарушение семантической эквивалентности.

### 19.3. False Block Rate (FBR)

\[
FBR =
\frac{RecoverableScenariosBlocked}
{RecoverableScenarios}
\]

### 19.4. Abstention Accuracy

Насколько корректно система использует `ABSTAIN` на сценариях `MUST_ABSTAIN`.

### 19.5. Schema Validity Rate

Доля сгенерированных вызовов, соответствующих новой JSON Schema.

### 19.6. Semantic Equivalence Rate

Доля исполненных адаптированных вызовов, прошедших semantic oracle.

### 19.7. Operational metrics

- latency;
- number of LLM calls;
- token usage;
- estimated API cost;
- number of validation stages.

---

## 20. Главный критерий качества

Метод не должен оптимизироваться только по максимальному recovery.

Основная постановка:

\[
\max CRR
\]

при ограничении

\[
UHR \leq \varepsilon
\]

Рабочее значение для анализа:

```text
ε = 1–2%
```

Точный порог не объявляется доказанным заранее и исследуется экспериментально.

---

## 21. Экспериментальный протокол

1. Заморозить MCP-EvoBench v1.0.
2. Заморозить версии моделей и prompts.
3. Выполнить каждый сценарий всеми baseline и предлагаемым методом.
4. Для основной deterministic-конфигурации использовать минимальную доступную temperature.
5. На отдельной стратифицированной подвыборке выполнить повторные запуски для оценки LLM variability.
6. Сохранять полный machine-readable trace:
   - input contracts;
   - model output;
   - mapping;
   - adapted call;
   - validation results;
   - oracle result;
   - latency;
   - token usage.
7. Не изменять benchmark после просмотра итоговых результатов без создания новой версии benchmark.

---

## 22. Статистический анализ

Для основных долей:

- 95% bootstrap confidence intervals.

Для парных бинарных исходов одного и того же scenario:

- McNemar test.

Для latency/token/cost при ненормальном распределении:

- Wilcoxon signed-rank test.

Также результаты представляются отдельно по каждому mutation family C1–C8.

---

## 23. Ablation study

Минимальный набор:

### A1 — without Semantic Verification

Убирается semantic/dynamic oracle до Risk Gate.

### A2 — without Structural Rules

Остаётся преимущественно LLM semantic mapping.

### A3 — without LLM

Используются structural diff + deterministic rules + validation.

### A4 — without Risk Gate

Все schema-valid adapters исполняются.

Особый интерес представляет сравнение A4 и full method по UHR.

---

## 24. Предполагаемая научная новизна

Корректная формулировка для будущей статьи:

> Предложен метод безопасного автоматического восстановления совместимости LLM-агентов при эволюции контрактов MCP-инструментов, отличающийся сочетанием структурного анализа изменений, семантического сопоставления параметров, автоматического построения compatibility adapter, многоуровневой верификации и механизма управляемого отказа при неоднозначности преобразования.

Дополнительный результат:

> Предложен воспроизводимый benchmark MCP-EvoBench для экспериментальной оценки методов восстановления совместимости при эволюции MCP Tool Contract, включающий синтаксические и семантические breaking changes и автоматизированный oracle для проверки сохранения результата и побочных эффектов.

Не заявлять:
- «впервые создан self-healing API»;
- «впервые генерируется API adapter»;
- «впервые применяется LLM для schema matching».

---

## 25. Практическая значимость

Метод может использоваться как compatibility middleware между MCP Client/LLM-agent и изменяющимся MCP Server:

```text
LLM Agent
    |
MCP Client
    |
MCP-Compat Proxy
    |
MCP Server vN
```

При breaking change слой:
- обнаруживает несовместимость;
- пытается построить безопасный adapter;
- выполняет верификацию;
- либо пропускает адаптированный вызов;
- либо блокирует его и требует обновления/вмешательства.

---

## 26. Угрозы валидности

В статье обязательно обсудить:

1. Синтетический benchmark не отражает все production MCP tools.
2. Качество semantic mapping зависит от качества descriptions.
3. Две LLM не доказывают универсальность для всех моделей.
4. Semantic oracle в benchmark знает ground truth, чего нет в реальном production.
5. Некоторые изменения невозможно безопасно восстановить автоматически в принципе.
6. Результаты зависят от набора mutation families и доли composed scenarios.

Эти ограничения не скрывать, а явно включить в Discussion.

---

## 27. Минимальный технический стек

- Python **3.11.4**
- JSON Schema **2020-12**
- pytest
- jsonschema
- официальный MCP Python SDK — подключается на позднем этапе
- GigaChat API — поздний этап
- локальная Qwen — поздний этап

На первых этапах реализации **MCP Server и LLM не требуются**.

---

## 28. План реализации

### Phase 0 — Research specification

Статус: **завершён этим документом**.

### Phase 1 — Domain model and schema infrastructure

- `ToolContract`
- `ToolCall`
- `EvolutionScenario`
- `MigrationDecision`
- JSON Schema validation
- canonical serialization

**С этого этапа подключается Codex.**

### Phase 2 — SchemaDiffEngine

Определение структурных изменений C1–C8.

### Phase 3 — Benchmark generator

Генерация MCP-EvoBench и semantic oracle.

### Phase 4 — Rule-based baseline

B0/B3.

### Phase 5 — LLM provider abstraction

Интерфейс semantic mapper без привязки к модели.

### Phase 6 — GigaChat + Qwen

B1/B2 + semantic mapper.

### Phase 7 — Verified Hybrid Recovery

Полный M1.

### Phase 8 — Real MCP integration

Тестовые MCP Server v1/v2 и MCP-Compat proxy.

### Phase 9 — Experiment runner

Полный воспроизводимый запуск benchmark.

### Phase 10 — Statistics and article

Таблицы, графики, тесты статистической значимости, статья.

---

## 29. Предлагаемая структура репозитория

```text
mcp-compat/
├── RESEARCH_SPEC.md
├── README.md
├── pyproject.toml
├── src/
│   └── mcp_compat/
│       ├── domain/
│       │   ├── contracts.py
│       │   ├── calls.py
│       │   └── scenarios.py
│       ├── schema/
│       │   ├── validator.py
│       │   └── canonical.py
│       ├── diff/
│       ├── recovery/
│       ├── verification/
│       ├── llm/
│       └── mcp/
├── benchmark/
│   ├── definitions/
│   ├── scenarios/
│   └── manifest.json
├── experiments/
├── tests/
└── docs/
```

---

## 30. Критерий готовности Phase 1

Phase 1 считается завершённым только если:

- проект устанавливается локально;
- все domain models типизированы;
- `ToolContract` поддерживает input/output JSON Schema;
- `ToolCall` валидируется относительно контракта;
- сценарий можно сохранить и загрузить без потерь;
- JSON Schema 2020-12 validation покрыта unit-tests;
- `pytest` проходит полностью;
- нет LLM, MCP transport и network-dependent тестов.

---

## 31. Точка подключения Codex

**Codex подключается сейчас.**

Первое задание Codex не должно пытаться реализовать весь проект. Оно реализует только Phase 1 и создаёт фундамент, на котором далее будет строиться научный эксперимент.

---

## 32. Научные ориентиры MCP

На момент фиксации Research Spec:

- MCP specification 2026-07-28 использует full JSON Schema 2020-12 для tool input/output schemas;
- проблема эволюции инструментов признана MCP-сообществом;
- SEP-1575 предлагал semantic versioning tools;
- SEP-1766 предлагает digest-based detection/pinning изменений;
- исследование MCP-Compat рассматривает следующий слой: **восстановление совместимости после обнаружения breaking change**.

Research Spec не зависит от принятия конкретного SEP: versioning/digest mechanisms рассматриваются как механизмы обнаружения, а не как решение задачи semantic compatibility recovery.
