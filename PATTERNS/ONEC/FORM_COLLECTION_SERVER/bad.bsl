// ILLUSTRATIVE_PATTERN: NOT EVIDENCE. Form attributes/directives are placeholders.
&НаКлиенте
Процедура ПересчитатьКоманда(Команда)

    // BAD: material traversal is performed on the client without proving transfer/runtime cost.
    Итог = 0;
    Для Каждого Строка Из Объект.Товары Цикл
        Итог = Итог + Строка.Количество;
    КонецЦикла;

    Объект.Итог = Итог;

КонецПроцедуры
