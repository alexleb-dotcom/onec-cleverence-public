// ILLUSTRATIVE_PATTERN: NOT EVIDENCE. Domain fields are placeholders.
Процедура ДобавитьФакт(ТаблицаФактов, Источник)

    Ключ = ПолучитьПроектныйКлюч(Источник);

    Если Не ЗначениеЗаполнено(Ключ) Тогда
        Возврат;
    КонецЕсли;

    // GOOD SHAPE: derive and validate before the first state mutation.
    НоваяСтрока = ТаблицаФактов.Добавить();
    НоваяСтрока.Ключ = Ключ;

КонецПроцедуры
