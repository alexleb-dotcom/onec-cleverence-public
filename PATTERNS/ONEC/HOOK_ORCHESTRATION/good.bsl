// ILLUSTRATIVE_PATTERN: NOT EVIDENCE. Names/signatures are placeholders.
&После("ОбработкаПроведения")
Процедура Пример_ОбработкаПроведенияПосле(Отказ, РежимПроведения)

    Если Отказ Тогда
        Возврат;
    КонецЕсли;

    // GOOD SHAPE: the hook adapts runtime context and delegates reusable behavior.
    ПримерБизнесЛогики.ПослеПроведения(Объект.Ссылка, РежимПроведения);

КонецПроцедуры
