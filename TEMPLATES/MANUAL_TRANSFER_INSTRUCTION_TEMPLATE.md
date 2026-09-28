# Инструкция по ручному переносу изменений

Использовать только когда выбран результат `MANUAL_TRANSFER_INSTRUCTION`.

По умолчанию для русскоязычного проекта/пользователя документ ведётся в UTF-8 на русском языке. Идентификаторы объектов, процедур, кода, путей, хэшей, API и машинных токенов сохраняются буквально.

Не использовать псевдоверсии в имени файла (`v2`, `final`, `fix`, `new` и подобные).

Проект: <exact bound project>
Задача: <exact bound task>
Целевая база / артефакт: <exact baseline or candidate identity>

## Предусловия
...

## Порядок изменений

### STEP-001 — <CREATE | MODIFY | DELETE>
- Объект / артефакт: <exact target>
- Место / якорь: <exact insertion / replacement / region / handler anchor>
- Код / payload: <exact content or payload reference>
- Зависит от: <stable step ids or none>
- Wiring: <form / command / role / subsystem / scheduled job / event subscription / integration wiring when applicable>

### STEP-002 — <CREATE | MODIFY | DELETE>
...

## Миграция / инициализация / одноразовые действия
<если применимо>

## Статическая проверка после переноса
...

## Runtime-проверка
...

## Нерешённые выборы для исполнителя
none

Если остаётся материальный выбор реализации, вместо `none` указать `BLOCKING: <exact unresolved choice>`; такая инструкция не может считаться готовой к переносу.

## Граница доказанности
- Полнота инструкции проверена: <yes | no | pending>
- Применённые target bytes/state наблюдались: <yes | no>
- Deployment/import наблюдался: <yes | no>
- Runtime-поведение наблюдалось: <yes | no | partial>
- Сильнейшее обоснованное утверждение: <...>

### Инварианты

- Порядок CREATE/MODIFY/DELETE и stable STEP ids обязателен.
- Каждый материальный шаг должен иметь точный target и точный anchor/payload.
- Все зависимости и требуемый порядок должны быть явными.
- Нельзя молча делегировать человеку материальный выбор реализации.
- Готовая инструкция не доказывает, что изменения применены, развернуты или проверены в runtime.
- Этот документ не заменяет `ChangePackage` и не создаёт новый proof owner.
