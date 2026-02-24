# app/utils/special_days_handler.py

from app.models import Docente
from app.utils.orario_utils import giorno_speciale_classe, piazza_blocco
from app.utils.ordinary_placement import registra_occupazione
import app.utils.occupazione as occ


print(">>> SPECIAL DAYS HANDLER CARICATO")

print(">>> LOADING special_days_handler.py FROM:", __file__)



def apply_special_days(
    griglia,
    giorni_settimana,
    classe,
    materie_info,
    materie_dict,
    occupazione_docenti,
    docente_ok
):
    """
    GIORNI SPECIALI:
    - piazza SOLO le ore indicate nel DB
    - NON riempie la giornata
    - rispetta i vincoli docente (docente_ok)
    - aggiorna occupazione locale + globale
    - marca la materia come "giorno speciale" per bloccare l’ordinario
    """

    for g in giorni_settimana:
        data_g = g["data"]
        giorno_it = g["giorno_it"]

        # Se c'è STAGE → skip
        row = griglia[data_g]

        # Se c’è STAGE in qualunque slot → skip
        if any(
            slot and isinstance(slot, dict) and slot.get("materia") == "STAGE"
            for slot in row
        ):
            continue

        # Recupera eventuale giorno speciale
        gs = giorno_speciale_classe(classe.id, data_g)
        

        if not gs:
            continue

        g["speciale"] = True

        # Identifica la materia
        mid = next((k for k, v in materie_dict.items() if v == gs.materia), None)
        if mid not in materie_info:
            continue

        info_m = materie_info[mid]

        docente_id = gs.docente_id
        docente = Docente.query.get(docente_id) if docente_id else None

        ore_giornaliere = len(griglia[data_g])
        ore_da_piazzare = min(gs.ore, info_m["debito_residuo"], ore_giornaliere)

        # Trova slot liberi
        slot_liberi = [i for i in range(ore_giornaliere) if griglia[data_g][i] is None]
        if len(slot_liberi) < ore_da_piazzare:
            continue

        ore_piazzate = 0

        for i in slot_liberi:
            if ore_piazzate >= ore_da_piazzare:
                break

            # 🔥 Controllo docente globale
            if docente_ok and not docente_ok(docente_id, data_g, giorno_it, i, 1):
                continue

            print(">>> SPECIALE PIAZZA:", docente_id, data_g, i, 1)

            # Piazza 1 ora
            piazza_blocco(
                griglia, data_g, i, 1,
                gs.materia,
                docente.nome_docente if docente else "",
                docente_id,
                occupazione_docenti
            )

            # 🔥 registra anche nella globale
            occ.OCCUPAZIONE_DOCENTI_GLOBALE.setdefault(docente_id, {})
            occ.OCCUPAZIONE_DOCENTI_GLOBALE[docente_id].setdefault(data_g, {})
            occ.OCCUPAZIONE_DOCENTI_GLOBALE[docente_id][data_g][i] = True


            # Marca come slot fisso
            griglia[data_g][i]["fisso"] = True
            griglia[data_g][i]["tipo"] = "SPECIALE"

            # Aggiorna contatori
            info_m["debito_residuo"] -= 1
            info_m["ore_assegnate"] += 1
            ore_piazzate += 1

        # 🔥 blocca l’ordinario su questo giorno
        info_m.setdefault("giorni_speciali", set()).add(data_g)
