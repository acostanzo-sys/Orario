# app/utils/ordinary_placement.py

from math import ceil

from app.utils.orario_utils import slot_libero, piazza_blocco
from app.utils.utils_scheduler import compatta_giornata, crea_buco_in_giornata
import app.utils.occupazione as occ


# ------------------------------------------------------------
# 0) CHECK / INIT OCCUPAZIONE GLOBALE DOCENTE
# ------------------------------------------------------------
def docente_disponibile_global(docente_id, data, ora):
    if docente_id is None:
        return True
    return occ.docente_libero(docente_id, data, ora)


def inizializza_occupazione_globale_da_locale(occupazione_docenti):
    occ.OCCUPAZIONE_DOCENTI_GLOBALE.clear()
    for docente_id, giorni_dict in occupazione_docenti.items():
        for data, ore_set in giorni_dict.items():
            for ora in ore_set:
                occ.occupa(docente_id, None, data, ora)


# ------------------------------------------------------------
# 1) CALCOLA FABBISOGNO SETTIMANALE
# ------------------------------------------------------------
def calcola_fabbisogno_settimanale(materie_info, settimane_classe):
    num_settimane = len(settimane_classe) or 1
    fabbisogno = {}
    for mid, info in materie_info.items():
        debito = info.get("debito_residuo", 0)
        if debito > 0:
            fabbisogno[mid] = ceil(debito / num_settimane)
    return fabbisogno


# ------------------------------------------------------------
# 2) DISTRIBUISCI FABBISOGNO
# ------------------------------------------------------------
def distribuisci_fabbisogno(griglie, settimane_classe, classe, materie_info, docente_ok):

    fabbisogno = calcola_fabbisogno_settimanale(materie_info, settimane_classe)
    ore_giornaliere = classe.ore_massime_giornaliere or 6

    for key in sorted(settimane_classe.keys()):
        giorni = sorted(settimane_classe[key], key=lambda x: x["data"])
        griglia = griglie[key]

        for mid, ore_sett in fabbisogno.items():
            info_m = materie_info[mid]
            docente_id = info_m.get("docente_id")
            docente_nome = info_m.get("docente_nome", "")
            nome_materia = info_m.get("nome", "").upper()

            blocco = info_m.get("blocco_orario", 1)
            if blocco == 1 and "EDUCAZIONE" in nome_materia and "MOTORIA" in nome_materia:
                blocco = 2

            for _ in range(ore_sett):
                if info_m["debito_residuo"] <= 0:
                    break

                piazzato = False

                for g in giorni:
                    data = g["data"]
                    giorno_it = g["giorno_it"]

                    if g.get("speciale") or g.get("is_special_day") or g.get("tipo") in ("STAGE", "FESTA"):
                        continue

                    for ora in range(ore_giornaliere - (blocco - 1)):

                        if any(griglia[data][h] is not None for h in range(ora, ora + blocco)):
                            continue

                        if docente_id is not None:
                            ok_blocco = True
                            for h in range(ora, ora + blocco):
                                if not docente_ok(docente_id, data, giorno_it, h, 1):
                                    ok_blocco = False
                                    break
                                if not docente_disponibile_global(docente_id, data, h):
                                    ok_blocco = False
                                    break
                                if occ.classe_occupata(classe.id, data, h):
                                    ok_blocco = False
                                    break
                            if not ok_blocco:
                                continue

                        if not slot_libero(griglia, data, ora, blocco):
                            continue

                        if crea_buco_in_giornata(griglia, data, ora, blocco):
                            continue

                        piazza_blocco(
                            griglia,
                            data,
                            ora,
                            blocco,
                            info_m["nome"],
                            docente_nome,
                            docente_id,
                            None,
                            classe_id=classe.id,
                            materia_id=mid,
                            tipo="ORDINARIO",
                            origine="ordinario"
                        )

                        if docente_id:
                            for h in range(ora, ora + blocco):
                                occ.occupa(docente_id, classe.id, data, h)

                        info_m["debito_residuo"] -= blocco
                        info_m["ore_assegnate"] += blocco
                        piazzato = True
                        break

                    if piazzato:
                        break


# ------------------------------------------------------------
# 3) COMPATTAZIONE LEGGERA
# ------------------------------------------------------------
def compatta_settimane(griglie, settimane_classe):
    for key in sorted(settimane_classe.keys()):
        giorni = sorted(settimane_classe[key], key=lambda x: x["data"])
        griglia = griglie[key]
        for g in giorni:
            compatta_giornata(griglia, g["data"])


# ------------------------------------------------------------
# 4) UTILITY
# ------------------------------------------------------------
def count_ore_docente_in_classe(docente_id, griglia, data, ore_giornaliere):
    if docente_id is None:
        return 0
    return sum(
        1 for h in range(ore_giornaliere)
        if isinstance(griglia[data][h], dict)
        and griglia[data][h].get("docente_id") == docente_id
    )


def crea_buco_docente(docente_id, data, ora):
    occ_doc = occ.OCCUPAZIONE_DOCENTI_GLOBALE.get(docente_id, {})
    ore = occ_doc.get(data, {})
    if ora not in ore:
        return False
    ore_list = sorted(ore.keys())
    return any(h < ora for h in ore_list) and any(h > ora for h in ore_list)


def count_ore_in_giornata(griglia, data, ore_giornaliere):
    return sum(1 for h in range(ore_giornaliere) if griglia[data][h] is not None)


# ------------------------------------------------------------
# 5) BACKFILL — PATCHATO (INVARIATO)
# ------------------------------------------------------------
def backfill_buchi(griglie, settimane_classe, classe, materie_info, docente_ok):

    changed = False
    ore_giornaliere = classe.ore_massime_giornaliere or 6

    for key in sorted(settimane_classe.keys()):
        giorni = sorted(settimane_classe[key], key=lambda x: x["data"])
        griglia = griglie[key]

        for g in giorni:
            data = g["data"]
            giorno_it = g["giorno_it"]

            if g.get("speciale") or g.get("is_special_day") or g.get("tipo") in ("STAGE", "FESTA"):
                continue

            for ora in range(ore_giornaliere):

                if griglia[data][ora] is not None:
                    continue

                if occ.classe_occupata(classe.id, data, ora):
                    continue

                for future_key in sorted(settimane_classe.keys()):
                    if future_key <= key:
                        continue

                    future_giorni = sorted(settimane_classe[future_key], key=lambda x: x["data"])
                    future_griglia = griglie[future_key]

                    trovato = False

                    for fg in future_giorni:
                        f_data = fg["data"]
                        f_giorno_it = fg["giorno_it"]

                        if count_ore_in_giornata(future_griglia, f_data, ore_giornaliere) <= 1:
                            continue

                        for f_ora in range(ore_giornaliere):

                            slot = future_griglia[f_data][f_ora]
                            if slot is None:
                                continue

                            if slot.get("fisso"):
                                continue
                            if slot.get("tipo") in ("STAGE", "FESTA", "PROFESSIONALE"):
                                continue
                            if slot.get("origine") in ("speciale", "fisso"):
                                continue
                            if slot.get("docente") and "DOC EST" in slot.get("docente"):
                                continue

                            docente_id = slot.get("docente_id")

                            if docente_id and not docente_ok(docente_id, data, giorno_it, ora, 1):
                                continue

                            if docente_id and not docente_disponibile_global(docente_id, data, ora):
                                continue

                            if occ.classe_occupata(classe.id, data, ora):
                                continue

                            if crea_buco_in_giornata(griglia, data, ora, 1):
                                continue

                            if crea_buco_in_giornata(future_griglia, f_data, f_ora, 1):
                                continue

                            if docente_id and crea_buco_docente(docente_id, f_data, f_ora):
                                continue

                            if docente_id and count_ore_docente_in_classe(
                                docente_id, griglia, data, ore_giornaliere
                            ) >= 3:
                                continue

                            if docente_id and count_ore_docente_in_classe(
                                docente_id, future_griglia, f_data, ore_giornaliere
                            ) <= 4:
                                continue

                            if docente_id and not docente_ok(docente_id, f_data, f_giorno_it, f_ora, 1):
                                continue

                            piazza_blocco(
                                griglia,
                                data,
                                ora,
                                1,
                                slot["materia"],
                                slot["docente"],
                                slot["docente_id"],
                                None,
                                classe_id=classe.id,
                                materia_id=slot.get("materia_id"),
                                tipo="ORDINARIO",
                                origine="backfill"
                            )

                            future_griglia[f_data][f_ora] = None
                            if docente_id:
                                occ.libera(docente_id, f_data, f_ora)

                            trovato = True
                            changed = True
                            break

                        if trovato:
                            break
                    if trovato:
                        break

    return changed

# ------------------------------------------------------------
# 6.5) NUOVA PASSATA: GARANTISCI 4 ORE CONSECUTIVE
# ------------------------------------------------------------
def garantisci_quattro_ore_consecutive(griglie, settimane_classe, classe, materie_info, docente_ok):

    changed = False
    ore_giornaliere = classe.ore_massime_giornaliere or 6

    for key in sorted(settimane_classe.keys()):
        giorni = sorted(settimane_classe[key], key=lambda x: x["data"])
        griglia = griglie[key]

        for g in giorni:
            data = g["data"]
            giorno_it = g["giorno_it"]

            if g.get("speciale") or g.get("tipo") in ("STAGE", "FESTA"):
                continue

            ore_presenti = [h for h in range(ore_giornaliere) if griglia[data][h] is not None]

            # Se già 4 consecutive → OK
            if len(ore_presenti) >= 4:
                consecutive = 1
                for i in range(1, len(ore_presenti)):
                    if ore_presenti[i] == ore_presenti[i-1] + 1:
                        consecutive += 1
                        if consecutive >= 4:
                            break
                    else:
                        consecutive = 1
                if consecutive >= 4:
                    continue

            # Compattazione interna
            target = 0
            for h in range(ore_giornaliere):
                if griglia[data][h] is not None:
                    slot = griglia[data][h]
                    docente_id = slot.get("docente_id")

                    if h == target:
                        target += 1
                        continue

                    if docente_id and not docente_ok(docente_id, data, giorno_it, target, 1):
                        continue
                    if docente_id and not docente_disponibile_global(docente_id, data, target):
                        continue
                    if occ.classe_occupata(classe.id, data, target):
                        continue

                    piazza_blocco(
                        griglia,
                        data,
                        target,
                        1,
                        slot["materia"],
                        slot["docente"],
                        docente_id,
                        None,
                        classe_id=classe.id,
                        materia_id=slot.get("materia_id"),
                        tipo="ORDINARIO",
                        origine="4consecutive"
                    )

                    griglia[data][h] = None
                    if docente_id:
                        occ.libera(docente_id, data, h)

                    changed = True
                    target += 1

    return changed


# ------------------------------------------------------------
# 7) COMPATTAZIONE AGGRESSIVA — PATCHATA
# ------------------------------------------------------------
def compattazione_aggressiva(griglie, settimane_classe, classe, materie_info, docente_ok):

    changed = False
    ore_giornaliere = classe.ore_massime_giornaliere or 6

    for key in sorted(settimane_classe.keys()):
        giorni = sorted(settimane_classe[key], key=lambda x: x["data"])
        griglia = griglie[key]

        for g in giorni:
            data = g["data"]
            giorno_it = g["giorno_it"]

            if g.get("speciale") or g.get("tipo") in ("STAGE", "FESTA"):
                continue

            for ora in range(ore_giornaliere):

                if griglia[data][ora] is not None:
                    continue

                if occ.classe_occupata(classe.id, data, ora):
                    continue

                for f_ora in range(ora + 1, ore_giornaliere):

                    slot = griglia[data][f_ora]
                    if slot is None:
                        continue

                    if slot.get("fisso"):
                        continue
                    if slot.get("tipo") in ("STAGE", "FESTA", "PROFESSIONALE", "SPECIALE"):
                        continue
                    if slot.get("origine") in ("speciale", "fisso"):
                        continue
                    if slot.get("docente") and "DOC EST" in slot.get("docente"):
                        continue

                    docente_id = slot.get("docente_id")
                    materia = slot.get("materia")

                    mid = next(
                        (m for m, info in materie_info.items() if info["nome"] == materia),
                        None
                    )
                    if mid:
                        blocco = materie_info[mid].get("blocco_orario", 1)
                        if blocco > 1:
                            continue

                    if docente_id and not docente_ok(docente_id, data, giorno_it, ora, 1):
                        continue

                    if docente_id and not docente_disponibile_global(docente_id, data, ora):
                        continue

                    if occ.classe_occupata(classe.id, data, ora):
                        continue

                    if crea_buco_in_giornata(griglia, data, f_ora, 1):
                        continue

                    if docente_id and count_ore_docente_in_classe(
                        docente_id, griglia, data, ore_giornaliere
                    ) >= 3:
                        continue

                    piazza_blocco(
                        griglia,
                        data,
                        ora,
                        1,
                        slot["materia"],
                        slot["docente"],
                        slot["docente_id"],
                        None,
                        classe_id=classe.id,
                        materia_id=slot.get("materia_id"),
                        tipo="ORDINARIO",
                        origine="compattazione"
                    )

                    griglia[data][f_ora] = None
                    if docente_id:
                        occ.libera(docente_id, data, f_ora)

                    changed = True
                    break

    return changed

# -----------------------
# 7.5 Riequilibra giornate
# -----------------------

def riequilibra_giornate(griglie, settimane_classe, classe, materie_info, docente_ok):

    changed = False
    ore_giornaliere = classe.ore_massime_giornaliere or 6

    for key in sorted(settimane_classe.keys()):
        giorni = sorted(settimane_classe[key], key=lambda x: x["data"])
        griglia = griglie[key]

        # Calcola carico giornaliero
        carichi = {
            g["data"]: sum(1 for h in range(ore_giornaliere) if griglia[g["data"]][h] is not None)
            for g in giorni
            if not g.get("speciale") and g.get("tipo") not in ("STAGE", "FESTA")
        }

        # Giorni troppo pieni e troppo vuoti
        giorni_pieni = [d for d, c in carichi.items() if c >= 5]
        giorni_vuoti = [d for d, c in carichi.items() if c <= 2]

        if not giorni_pieni or not giorni_vuoti:
            continue

        for data_piena in giorni_pieni:
            for data_vuota in giorni_vuoti:

                # Trova uno slot libero nel giorno vuoto
                for ora_dest in range(ore_giornaliere):
                    if griglia[data_vuota][ora_dest] is not None:
                        continue
                    if occ.classe_occupata(classe.id, data_vuota, ora_dest):
                        continue
                    if crea_buco_in_giornata(griglia, data_vuota, ora_dest, 1):
                        continue

                    # Trova uno slot spostabile nel giorno pieno
                    for ora_src in range(ore_giornaliere):
                        slot = griglia[data_piena][ora_src]
                        if slot is None:
                            continue

                        # Escludi slot non spostabili
                        if slot.get("fisso"):
                            continue
                        if slot.get("tipo") in ("STAGE", "FESTA", "PROFESSIONALE", "SPECIALE"):
                            continue
                        if slot.get("origine") in ("speciale", "fisso"):
                            continue
                        if slot.get("docente") and "DOC EST" in slot.get("docente"):
                            continue

                        docente_id = slot.get("docente_id")
                        materia = slot.get("materia")

                        # Blocchi > 1 non spostabili
                        mid = next((m for m, info in materie_info.items() if info["nome"] == materia), None)
                        if mid:
                            blocco = materie_info[mid].get("blocco_orario", 1)
                            if blocco > 1:
                                continue

                        # Vincoli docente
                        giorno_it_dest = next(g["giorno_it"] for g in giorni if g["data"] == data_vuota)
                        giorno_it_src = next(g["giorno_it"] for g in giorni if g["data"] == data_piena)

                        if docente_id:
                            if not docente_ok(docente_id, data_vuota, giorno_it_dest, ora_dest, 1):
                                continue
                            if not docente_disponibile_global(docente_id, data_vuota, ora_dest):
                                continue
                            if not docente_ok(docente_id, data_piena, giorno_it_src, ora_src, 1):
                                continue

                        # Evita buchi nel giorno pieno
                        if crea_buco_in_giornata(griglia, data_piena, ora_src, 1):
                            continue

                        # Tutto ok → sposta
                        piazza_blocco(
                            griglia,
                            data_vuota,
                            ora_dest,
                            1,
                            slot["materia"],
                            slot["docente"],
                            docente_id,
                            None,
                            classe_id=classe.id,
                            materia_id=slot.get("materia_id"),
                            tipo="ORDINARIO",
                            origine="riequilibrio"
                        )

                        # Libera slot originale
                        griglia[data_piena][ora_src] = None
                        if docente_id:
                            occ.libera(docente_id, data_piena, ora_src)
                            occ.occupa(docente_id, classe.id, data_vuota, ora_dest)

                        changed = True
                        break

                    if changed:
                        break
                if changed:
                    break
            if changed:
                break

    return changed



# ------------------------------------------------------------
# 8) ORDINARIO GLOBALE COMPLETO
# ------------------------------------------------------------
from app.utils.fixed_days_handler import apply_fixed_days

def apply_ordinary(
    griglie,
    settimane_classe,
    classe,
    materie_info,
    materie_dict,
    docenti_dict,
    occupazione_docenti,
    docente_ok
):

    # 0) Inizializza OCCUPAZIONE_CLASSI_GLOBALE
    for key in sorted(settimane_classe.keys()):
        giorni = sorted(settimane_classe[key], key=lambda x: x["data"])
        for g in giorni:
            data = g["data"]
            occ.OCCUPAZIONE_CLASSI_GLOBALE.setdefault(classe.id, {})
            occ.OCCUPAZIONE_CLASSI_GLOBALE[classe.id].setdefault(data, set())

    # 0.5) Inizializza OCCUPAZIONE_DOCENTI_GLOBALE 
    inizializza_occupazione_globale_da_locale(occupazione_docenti)

    # 1) Giorni fissi
    giorni_fissi_classe = getattr(classe, "giorni_fissi", None)

    giorni_settimana = [
        g
        for settimana in settimane_classe.values()
        for g in settimana
    ]

    apply_fixed_days(
        griglia=griglie,
        giorni_settimana=giorni_settimana,
        classe=classe,
        materie_info=materie_info,
        materie_dict=materie_dict,
        occupazione_docenti=occupazione_docenti,
        giorni_fissi_classe=giorni_fissi_classe,
        docente_ok=docente_ok
    )


    # 2) Distribuzione iniziale
    distribuisci_fabbisogno(
        griglie,
        settimane_classe,
        classe,
        materie_info,
        docente_ok
    )

    # 3) Ciclo di ottimizzazione
    for _ in range(5):
        changed = False

        changed |= backfill_buchi(
            griglie,
            settimane_classe,
            classe,
            materie_info,
            docente_ok
        )

        changed |= riequilibra_giornate(
            griglie,
            settimane_classe,
            classe,
            materie_info,
            docente_ok
        )

        changed |= garantisci_quattro_ore_consecutive(
            griglie,
            settimane_classe,
            classe,
            materie_info,
            docente_ok
        )

        changed |= compattazione_aggressiva(
            griglie,
            settimane_classe,
            classe,
            materie_info,
            docente_ok
        )

        if not changed:
            break

    # 4) Compattazione finale
    compatta_settimane(griglie, settimane_classe)

    # 5) Recupero ore non piazzate
    
    recupera_debito_residuo(
        griglie,
        settimane_classe,
        classe,
        materie_info,
        docente_ok
    )

    
    
    def recupera_debito_residuo(griglie, settimane_classe, classe, materie_info, docente_ok):

        changed = False
        ore_giornaliere = classe.ore_massime_giornaliere or 6

        for mid, info_m in materie_info.items():
            debito = info_m.get("debito_residuo", 0)
            if debito <= 0:
                continue

            docente_id = info_m.get("docente_id")
            docente_nome = info_m.get("docente_nome", "")
            blocco = info_m.get("blocco_orario", 1)

            for key in sorted(settimane_classe.keys()):
                giorni = sorted(settimane_classe[key], key=lambda x: x["data"])
                griglia = griglie[key]

                for g in giorni:
                    data = g["data"]
                    giorno_it = g["giorno_it"]

                    if g.get("speciale") or g.get("tipo") in ("STAGE", "FESTA"):
                        continue

                    for ora in range(ore_giornaliere - (blocco - 1)):

                        if debito <= 0:
                            break

                        if any(griglia[data][h] is not None for h in range(ora, ora + blocco)):
                            continue

                        if docente_id:
                            ok = True
                            for h in range(ora, ora + blocco):
                                if not docente_ok(docente_id, data, giorno_it, h, 1):
                                    ok = False
                                    break
                                if not docente_disponibile_global(docente_id, data, h):
                                    ok = False
                                    break
                                if occ.classe_occupata(classe.id, data, h):
                                    ok = False
                                    break
                            if not ok:
                                continue

                        if crea_buco_in_giornata(griglia, data, ora, blocco):
                            continue

                        piazza_blocco(
                            griglia,
                            data,
                            ora,
                            blocco,
                            info_m["nome"],
                            docente_nome,
                            docente_id,
                            None,
                            classe_id=classe.id,
                            materia_id=mid,
                            tipo="RECUPERO",
                            origine="recupero"
                        )

                        if docente_id:
                            for h in range(ora, ora + blocco):
                                occ.occupa(docente_id, classe.id, data, h)

                        info_m["debito_residuo"] -= blocco
                        info_m["ore_assegnate"] += blocco
                        debito -= blocco
                        changed = True

        return changed



# ------------------------------------------------------------
# 9) COMPATIBILITÀ LEGACY
# ------------------------------------------------------------
def registra_occupazione(*args, **kwargs):
    """
    Funzione di compatibilità per vecchi import.
    La logica di occupazione è gestita direttamente nelle funzioni sopra.
    """
    pass
