// ILLUSTRATIVE_PATTERN: NOT EVIDENCE. Domain fields are placeholders.
Процедура ДобавитьФакт(ТаблицаФактов, Источник)

    // BAD: mutation happens before the key is proven usable.
    НоваяСтрока = ТаблицаФактов.Добавить();
    Ключ = ПолучитьПроектныйКлюч(Источник);

    Если Не ЗначениеЗаполнено(Ключ) Тогда
        Возврат;
    КонецЕсли;

    НоваяСтрока.Ключ = Ключ;

КонецПроцедуры
