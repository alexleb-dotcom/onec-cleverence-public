// ILLUSTRATIVE_PATTERN: NOT EVIDENCE. Identity fields must come from the domain.
Функция ПолучитьКлюч(Строка)

    // BAD: display/normalization data participates in sameness without domain proof.
    Возврат Строка.ИдентификаторСущности
        + "|" + Строка.ИдентификаторПартии
        + "|" + Строка.ЕдиницаОтображения;

КонецФункции
