# research/ — NOT validated, NOT for production ⚠️

Código de **investigación** que **no** debe importarse desde `bot/` ni `execution/` (hay un test que
lo impone: `tests/test_no_research_imports.py`).

## `smart_money.py`
- **Qué hace:** puntúa wallets por un **proxy** de flujo de USD (`sold - bought` sobre `legs`) y luego
  mide **walk-forward** si sus compras predicen retornos positivos futuros.
- **Advertencia:** el proxy **ignora posiciones abiertas** (una wallet que solo compró y nunca vendió
  no se penaliza), así que **no es PnL realizado** fiable.
- **Resultado medido (`docs/ARC_AI_SMART_MONEY.md`): SIN EDGE.** No se envía como señal.
- **Uso:** `python -m research.smart_money --dsn <dsn> --train-end 22700000 --test-end 23080000`
  (solo lectura).

## Regla
Nada en `bot/` o `execution/` puede importar `research.*`. Si algún día una investigación se **valida**
con edge medido, se mueve a producción **con** su backtest reproducible y su test.
