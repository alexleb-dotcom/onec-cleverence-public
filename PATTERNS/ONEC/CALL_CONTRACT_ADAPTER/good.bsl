// ILLUSTRATIVE_PATTERN: NOT EVIDENCE. Exact exported declarations must be read first.
Процедура ВыполнитьОперацию(Источник)

    Параметры = Новый Структура;
    Параметры.Вставить("ПроверятьОграничения", Истина);
    Параметры.Вставить("РежимВыполнения", 0);

    // GOOD SHAPE: a project adapter names semantic intent; its own callee contract is still source-proven.
    ПримерАдаптерКонтракта.ВыполнитьПоКонтракту(Источник, Параметры);

КонецПроцедуры
