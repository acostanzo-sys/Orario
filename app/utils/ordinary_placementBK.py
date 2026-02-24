# app/utils/ordinary_placement.py

from app.utils.orario_utils import slot_libero, piazza_blocco
from app.utils.utils_scheduler import crea_buco_in_giornata, compatta_giornata
from app.models import Docente
import app.utils.occupazione as occ

print(">>> LOADING ordinary_placement.py FROM:", __file__)


# ------------------------------------------------------------
# 🔥 AGGIORNA SOLO L’OCCUPAZIONE GLOBALE (mai quella locale!)
# ------------------------------------------------------------
def registra_occupazione(docente_id, data, start, blocco):
    """Registra l’occupazione globale del docente, convertendo set → dict se necessario."""
    if docente_id is None:
        return

    occ.OCCUPAZIONE_DOCENTI_GLOBALE.setdefault(docente_id, {})

    # Se esiste già ed è un set → converti in dict
    if isinstance(occ.OCCUPAZIONE_DOCENTI_GLOBALE[docente_id].get(data), set):
        vecchio_set = occ.OCCUPAZIONE_DOCENTI_GLOBALE[docente_id][data]
        occ.OCCUPAZIONE_DOCENTI_GLOBALE[docente_id][data] = {ora: True for ora in vecchio_set}

    # Se non esiste → crea dict vuoto
    occ.OCCUPAZIONE_DOCENTI_GLOBALE[docente_id].setdefault(data, {})

    # Ora è sicuramente un dict → possiamo assegnare
    for ora in range(start, start + blocco):
        occ.OCCUPAZIONE_DOCENTI_GLOBALE[docente_id][data][ora] = True



# ------------------------------------------------------------
# ⭐ CONTROLLO QUALITÀ GIORNATA
# ------------------------------------------------------------
def giornata_ok_intelligente(lezioni, ore_min=4, ore_max=6):
    """
    Regole forti di qualità:
    - almeno ore_min ore
    - massimo ore_max ore
    - niente giornate da 1–2 ore
    - niente buchi centrali
    - niente blocchi assurdi (es. 6 ore stessa materia)
    """
    piene = [i for i, s in enumerate(lezioni) if s is not None]

    if not piene:
        return True  # giornata vuota: ok (verrà riempita altrove)

    tot = len(piene)

    if tot < ore_min:
        return False

    if tot == 2 or tot == 1:
        return False

    if tot > ore_max:
        return False

    prima, ultima = piene[0], piene[-1]
    for i in range(prima, ultima + 1):
        if lezioni[i] is None:
            return False

    # evita 5–6 ore tutte della stessa materia
    materie = [s.get("materia") for s in lezioni if s is not None]
    if materie:
        from collections import Counter
        c = Counter(materie)
        if max(c.values()) >= 5:
            return False

    return True



# ------------------------------------------------------------
# ⭐ APPLY ORDINARY — VERSIONE MIGLIORATA
# ------------------------------------------------------------
def apply_ordinary(
    griglie,
    settimane_classe,
    classe,
    materie_info,
    materie_dict,
    docenti_dict,
    occupazione_docenti,   # ← QUESTO DEVE RESTARE SET-BASED
    docente_ok
):
    """
    Piazzamento ordinario multi-settimana.
    """

    ore_giornaliere = classe.ore_massime_giornaliere or 6

    cambiato = True
    while cambiato:
        cambiato = False

        for key in sorted(settimane_classe.keys()):
            giorni_settimana = sorted(settimane_classe[key], key=lambda x: x["data"])
            griglia = griglie[key]

            for g in giorni_settimana:
                data_g = g["data"]
                giorno_it = g["giorno_it"]

                # Salta giorni speciali
                if any(
                    "giorni_speciali" in info_m and data_g in info_m["giorni_speciali"]
                    for info_m in materie_info.values()
                ):
                    continue

                # Salta STAGE o FESTA
                if any(s and s.get("materia") in ("STAGE", "FESTA") for s in griglia[data_g]):
                    continue

                for start in range(ore_giornaliere):

                    # Slot fisso → non toccare
                    if griglia[data_g][start] and griglia[data_g][start].get("fisso"):
                        continue

                    # Slot già occupato
                    if griglia[data_g][start] is not None:
                        continue

                    candidati = []

                    # --------------------------------------------------------
                    # CERCA MATERIE PIAZZABILI
                    # --------------------------------------------------------
                    for mid, info_m in materie_info.items():

                        if info_m["debito_residuo"] <= 0:
                            continue

                        docente_id_raw = info_m["docente_id"]

                        try:
                            docente_id = int(docente_id_raw) if docente_id_raw is not None else None
                        except Exception:
                            continue

                        docente_obj = Docente.query.get(docente_id) if docente_id else None
                        if docente_id and not docente_obj:
                            continue

                        blocco_min = info_m["ore_minime_consecutive"]
                        possibili_blocchi = [blocco_min] if blocco_min > 1 else [2, 1]

                        for blocco in possibili_blocchi:

                            if blocco > info_m["debito_residuo"]:
                                continue

                            if start + blocco > ore_giornaliere:
                                continue

                            if not slot_libero(griglia, data_g, start, blocco):
                                continue

                            if crea_buco_in_giornata(griglia, data_g, start, blocco):
                                continue

                            ore_giornata = sum(
                                1 for s in griglia[data_g]
                                if s and s.get("materia") == info_m["nome"]
                            )

                            if info_m["ore_minime_consecutive"] <= 1:
                                if ore_giornata + blocco > 2:
                                    continue
                            else:
                                if ore_giornata > 0:
                                    continue

                            print(">>> ORDINARIO CANDIDATO:",
                                  docente_id, data_g, start, blocco,
                                  "materia:", info_m["nome"])

                            candidati.append((mid, info_m, docente_id, docente_obj, blocco))
                            break

                    if not candidati:
                        continue

                    # --------------------------------------------------------
                    # SCELTA DEL CANDIDATO MIGLIORE
                    # --------------------------------------------------------
                    candidati.sort(key=lambda x: x[1]["debito_residuo"], reverse=True)
                    mid, info_m, docente_id, docente_obj, blocco = candidati[0]

                    # --------------------------------------------------------
                    # LOGICA A — SE IL DOCENTE È OCCUPATO
                    # --------------------------------------------------------
                    if not docente_ok(docente_id, data_g, giorno_it, start, blocco):

                        piazzato_in_future = False

                        for future_key in sorted(settimane_classe.keys()):
                            if future_key <= key:
                                continue

                            future_giorni = sorted(
                                settimane_classe[future_key],
                                key=lambda x: x["data"]
                            )
                            future_griglia = griglie[future_key]

                            for fg in future_giorni:
                                f_data = fg["data"]
                                f_giorno_it = fg["giorno_it"]

                                for f_start in range(ore_giornaliere):

                                    if f_start + blocco > ore_giornaliere:
                                        continue

                                    if future_griglia[f_data][f_start] is not None:
                                        continue

                                    if not docente_ok(docente_id, f_data, f_giorno_it, f_start, blocco):
                                        continue

                                    if not slot_libero(future_griglia, f_data, f_start, blocco):
                                        continue

                                    if crea_buco_in_giornata(future_griglia, f_data, f_start, blocco):
                                        continue

                                    print(">>> ORDINARIO FUTURO:",
                                          docente_id, f_data, f_start, blocco,
                                          "materia:", info_m["nome"])

                                    piazza_blocco(
                                        future_griglia, f_data, f_start, blocco,
                                        info_m["nome"],
                                        docente_obj.nome_docente if docente_obj else "",
                                        docente_id,
                                        occupazione_docenti
                                    )

                                    # 🔥 aggiorna SOLO il globale
                                    registra_occupazione(docente_id, f_data, f_start, blocco)

                                    info_m["debito_residuo"] -= blocco
                                    info_m["ore_assegnate"] += blocco

                                    # ⭐ CONTROLLO QUALITÀ GIORNATA FUTURA
                                    if not giornata_ok_intelligente(future_griglia[f_data]):
                                        # annulla piazzamento
                                        for i in range(f_start, f_start + blocco):
                                            future_griglia[f_data][i] = None
                                            if docente_id:
                                                occ.OCCUPAZIONE_DOCENTI_GLOBALE[docente_id][f_data].pop(i, None)

                                        info_m["debito_residuo"] += blocco
                                        info_m["ore_assegnate"] -= blocco
                                        piazzato_in_future = False
                                        continue

                                    piazzato_in_future = True
                                    break

                                if piazzato_in_future:
                                    break
                            if piazzato_in_future:
                                break

                        if piazzato_in_future:
                            continue

                    # --------------------------------------------------------
                    # PIAZZAMENTO NELLA SETTIMANA CORRENTE
                    # --------------------------------------------------------
                    print(">>> ORDINARIO PIAZZA:",
                          docente_id, data_g, start, blocco,
                          "materia:", info_m["nome"])

                    piazza_blocco(
                        griglia, data_g, start, blocco,
                        info_m["nome"],
                        docente_obj.nome_docente if docente_obj else "",
                        docente_id,
                        occupazione_docenti
                    )

                    # 🔥 aggiorna SOLO il globale
                    registra_occupazione(docente_id, data_g, start, blocco)

                    info_m["debito_residuo"] -= blocco
                    info_m["ore_assegnate"] += blocco

                    # ⭐ CONTROLLO QUALITÀ GIORNATA
                    if not giornata_ok_intelligente(griglia[data_g]):
                        # annulla piazzamento
                        for i in range(start, start + blocco):
                            griglia[data_g][i] = None
                            if docente_id:
                                occ.OCCUPAZIONE_DOCENTI_GLOBALE[docente_id][data_g].pop(i, None)

                        info_m["debito_residuo"] += blocco
                        info_m["ore_assegnate"] -= blocco
                        continue

                    # --------------------------------------------------------
                    # MINIMO 4 ORE AL GIORNO
                    # --------------------------------------------------------
                    ore_presenti = sum(1 for s in griglia[data_g] if s is not None)

                    while ore_presenti < 4 and info_m["debito_residuo"] > 0:

                        slot_extra = next(
                            (i for i, s in enumerate(griglia[data_g]) if s is None),
                            None
                        )
                        if slot_extra is None:
                            break

                        if not docente_ok(docente_id, data_g, giorno_it, slot_extra, 1):
                            break

                        if not slot_libero(griglia, data_g, slot_extra, 1):
                            break

                        print(">>> ORDINARIO EXTRA:",
                              docente_id, data_g, slot_extra, 1,
                              "materia:", info_m["nome"])

                        piazza_blocco(
                            griglia, data_g, slot_extra, 1,
                            info_m["nome"],
                            docente_obj.nome_docente if docente_obj else "",
                            docente_id,
                            occupazione_docenti
                        )

                        # 🔥 aggiorna SOLO il globale
                        registra_occupazione(docente_id, data_g, slot_extra, 1)

                        info_m["debito_residuo"] -= 1
                        info_m["ore_assegnate"] += 1
                        ore_presenti += 1

                        # ⭐ CONTROLLO QUALITÀ GIORNATA
                        if not giornata_ok_intelligente(griglia[data_g]):
                            # annulla piazzamento extra
                            griglia[data_g][slot_extra] = None
                            if docente_id:
                                occ.OCCUPAZIONE_DOCENTI_GLOBALE[docente_id][data_g].pop(slot_extra, None)

                            info_m["debito_residuo"] += 1
                            info_m["ore_assegnate"] -= 1
                            ore_presenti -= 1
                            break

                    # --------------------------------------------------------
                    # COMPATTAZIONE
                    # --------------------------------------------------------
                    if not any(s and s.get("fisso") for s in griglia[data_g]):
                        compatta_giornata(griglia, data_g)

                    cambiato = True
