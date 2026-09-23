// ILLUSTRATIVE_PATTERN: NOT EVIDENCE. The real runtime entrypoint must be source-proven.
Процедура ОбработатьКоманду(Источник) Экспорт

    // GOOD SHAPE: delivery contains an explicit caller path to the new helper.
    ОбработатьНовоеПравило(Источник);

КонецПроцедуры

Процедура ОбработатьНовоеПравило(Источник)

    Результат = РассчитатьНовоеЗначение(Источник);

КонецПроцедуры

Функция РассчитатьНовоеЗначение(Источник)
    Возврат Источник.Значение;
КонецФункции
