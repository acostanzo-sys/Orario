# app/utils/validator.py

from collections import defaultdict
from app.models import Docente
from app.utils.validator_html import render_html_report
from app.utils.utils_scheduler import crea_buco_in_giornata



# Memoria temporanea per la diagnostica (evita JSON serialization error)
CLASSI_INFO_CACHE = None
CALENDARIO_CACHE = None


# ============================================================
# VALIDATORE A — GRIGLIA REALE DEL MOTORE
# ============================================================

def valida_griglia_reale(classi_info):
    """
    Controlla sovrapposizioni REALI:
    - legge le griglie interne generate dal motore
    - verifica se un docente è in due classi nello stesso giorno/ora
    """

    conflitti = []
    mappa = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))

    for cid, info in classi_info.items():
        classe = info["classe"]
        griglie = info.get("griglie")

        if not griglie:
            continue

        for key, griglia in griglie.items():
            for data, ore in griglia.items():
                for ora, slot in enumerate(ore):
                    if isinstance(slot, dict) and slot.get("docente_id"):
                        did = slot["docente_id"]
                        docente = Docente.query.get(did)

                        if docente and docente.nome_docente != "DOC EST":
                            mappa[did][data][ora].append(classe.nome_classe)

    # Cerca conflitti reali
    for did, per_data in mappa.items():
        docente = Docente.query.get(did)
        for data, per_ora in per_data.items():
            for ora, classi in per_ora.items():
                if len(classi) > 1:
                    conflitti.append({
                        "docente": docente.nome_docente,
                        "data": data,
                        "ora": ora,
                        "classi": classi
                    })

    return conflitti


# ============================================================
# VALIDATORE B — CALENDARIO FINALE (JSON)
# ============================================================

def valida_calendario_finale(calendario_per_classe):
    """
    Controlla sovrapposizioni nel calendario finale:
    - può contenere falsi positivi
    - serve per diagnosticare errori di conversione
    """

    conflitti = []
    mappa = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))

    for cid, info in calendario_per_classe.items():

        # Nome classe robusto
        classe_nome = (
            info.get("classe")
            or info.get("nome_classe")
            or info.get("classe_nome")
            or f"classe_{cid}"
        )

        calendario = info["calendario"]

        for giorno in calendario:
            data = giorno["data"]
            for ora, slot in enumerate(giorno["lezioni"]):
                if slot and slot.get("docente_id"):
                    did = slot["docente_id"]
                    docente = Docente.query.get(did)

                    if docente and docente.nome_docente != "DOC EST":
                        mappa[did][data][ora].append(classe_nome)

    # Cerca conflitti nel calendario finale
    for did, per_data in mappa.items():
        docente = Docente.query.get(did)
        for data, per_ora in per_data.items():
            for ora, classi in per_ora.items():
                if len(classi) > 1:
                    conflitti.append({
                        "docente": docente.nome_docente,
                        "data": data,
                        "ora": ora,
                        "classi": classi
                    })

    return conflitti


# ============================================================
# VALIDATORE C — CONFRONTO A vs B
# ============================================================

def stampa_report(calendario_per_classe, classi_info):
    """
    Salva classi_info in cache (non serializzabile in sessione)
    E genera il report HTML completo.
    """

    global CLASSI_INFO_CACHE, CALENDARIO_CACHE
    CLASSI_INFO_CACHE = classi_info
    CALENDARIO_CACHE = calendario_per_classe

    conflitti_reali = valida_griglia_reale(classi_info)
    conflitti_finali = valida_calendario_finale(calendario_per_classe)

    # Debug console
    print("\n=== VALIDATORE A (griglia reale) ===")
    print(conflitti_reali)
    print("\n=== VALIDATORE B (calendario finale) ===")
    print(conflitti_finali)

    # HTML per la pagina diagnostica
    return render_html_report(conflitti_reali, conflitti_finali)


def set_validator_cache(calendario, classi_info):
    global CALENDARIO_CACHE, CLASSI_INFO_CACHE
    CALENDARIO_CACHE = calendario
    CLASSI_INFO_CACHE = classi_info


def aggiorna_occupazione_post_sync(calendario_per_classe):
    """
    Ricostruisce OCCUPAZIONE_DOCENTI_GLOBALE a partire dal calendario finale,
    usando la stessa struttura del motore:
    docente_id → data → ora → True
    """
    from app.utils.occupazione import OCCUPAZIONE_DOCENTI_GLOBALE

    OCCUPAZIONE_DOCENTI_GLOBALE.clear()

    for cid, info in calendario_per_classe.items():
        calendario = info["calendario"]
        for giorno in calendario:
            data = giorno["data"]
            for idx, slot in enumerate(giorno["lezioni"]):
                docente_id = slot.get("docente_id")
                if docente_id:
                    OCCUPAZIONE_DOCENTI_GLOBALE.setdefault(docente_id, {})
                    OCCUPAZIONE_DOCENTI_GLOBALE[docente_id].setdefault(data, {})
                    OCCUPAZIONE_DOCENTI_GLOBALE[docente_id][data][idx] = True


def valida_motore(griglie, settimane_classe, ore_giornaliere):
    """
    Controlla la coerenza interna del motore:
    - nessun docente in due classi alla stessa ora
    - nessun buco illegale nella classe
    - nessun buco illegale nel docente
    - nessun giorno con 0 o 1 ore
    - nessun blocco spezzato
    - nessun docente oltre 3 ore nella stessa classe
    """

    errori = []

    # ------------------------------------------------------------
    # 1) Ricostruzione occupazione globale
    # ------------------------------------------------------------
    import app.utils.occupazione as occ
    occ.rebuild_global_occupation(griglie, settimane_classe, ore_giornaliere)
    occ_global = occ.OCCUPAZIONE_DOCENTI_GLOBALE

    # ------------------------------------------------------------
    # 2) Conflitti globali (docente in due classi alla stessa ORA)
    # ------------------------------------------------------------
    for docente_id, giorni in occ_global.items():
        for data, ore in giorni.items():
            for ora in ore.keys():
                classi_presenti = []
                for cid, griglia_classe in griglie.items():
                    if data in griglia_classe:
                        slot = griglia_classe[data][ora]
                        if isinstance(slot, dict) and slot.get("docente_id") == docente_id:
                            classi_presenti.append(cid)

                if len(set(classi_presenti)) > 1:
                    errori.append(
                        f"[CONFLITTO] Docente {docente_id} in più classi il {data} all'ora {ora} (classi: {list(set(classi_presenti))})"
                    )

    # ------------------------------------------------------------
    # 3) Nessun giorno con 0 o 1 ore
    # ------------------------------------------------------------
    for cid, griglia_classe in griglie.items():
        for data, ore in griglia_classe.items():
            ore_presenti = sum(1 for slot in ore if slot is not None)
            if ore_presenti <= 1:
                errori.append(
                    f"[GIORNO VUOTO] Classe {cid} ha solo {ore_presenti} ore il {data}"
                )

    # ------------------------------------------------------------
    # 4) Nessun buco illegale nella classe
    # ------------------------------------------------------------
    for cid, griglia_classe in griglie.items():
        for data, ore in griglia_classe.items():
            for ora in range(len(ore)):
                if ore[ora] is None:
                    if crea_buco_in_giornata(griglia_classe, data, ora, 1):
                        errori.append(
                            f"[BUCO CLASSE] Classe {cid} ha un buco illegale il {data} ora {ora}"
                        )

    # ------------------------------------------------------------
    # 5) Nessun buco illegale nel docente
    # ------------------------------------------------------------
    from app.utils.ordinary_placement import crea_buco_docente

    for docente_id, giorni in occ_global.items():
        for data, ore in giorni.items():
            for ora in ore.keys():
                if crea_buco_docente(docente_id, data, ora):
                    errori.append(
                        f"[BUCO DOCENTE] Docente {docente_id} ha un buco illegale il {data} ora {ora}"
                    )

    # ------------------------------------------------------------
    # 6) Nessun docente oltre 3 ore nella stessa classe
    # ------------------------------------------------------------
    from app.utils.ordinary_placement import count_ore_docente_in_classe

    for cid, griglia_classe in griglie.items():
        for data, ore in griglia_classe.items():
            for docente_id in occ_global.keys():
                ore_doc = count_ore_docente_in_classe(docente_id, griglia_classe, data, ore_giornaliere)
                if ore_doc > 3:
                    errori.append(
                        f"[TROPPE ORE] Docente {docente_id} ha {ore_doc} ore nella classe {cid} il {data}"
                    )

    # ------------------------------------------------------------
    # 7) Nessun blocco spezzato
    # ------------------------------------------------------------
    for cid, griglia_classe in griglie.items():
        for data, ore in griglia_classe.items():
            for ora in range(len(ore) - 1):
                slot = ore[ora]
                next_slot = ore[ora + 1]

                if isinstance(slot, dict) and isinstance(next_slot, dict):
                    if slot["materia"] == next_slot["materia"] and slot["docente_id"] != next_slot["docente_id"]:
                        errori.append(
                            f"[BLOCCO SPEZZATO] Classe {cid} il {data} tra ora {ora} e {ora+1}"
                        )

    return errori
