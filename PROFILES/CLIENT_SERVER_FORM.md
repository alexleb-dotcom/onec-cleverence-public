# PROFILE — CLIENT_SERVER_FORM

## Detection

- `&НаКлиенте`
- `&НаСервере`
- `&НаСервереБезКонтекста`

## Triggered standards

- `std487`
- `std496`
- `std628`
- `std636`

## Mandatory checks

- server calls per real user action
- implicit server calls
- context vs no-context justification
- traffic volume
- Знач for call-server parameters where applicable
- long operation threshold
- mutation of form data after server call
- no duplicated server business logic in form
- distinguish direct form-data access from a nested path: `Форма.Объект.X` / `Объект.X` is not itself a DB or client-server call; for `X.Y`, prove the runtime type of `X` and review reference dereference/N+1 risk
- traverse/search a material `ДанныеФормыКоллекция` on the server and count explicit plus implicit server transitions per real user action

## Completion rule

Every check above must be classified with evidence or explicit non-applicability. Unknown material behavior is not PASS.

## Independent ITS discovery

Search std487 and related standards for the exact form mechanism. Known neighboring standards include std628 (DataFormCollection implicit traffic) and std636 (context/no-context transfer).

Review not only explicit server calls but platform methods/properties that may perform implicit calls and whether server-call parameters should use `Знач` to avoid unnecessary return transfer.

- inspect implicit platform server calls and DataFormCollection traffic; explicit directives are not the whole topology (std628).
- do not turn the number of dots into a performance rule: direct scalar form-data reads are normal; nested members are `REVIEW` until the first member's runtime type is proven (std496).
