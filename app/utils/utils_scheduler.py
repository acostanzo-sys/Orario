# app/utils/utils_scheduler.py

from app.utils.orario_utils import docente_disponibile
import app.utils.occupazione as occ
from app.models import Docente
from app.utils.occupazione import docente_disponibile_global


print(">>> LOADING utils_scheduler.py FROM:", __file__)


def docente_ok_wrapper(docente_id, data_g, giorno_it, start, blocco):
    occ_glob = occ.OCCUPAZIONE_DOCENTI_GLOBALE

    print(">>> CHECK:", docente_id, data_g, "OCCUPATO:", 
          occ_glob.get(docente_id, {}).get(data_g, {}))

    try:
        docente_id_norm = int(docente_id) if docente_id is not None else None
    except:
        return False

    docente = Docente.query.get(docente_id_norm) if docente_id_norm else None

    if docente and docente.nome_docente == "DOC EST":
        return True

    if docente_id_norm and not docente:
        return False

    if docente_id_norm is None:
        return True

    # 1) Controllo sovrapposizioni globali
    occ_doc = occ_glob.get(docente_id_norm, {})
    slots_occupati = occ_doc.get(data_g, {})

    for i in range(start, start + blocco):
        if i in slots_occupati:
            return False

    # 2) Controllo disponibilità oraria
    for i in range(start, start + blocco):
        if not docente_disponibile(docente_id_norm, giorno_it, i):
            return False

    return True



# ============================================================
# 2) EVITA BUCHI
# ============================================================

def crea_buco_in_giornata(griglia, data, ora, durata):
    """
    Ritorna True se lo spostamento creerebbe un buco nella giornata.
    Gestisce correttamente giornate vuote o parzialmente vuote.
    """

    row = griglia[data]

    # Se è una LISTA → usa una COPIA TEMPORANEA, NON modificarla nella griglia
    if isinstance(row, list):
        row = {i: row[i] for i in range(len(row))}

    # Trova tutte le ore occupate
    ore_occupate = [o for o, slot in row.items() if slot is not None]

    # Se la giornata è completamente vuota → nessun buco possibile
    if not ore_occupate:
        return False

    prima = min(ore_occupate)
    ultima = max(ore_occupate)

    # Se stiamo inserendo PRIMA della prima ora → nessun buco
    if ora <= prima:
        return False

    # Se stiamo inserendo DOPO l'ultima ora → nessun buco
    if ora >= ultima:
        return False

    # Se stiamo inserendo in mezzo → controlliamo se crea un buco
    for o in range(prima, ultima + 1):
        if row.get(o) is None and o != ora:
            return True

    return False

# ============================================================
# 3) COMPATTAZIONE SICURA
# ============================================================

def compatta_giornata(griglia, data):
    """
    Compatta una giornata SENZA MAI creare conflitti:
    - usa docente_ok_wrapper per ogni spostamento
    - controlla disponibilità globale e locale
    - non tocca fissi, speciali, stage, festa, DOC EST
    - non spezza blocchi
    - non crea buchi
    """

    row = griglia[data]

    # Se è una LISTA → usa una COPIA TEMPORANEA, NON modificarla nella griglia
    if isinstance(row, list):
        row = {i: row[i] for i in range(len(row))}

    # Ora row è SEMPRE un dict temporaneo
    ore = sorted(row.keys())
    target = 0

    for ora in ore:
        slot = row[ora]

        # slot vuoto → niente da spostare
        if slot is None:
            continue

        # slot non-dict → ignora
        if not isinstance(slot, dict):
            continue

        docente_id = slot.get("docente_id")

        # NON toccare fissi, speciali, stage, festa, DOC EST
        if slot.get("fisso"):
            target += 1
            continue
        if slot.get("tipo") in ("STAGE", "FESTA", "SPECIALE"):
            target += 1
            continue
        if slot.get("docente") and "DOC EST" in slot.get("docente"):
            target += 1
            continue

        # Se target == ora → già compatto
        if target == ora:
            target += 1
            continue

        # Controllo disponibilità locale (wrapper)
        try:
            from app.utils.orario_utils import label_giorno_it
            giorno_it = label_giorno_it(data)
        except:
            giorno_it = None

        if docente_id and giorno_it:
            if not docente_ok_wrapper(docente_id, data, giorno_it, target, 1):
                target += 1
                continue

        # Controllo disponibilità globale
        if docente_id and not docente_disponibile_global(docente_id, data, target):
            target += 1
            continue

        # NON creare buchi
        if crea_buco_in_giornata(griglia, data, target, 1):
            target += 1
            continue

        # SPOSTAMENTO SICURO
        # ⚠️ Ora dobbiamo modificare la griglia vera, NON la copia temporanea
        gr_row = griglia[data]

        # Se la griglia reale è ancora una lista → convertiamola ORA (una sola volta)
        if isinstance(gr_row, list):
            gr_row = {i: gr_row[i] for i in range(len(gr_row))}
            griglia[data] = gr_row

        # Eseguiamo lo spostamento sulla griglia reale
        gr_row[target] = slot
        gr_row[ora] = None

        # aggiorna globale
        if docente_id:
            occ.OCCUPAZIONE_DOCENTI_GLOBALE.setdefault(docente_id, {})
            occ.OCCUPAZIONE_DOCENTI_GLOBALE[docente_id].setdefault(data, {})
            occ.OCCUPAZIONE_DOCENTI_GLOBALE[docente_id][data][target] = True

            occ.OCCUPAZIONE_DOCENTI_GLOBALE[docente_id][data].pop(ora, None)

        target += 1


def ottimizza_settimana_classe(griglie, settimane_classe, classe):
    """
    Ottimizzazione locale settimanale:
    - evita giorni troppo leggeri/pesanti
    - sposta singole lezioni da giorni pieni a giorni poveri
    - usa giornata_ok_intelligente come criterio
    """

    ore_giornaliere = classe.ore_massime_giornaliere or 6

    for key in sorted(settimane_classe.keys()):
        giorni_settimana = sorted(settimane_classe[key], key=lambda x: x["data"])
        griglia = griglie[key]

        # calcola carico per giorno
        carichi = []
        for g in giorni_settimana:
            data_g = g["data"]
            lez = griglia[data_g]
            tot = sum(1 for s in lez if s is not None)
            carichi.append((data_g, tot))

        # giorni poveri (<4) e giorni ricchi (>5)
        poveri = [d for d, tot in carichi if 0 < tot < 4]
        ricchi = [d for d, tot in carichi if tot > 5]

        for data_p in poveri:
            for data_r in ricchi:
                if data_p == data_r:
                    continue

                lez_p = griglia[data_p]
                lez_r = griglia[data_r]

                # prova a prendere una lezione "spostabile" dal giorno ricco
                for ora_r, slot in enumerate(lez_r):
                    if slot is None or slot.get("fisso"):
                        continue

                    docente_id = slot["docente_id"]

                    # cerca uno slot libero nel giorno povero
                    for ora_p in range(ore_giornaliere):
                        if lez_p[ora_p] is not None:
                            continue

                        # docente libero nel giorno povero?
                        if docente_id:
                            if ora_p in occ.OCCUPAZIONE_DOCENTI_GLOBALE.get(docente_id, {}).get(data_p, {}):
                                continue

                        # prova lo spostamento
                        lez_p[ora_p] = slot
                        lez_r[ora_r] = None

                        if giornata_ok_intelligente(lez_p) and giornata_ok_intelligente(lez_r):
                            # aggiorna globale
                            if docente_id:
                                occ.OCCUPAZIONE_DOCENTI_GLOBALE.setdefault(docente_id, {})
                                occ.OCCUPAZIONE_DOCENTI_GLOBALE[docente_id].setdefault(data_p, {})
                                occ.OCCUPAZIONE_DOCENTI_GLOBALE[docente_id][data_p][ora_p] = True
                                occ.OCCUPAZIONE_DOCENTI_GLOBALE[docente_id].get(data_r, {}).pop(ora_r, None)
                            break
                        else:
                            # rollback
                            lez_r[ora_r] = slot
                            lez_p[ora_p] = None
                    else:
                        continue
                    break
