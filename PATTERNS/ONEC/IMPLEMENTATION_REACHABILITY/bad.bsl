// ILLUSTRATIVE_PATTERN: NOT EVIDENCE. Entrypoints are project-specific.
Процедура ОбработатьНовоеПравило(Источник)

    // BAD: the helper can be locally correct and still be unreachable functionality.
    Результат = РассчитатьНовоеЗначение(Источник);

КонецПроцедуры

Функция РассчитатьНовоеЗначение(Источник)
    Возврат Источник.Значение;
КонецФункции
