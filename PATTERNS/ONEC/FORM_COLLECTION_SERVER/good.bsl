// ILLUSTRATIVE_PATTERN: NOT EVIDENCE. Exact form context must be proven.
&НаКлиенте
Процедура ПересчитатьКоманда(Команда)

    ПересчитатьНаСервере();

КонецПроцедуры

&НаСервере
Процедура ПересчитатьНаСервере()

    Итог = 0;
    Для Каждого Строка Из Объект.Товары Цикл
        Итог = Итог + Строка.Количество;
    КонецЦикла;

    // GOOD SHAPE: one evidenced server boundary owns material collection traversal.
    Объект.Итог = Итог;

КонецПроцедуры
