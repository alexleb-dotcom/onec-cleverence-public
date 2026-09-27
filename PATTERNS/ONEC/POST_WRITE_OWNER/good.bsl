// ILLUSTRATIVE_PATTERN: NOT EVIDENCE. Actual writer order must be traced from source.
Процедура ЗаполнитьРезультат(Результат, Источник)

    ЗаполнитьСтандартныеПоля(Результат, Источник);

    // GOOD SHAPE: after proving lifecycle order, the authoritative owner writes last.
    Результат.ПроектноеПоле = ПолучитьПроектноеЗначение(Источник);

КонецПроцедуры
