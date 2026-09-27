// ILLUSTRATIVE_PATTERN: NOT EVIDENCE. Lifecycle routines are placeholders.
Процедура ЗаполнитьРезультат(Результат, Источник)

    // BAD: custom value is assigned before a later writer that may overwrite it.
    Результат.ПроектноеПоле = ПолучитьПроектноеЗначение(Источник);
    ЗаполнитьСтандартныеПоля(Результат, Источник);

КонецПроцедуры
