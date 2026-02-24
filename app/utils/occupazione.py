# app/utils/occupazione.py

# ⚠️ Deve essere un dict normale, NON defaultdict
OCCUPAZIONE_DOCENTI_GLOBALE = {}


def docente_disponibile_global(docente_id, data, ora):
    """
    Ritorna True se il docente NON risulta occupato globalmente
    in quella data/ora (su altre classi).
    """
    if docente_id not in OCCUPAZIONE_DOCENTI_GLOBALE:
        return True

    if data not in OCCUPAZIONE_DOCENTI_GLOBALE[docente_id]:
        return True

    return ora not in OCCUPAZIONE_DOCENTI_GLOBALE[docente_id][data]


def rebuild_global_occupation(griglie, settimane_classe, ore_giornaliere):
    """
    Ricostruisce OCCUPAZIONE_DOCENTI_GLOBALE leggendo TUTTE le griglie
    di TUTTE le settimane della classe.

    Questa funzione è fondamentale:
    - garantisce coerenza totale dopo ogni passata dell’ottimizzatore
    - impedisce la corruzione dello stato globale
    - evita conflitti reali nel VALIDATORE A
    """
    OCCUPAZIONE_DOCENTI_GLOBALE.clear()

    for key, griglia in griglie.items():
        giorni = settimane_classe[key]

        for g in giorni:
            data = g["data"]

            for ora in range(ore_giornaliere):
                slot = griglia[data][ora]

                # slot vuoto → nessuna occupazione
                if not isinstance(slot, dict):
                    continue

                docente_id = slot.get("docente_id")
                if docente_id is None:
                    continue

                # registra occupazione globale
                OCCUPAZIONE_DOCENTI_GLOBALE.setdefault(docente_id, {})
                OCCUPAZIONE_DOCENTI_GLOBALE[docente_id].setdefault(data, {})
                OCCUPAZIONE_DOCENTI_GLOBALE[docente_id][data][ora] = True
