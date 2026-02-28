# app/utils/fixed_days_handler.py

from app.utils.orario_utils import slot_libero, piazza_blocco, normalizza_giorno_it
from app.models import Docente

print(">>> FIXED DAYS HANDLER CARICATO")
print(">>> LOADING fixed_days_handler.py FROM:", __file__)


def apply_fixed_days(
    griglia,
    giorni_settimana,
    classe,
    materie_info,
    materie_dict,
    occupazione_docenti,
    giorni_fissi_classe,
    docente_ok
):
    """
    GIORNI FISSI (hard lock):
    - piazza SOLO le ore richieste
    - inserisce SEMPRE il docente associato
    - rispetta vincoli docente (docente_ok)
    - aggiorna occupazione globale tramite piazza_blocco
    - marca gli slot come fissi
    - NON invade giorni speciali
    - NON invade STAGE
    """

    if not giorni_fissi_classe:
        return

    for gf in giorni_fissi_classe:
        materia_id = gf.materia_id
        docente_id = gf.docente_id
        giorno_nome = gf.giorno
        ore_richieste = gf.ore

        if materia_id not in materie_info:
            continue

        info_m = materie_info[materia_id]

        docente = Docente.query.get(docente_id)
        if not docente:
            print(f"[ATTENZIONE] Giorno fisso senza docente valido: materia {materia_id}")
            continue

        for g in giorni_settimana:
            if normalizza_giorno_it(g["giorno_it"]) != normalizza_giorno_it(giorno_nome):
                continue

            data_g = g["data"]
            giorno_it = g["giorno_it"]

            # NON invadere giorni speciali
            if "giorni_speciali" in info_m and data_g in info_m["giorni_speciali"]:
                continue

            row = griglia[data_g]   # 🔥 SEMPRE LISTA

            # NON invadere STAGE
            if any(
                slot and isinstance(slot, dict) and slot.get("materia") == "STAGE"
                for slot in row
            ):
                continue

            ore_giornaliere = len(row)
            ore_da_piazzare = min(ore_richieste, info_m["debito_residuo"], ore_giornaliere)

            # Trova slot liberi
            slot_liberi = [i for i in range(ore_giornaliere) if row[i] is None]
            if len(slot_liberi) < ore_da_piazzare:
                continue

            ore_piazzate = 0

            for i in slot_liberi:
                if ore_piazzate >= ore_da_piazzare:
                    break

                # Disponibilità docente
                if docente_ok and not docente_ok(docente_id, data_g, giorno_it, i, 1):
                    continue

                print(">>> FISSO PIAZZA:", docente_id, data_g, i, 1)

                # Piazza 1 ora (aggiorna globale)
                piazza_blocco(
                    griglia,
                    data_g,
                    i,
                    1,
                    materie_dict[materia_id],
                    docente.nome_docente if docente else "",
                    docente_id,
                    occupazione_docenti,
                    classe_id=classe.id,
                    materia_id=materia_id,
                    tipo="FISSO",
                    origine="fisso"
                )

                # Marca come slot fisso
                griglia[data_g][i]["fisso"] = True

                # Aggiorna contatori
                info_m["debito_residuo"] -= 1
                info_m["ore_assegnate"] += 1
                ore_piazzate += 1
