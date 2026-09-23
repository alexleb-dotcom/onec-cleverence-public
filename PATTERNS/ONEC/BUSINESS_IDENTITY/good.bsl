// ILLUSTRATIVE_PATTERN: NOT EVIDENCE. The exact identity set must be evidenced.
Функция ПолучитьКлюч(Строка)

    // GOOD SHAPE: only fields proven intrinsic to business sameness form the key.
    Возврат Строка.ИдентификаторСущности + "|" + Строка.ИдентификаторПартии;

КонецФункции

Процедура ЗаполнитьПредставление(Результат, Строка)

    // Representation remains available but does not silently redefine identity.
    Результат.ЕдиницаОтображения = Строка.ЕдиницаОтображения;

КонецПроцедуры
