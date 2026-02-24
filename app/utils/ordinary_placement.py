# app/utils/ordinary_placement.py

from math import ceil

from app.utils.orario_utils import slot_libero, piazza_blocco
from app.utils.utils_scheduler import compatta_giornata, crea_buco_in_giornata
import app.utils.occupazione as occ


# ------------------------------------------------------------
# 0) CHECK / INIT OCCUPAZIONE GLOBALE DOCENTE
# ------------------------------------------------------------
def docente_disponibile_global(docente_id, data, ora):
    """
    Ritorna True se il docente NON è occupato globalmente
    in quella data/ora (su altre classi).
    """
    if docente_id is None:
        return True

    occ_global = occ.OCCUPAZIONE_DOCENTI_GLOBALE

    if docente_id not in occ_global:
        return True

    if data not in occ_global[docente_id]:
        return True

    return ora not in occ_global[docente_id][data]


def inizializza_occupazione_globale_da_locale(occupazione_docenti):
    """
    Converte l'occupazione locale (che usa SET)
    in OCCUPAZIONE_DOCENTI_GLOBALE (che usa dict → {ora: True})
    """
    occ.OCCUPAZIONE_DOCENTI_GLOBALE.clear()

    for docente_id, giorni_dict in occupazione_docenti.items():
        for data, ore_set in giorni_dict.items():
            occ.OCCUPAZIONE_DOCENTI_GLOBALE.setdefault(docente_id, {})
            occ.OCCUPAZIONE_DOCENTI_GLOBALE[docente_id].setdefault(data, {})
            for ora in ore_set:
                occ.OCCUPAZIONE_DOCENTI_GLOBALE[docente_id][data][ora] = True


# ------------------------------------------------------------
# 1) CALCOLA FABBISOGNO SETTIMANALE
# ------------------------------------------------------------
def calcola_fabbisogno_settimanale(materie_info, settimane_classe):
    """
    Restituisce un dict:
    materia_id → ore_per_settimana
    """
    num_settimane = len(settimane_classe) or 1

    fabbisogno = {}
    for mid, info in materie_info.items():
        debito = info.get("debito_residuo", 0)
        if debito <= 0:
            continue

        ore_sett = ceil(debito / num_settimane)
        fabbisogno[mid] = ore_sett

    return fabbisogno


# ------------------------------------------------------------
# 2) DISTRIBUISCI FABBISOGNO NELLE SETTIMANE (con blocchi)
# ------------------------------------------------------------
def distribuisci_fabbisogno(griglie, settimane_classe, classe, materie_info, docente_ok):
    """
    Per ogni settimana:
    - prende il fabbisogno settimanale
    - prova a piazzare le ore nei buchi disponibili
    - rispetta blocchi minimi per materia (es. EDUCAZIONE MOTORIA = 2 ore)
    """

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

            # blocco orario per la materia
            blocco = info_m.get("blocco_orario", 1)
            if blocco == 1 and "EDUCAZIONE" in nome_materia and "MOTORIA" in nome_materia:
                blocco = 2

            for _ in range(ore_sett):
                if info_m["debito_residuo"] <= 0:
                    break

                piazzato = False

                # prova a piazzare in ogni giorno
                for g in giorni:
                    data = g["data"]
                    giorno_it = g["giorno_it"]

                    # salta i giorni speciali / STAGE / FESTA
                    if g.get("speciale") or g.get("is_special_day") or g.get("tipo") in ("STAGE", "FESTA"):
                        continue

                    for ora in range(ore_giornaliere - (blocco - 1)):

                        # tutti gli slot del blocco devono essere liberi
                        if any(griglia[data][h] is not None for h in range(ora, ora + blocco)):
                            continue

                        # vincoli di disponibilità docente (locale + globale) su tutto il blocco
                        if docente_id is not None:
                            ok_blocco = True
                            for h in range(ora, ora + blocco):
                                if not docente_ok(docente_id, data, giorno_it, h, 1):
                                    ok_blocco = False
                                    break
                                if not docente_disponibile_global(docente_id, data, h):
                                    ok_blocco = False
                                    break
                            if not ok_blocco:
                                continue

                        if not slot_libero(griglia, data, ora, blocco):
                            continue

                        if crea_buco_in_giornata(griglia, data, ora, blocco):
                            continue

                        # piazza blocco
                        piazza_blocco(
                            griglia, data, ora, blocco,
                            info_m["nome"],
                            docente_nome,
                            docente_id,
                            None  # occupazione locale non usata
                        )

                        # aggiorna globale per tutte le ore del blocco
                        if docente_id is not None:
                            occ.OCCUPAZIONE_DOCENTI_GLOBALE.setdefault(docente_id, {})
                            occ.OCCUPAZIONE_DOCENTI_GLOBALE[docente_id].setdefault(data, {})
                            for h in range(ora, ora + blocco):
                                occ.OCCUPAZIONE_DOCENTI_GLOBALE[docente_id][data][h] = True

                        info_m["debito_residuo"] -= blocco
                        info_m["ore_assegnate"] += blocco
                        piazzato = True
                        break

                    if piazzato:
                        break


# ------------------------------------------------------------
# 3) COMPATTAZIONE GLOBALE (LEGGERA)
# ------------------------------------------------------------
def compatta_settimane(griglie, settimane_classe):
    for key in sorted(settimane_classe.keys()):
        giorni = sorted(settimane_classe[key], key=lambda x: x["data"])
        griglia = griglie[key]

        for g in giorni:
            data = g["data"]
            compatta_giornata(griglia, data)


# ------------------------------------------------------------
# 4) UTILITY CONTEGGI SU GRIGLIA DI CLASSE
# ------------------------------------------------------------
def count_ore_docente_in_classe(docente_id, griglia, data, ore_giornaliere):
    """
    Conta quante ore un docente insegna in QUESTA classe in un certo giorno,
    guardando direttamente la griglia della classe (non la globale).
    """
    if docente_id is None:
        return 0

    return sum(
        1
        for h in range(ore_giornaliere)
        if isinstance(griglia[data][h], dict)
        and griglia[data][h].get("docente_id") == docente_id
    )


def crea_buco_docente(docente_id, data, ora):
    """
    Ritorna True se togliere la lezione a (data, ora) crea un buco
    nella giornata del docente (su TUTTE le classi).
    """
    occ_doc = occ.OCCUPAZIONE_DOCENTI_GLOBALE.get(docente_id, {})
    ore = occ_doc.get(data, {})

    if ora not in ore:
        return False  # non c'è nulla da togliere

    ore_list = sorted(ore.keys())
    ha_prima = any(h < ora for h in ore_list)
    ha_dopo = any(h > ora for h in ore_list)

    # se ha ore prima e dopo → togliere crea un buco
    if ha_prima and ha_dopo:
        return True

    return False


def count_ore_in_giornata(griglia, data, ore_giornaliere):
    """
    Conta quante ore sono presenti in una giornata per una classe.
    Serve per non svuotare i giorni (0 o 1 ora).
    """
    return sum(1 for h in range(ore_giornaliere) if griglia[data][h] is not None)


# ------------------------------------------------------------
# 5) BACKFILL: RIEMPI I BUCHI PRENDENDO ORE DAL FUTURO
# ------------------------------------------------------------
def backfill_buchi(griglie, settimane_classe, classe, materie_info, docente_ok):
    """
    Riempie buchi prendendo lezioni dalle settimane future.
    Ritorna True se ha effettuato almeno uno spostamento.
    """
    changed = False
    ore_giornaliere = classe.ore_massime_giornaliere or 6

    for key in sorted(settimane_classe.keys()):
        giorni = sorted(settimane_classe[key], key=lambda x: x["data"])
        griglia = griglie[key]

        for g in giorni:
            data = g["data"]
            giorno_it = g["giorno_it"]

            # ⛔ NON toccare i giorni speciali
            if g.get("speciale") or g.get("is_special_day") or g.get("tipo") in ("STAGE", "FESTA"):
                continue

            for ora in range(ore_giornaliere):

                # slot già pieno → salta
                if griglia[data][ora] is not None:
                    continue

                # cerca una lezione nelle settimane future
                for future_key in sorted(settimane_classe.keys()):
                    if future_key <= key:
                        continue

                    future_giorni = sorted(settimane_classe[future_key], key=lambda x: x["data"])
                    future_griglia = griglie[future_key]

                    trovato = False

                    for fg in future_giorni:
                        f_data = fg["data"]
                        f_giorno_it = fg["giorno_it"]

                        # NON svuotare giorni con 0 o 1 ora
                        if count_ore_in_giornata(future_griglia, f_data, ore_giornaliere) <= 1:
                            continue

                        for f_ora in range(ore_giornaliere):
                            slot = future_griglia[f_data][f_ora]
                            if slot is None:
                                continue

                            # NON spostare lezioni fisse, speciali, STAGE, FESTA, PROFESSIONALI, DOC EST
                            if slot.get("fisso"):
                                continue
                            if slot.get("tipo") in ("STAGE", "FESTA", "PROFESSIONALE"):
                                continue
                            if slot.get("origine") in ("speciale", "fisso"):
                                continue
                            if slot.get("docente") and "DOC EST" in slot.get("docente"):
                                continue

                            docente_id = slot.get("docente_id")

                            # 1) disponibilità locale DESTINAZIONE (wrapper)
                            if docente_id and not docente_ok(docente_id, data, giorno_it, ora, 1):
                                continue

                            # 2) disponibilità globale DESTINAZIONE
                            if docente_id and not docente_disponibile_global(docente_id, data, ora):
                                continue

                            # 3) NON creare buco nella classe destinazione
                            if crea_buco_in_giornata(griglia, data, ora, 1):
                                continue

                            # 4) NON creare buco nella classe origine
                            if crea_buco_in_giornata(future_griglia, f_data, f_ora, 1):
                                continue

                            # 5) NON creare buco nella giornata del docente
                            if docente_id and crea_buco_docente(docente_id, f_data, f_ora):
                                continue

                            # 6) massimo 3 ore dello stesso docente nella stessa classe (destinazione)
                            if docente_id and count_ore_docente_in_classe(
                                docente_id, griglia, data, ore_giornaliere
                            ) >= 3:
                                continue

                            # 7) almeno 4 ore nella classe origine
                            if docente_id and count_ore_docente_in_classe(
                                docente_id, future_griglia, f_data, ore_giornaliere
                            ) <= 4:
                                continue

                            # 8) controllo locale SORGENTE (wrapper, per coerenza)
                            if docente_id and not docente_ok(docente_id, f_data, f_giorno_it, f_ora, 1):
                                continue

                            # SPOSTAMENTO SICURO
                            griglia[data][ora] = slot
                            future_griglia[f_data][f_ora] = None

                            # aggiorna occupazione globale
                            if docente_id:
                                occ.OCCUPAZIONE_DOCENTI_GLOBALE.setdefault(docente_id, {})
                                occ.OCCUPAZIONE_DOCENTI_GLOBALE[docente_id].setdefault(data, {})
                                occ.OCCUPAZIONE_DOCENTI_GLOBALE[docente_id][data][ora] = True

                                if f_data in occ.OCCUPAZIONE_DOCENTI_GLOBALE[docente_id]:
                                    occ.OCCUPAZIONE_DOCENTI_GLOBALE[docente_id][f_data].pop(f_ora, None)

                            trovato = True
                            changed = True
                            break

                        if trovato:
                            break
                    if trovato:
                        break

    return changed


# ------------------------------------------------------------
# 6) RIEQUILIBRIO GIORNATE
# ------------------------------------------------------------
def riequilibra_giornate(griglie, settimane_classe, classe, materie_info, docente_ok):
    """
    Riequilibra le giornate portando ogni giorno NON speciale
    ad almeno 4 ore, senza violare alcun vincolo del motore.
    Ritorna True se ha effettuato almeno uno spostamento.
    """

    changed = False
    ore_minime = 4
    ore_giornaliere = classe.ore_massime_giornaliere or 6

    for key in sorted(settimane_classe.keys()):
        giorni = sorted(settimane_classe[key], key=lambda x: x["data"])
        griglia = griglie[key]

        # 1) Identifica giorni poveri e giorni ricchi
        giorni_poveri = []
        giorni_ricchi = []

        for g in giorni:
            data = g["data"]

            # NON toccare giorni speciali / STAGE / FESTA
            if g.get("speciale") or g.get("tipo") in ("STAGE", "FESTA"):
                continue

            ore_presenti = sum(
                1 for h in range(ore_giornaliere)
                if isinstance(griglia[data][h], dict)
            )

            if ore_presenti < ore_minime:
                giorni_poveri.append((data, ore_presenti))
            elif ore_presenti >= ore_minime + 2:
                giorni_ricchi.append((data, ore_presenti))

        # 2) Riequilibrio: sposta ore dai ricchi ai poveri
        for data_povero, ore_povero in giorni_poveri:
            if ore_povero >= ore_minime:
                continue

            for data_ricco, ore_ricco in giorni_ricchi:

                # NON scendere sotto 4 ore nel giorno ricco
                if ore_ricco <= ore_minime:
                    continue

                # NON toccare giorni speciali / STAGE / FESTA nel ricco
                if any(
                    isinstance(slot, dict) and slot.get("tipo") in ("STAGE", "FESTA", "SPECIALE")
                    for slot in griglia[data_ricco]
                ):
                    continue

                # NON toccare giorni con slot fissi nel ricco
                if any(
                    isinstance(slot, dict) and slot.get("fisso")
                    for slot in griglia[data_ricco]
                ):
                    continue

                for ora_r in range(ore_giornaliere):
                    slot = griglia[data_ricco][ora_r]

                    # Slot vuoto → skip
                    if not isinstance(slot, dict):
                        continue

                    docente_id = slot.get("docente_id")
                    materia = slot.get("materia")

                    # NON toccare fissi, speciali, STAGE, FESTA, DOC EST
                    if slot.get("fisso"):
                        continue
                    if slot.get("tipo") in ("STAGE", "FESTA", "SPECIALE"):
                        continue
                    if slot.get("docente") and "DOC EST" in slot.get("docente"):
                        continue

                    # NON spezzare blocchi
                    mid = next(
                        (m for m, info in materie_info.items() if info["nome"] == materia),
                        None
                    )
                    if mid:
                        blocco = materie_info[mid].get("blocco_orario", 1)
                        if blocco > 1:
                            continue

                    # NON creare buchi nel giorno ricco
                    if crea_buco_in_giornata(griglia, data_ricco, ora_r, 1):
                        continue

                    # Cerca slot libero nel giorno povero
                    for ora_p in range(ore_giornaliere):

                        # Slot non libero → skip
                        if griglia[data_povero][ora_p] is not None:
                            continue

                        # NON creare buchi nel giorno povero
                        if crea_buco_in_giornata(griglia, data_povero, ora_p, 1):
                            continue

                        giorno_it_p = next(
                            g["giorno_it"] for g in giorni if g["data"] == data_povero
                        )

                        # Disponibilità locale DESTINAZIONE (wrapper)
                        if docente_id and not docente_ok(docente_id, data_povero, giorno_it_p, ora_p, 1):
                            continue

                        # Disponibilità globale DESTINAZIONE
                        if docente_id and not docente_disponibile_global(docente_id, data_povero, ora_p):
                            continue

                        # NON superare 3 ore dello stesso docente nella stessa classe
                        if docente_id and count_ore_docente_in_classe(
                            docente_id, griglia, data_povero, ore_giornaliere
                        ) >= 3:
                            continue

                        # SPOSTAMENTO SICURO
                        griglia[data_povero][ora_p] = slot
                        griglia[data_ricco][ora_r] = None

                        # Aggiorna occupazione globale
                        if docente_id:
                            occ.OCCUPAZIONE_DOCENTI_GLOBALE.setdefault(docente_id, {})
                            occ.OCCUPAZIONE_DOCENTI_GLOBALE[docente_id].setdefault(data_povero, {})
                            occ.OCCUPAZIONE_DOCENTI_GLOBALE[docente_id][data_povero][ora_p] = True

                            if data_ricco in occ.OCCUPAZIONE_DOCENTI_GLOBALE[docente_id]:
                                occ.OCCUPAZIONE_DOCENTI_GLOBALE[docente_id][data_ricco].pop(ora_r, None)

                        ore_povero += 1
                        ore_ricco -= 1
                        changed = True
                        break

    return changed


# ------------------------------------------------------------
# 7) COMPATTAZIONE AGGRESSIVA (CHIUSURA BUCHI NELLA STESSA GIORNATA)
# ------------------------------------------------------------
def compattazione_aggressiva(griglie, settimane_classe, classe, materie_info, docente_ok):
    """
    Prova a chiudere i buchi all'interno della stessa giornata,
    spostando lezioni più in alto possibile, rispettando tutti i vincoli.
    Ritorna True se ha effettuato almeno uno spostamento.
    """
    changed = False
    ore_giornaliere = classe.ore_massime_giornaliere or 6

    for key in sorted(settimane_classe.keys()):
        giorni = sorted(settimane_classe[key], key=lambda x: x["data"])
        griglia = griglie[key]

        for g in giorni:
            data = g["data"]
            giorno_it = g["giorno_it"]

            # NON toccare giorni speciali / STAGE / FESTA
            if g.get("speciale") or g.get("tipo") in ("STAGE", "FESTA"):
                continue

            for ora in range(ore_giornaliere):
                # se slot pieno → niente
                if griglia[data][ora] is not None:
                    continue

                # cerco una lezione più in basso da risalire
                for f_ora in range(ora + 1, ore_giornaliere):
                    slot = griglia[data][f_ora]
                    if slot is None:
                        continue

                    # NON spostare fissi, speciali, STAGE, FESTA, PROFESSIONALI, DOC EST
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

                    # NON spezzare blocchi > 1
                    mid = next(
                        (m for m, info in materie_info.items() if info["nome"] == materia),
                        None
                    )
                    if mid:
                        blocco = materie_info[mid].get("blocco_orario", 1)
                        if blocco > 1:
                            continue

                    # disponibilità locale DESTINAZIONE
                    if docente_id and not docente_ok(docente_id, data, giorno_it, ora, 1):
                        continue

                    # disponibilità globale DESTINAZIONE
                    if docente_id and not docente_disponibile_global(docente_id, data, ora):
                        continue

                    # NON creare buco nella posizione di origine
                    if crea_buco_in_giornata(griglia, data, f_ora, 1):
                        continue

                    # NON superare 3 ore dello stesso docente nella stessa classe
                    if docente_id and count_ore_docente_in_classe(
                        docente_id, griglia, data, ore_giornaliere
                    ) >= 3:
                        continue

                    # SPOSTAMENTO SICURO NELLA STESSA GIORNATA
                    griglia[data][ora] = slot
                    griglia[data][f_ora] = None

                    # aggiorna occupazione globale
                    if docente_id:
                        occ.OCCUPAZIONE_DOCENTI_GLOBALE.setdefault(docente_id, {})
                        occ.OCCUPAZIONE_DOCENTI_GLOBALE[docente_id].setdefault(data, {})
                        occ.OCCUPAZIONE_DOCENTI_GLOBALE[docente_id][data][ora] = True
                        occ.OCCUPAZIONE_DOCENTI_GLOBALE[docente_id][data].pop(f_ora, None)

                    changed = True
                    break  # passa al prossimo buco

    return changed


# ------------------------------------------------------------
# 8) ORDINARIO GLOBALE COMPLETO (firma compatibile con l’orchestratore)
# ------------------------------------------------------------
from app.utils.occupazione import rebuild_global_occupation

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
    """
    Nuovo motore ordinario globale:
    - inizializza occupazione globale dai dati locali
    - distribuzione settimanale del fabbisogno
    - più passate di:
        * backfill buchi
        * riequilibrio giornate
        * compattazione aggressiva
    - ricostruzione globale dopo ogni passata
    - compattazione finale leggera
    """

    # 0) inizializza occupazione globale partendo dall'occupazione locale
    inizializza_occupazione_globale_da_locale(occupazione_docenti)

    # 1) distribuzione iniziale
    distribuisci_fabbisogno(griglie, settimane_classe, classe, materie_info, docente_ok)

    # 2) ciclo di ottimizzazione aggressivo
    for _ in range(5):  # 5 passate aggressive
        changed = False

        changed |= backfill_buchi(griglie, settimane_classe, classe, materie_info, docente_ok)
        changed |= riequilibra_giornate(griglie, settimane_classe, classe, materie_info, docente_ok)
        changed |= compattazione_aggressiva(griglie, settimane_classe, classe, materie_info, docente_ok)

        # 🔥 Ricostruzione globale dopo ogni passata
        rebuild_global_occupation(griglie, settimane_classe, classe.ore_massime_giornaliere)

        if not changed:
            break

    # 3) compattazione finale "soft"
    compatta_settimane(griglie, settimane_classe)


# ------------------------------------------------------------
# 9) COMPATIBILITÀ LEGACY
# ------------------------------------------------------------
def registra_occupazione(*args, **kwargs):
    """
    Funzione di compatibilità per vecchi import.
    La logica di occupazione è gestita direttamente nelle funzioni sopra.
    """
    pass
