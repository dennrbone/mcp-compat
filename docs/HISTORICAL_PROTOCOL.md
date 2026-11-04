# Исторический протокол MCP-EvoBench

Здесь сохранены научные определения классификации, метрик и контролей
исходного исследования. Это определения исторического дизайна, не новый
критерий доказанного допуска. Активные данные — evobench-1.2, 2160 случаев;
их digest и состав задаёт benchmark/manifest.json. Предыдущие freezes
сохранены для проверки происхождения. Фактически выполненные матрицы и
неподтверждённые гипотезы описаны в RESULTS.md и STUDY_PROTOCOL_1_4.md.

Исторический SandboxVerifier сравнивал результат либо состояние; отдельная
формализация нового совместного критерия — METHOD_FORMALIZATION.md.
Модельные контроли B0–B3/M1/A1–A4 и новые A–E/FULL/NO_FINAL относятся
к разным протоколам; одинаковые буквы не означают одинаковый метод.

## Классификация эволюции контрактов

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

## Категории решения

Каждый сценарий имеет ground-truth категорию:

### SAFE_AUTO

Существует однозначное детерминированное преобразование, которое можно выполнить автоматически.

### CONDITIONAL

Преобразование возможно только при наличии дополнительного явно заданного знания или успешной семантической проверки.

### MUST_ABSTAIN

Из старого вызова и разрешённого контекста нельзя однозначно получить безопасный новый вызов.

Основная безопасность метода проверяется тем, что `MUST_ABSTAIN` не должен превращаться в уверенный `EXECUTE`.

## Домены benchmark

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

## Формат сценария

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

## Семантический oracle

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

## Baseline-методы

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

## Основные метрики

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

## Ablation study

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

## Угрозы валидности

В статье обязательно обсудить:

1. Синтетический benchmark не отражает все production MCP tools.
2. Качество semantic mapping зависит от качества descriptions.
3. Две LLM не доказывают универсальность для всех моделей.
4. Semantic oracle в benchmark знает ground truth, чего нет в реальном production.
5. Некоторые изменения невозможно безопасно восстановить автоматически в принципе.
6. Результаты зависят от набора mutation families и доли composed scenarios.

Эти ограничения не скрывать, а явно включить в Discussion.
