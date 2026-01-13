# app/routes/orario.py

from flask import Blueprint, render_template, send_file
from datetime import datetime, date, time, timedelta
from io import BytesIO

from app.models import (
    db,
    Classe,
    MateriaClasse,
    Materia,
    AnnoFormativo,
    GiornoFisso,
    VincoloDocente,
    GiornoSpeciale,
    Stage,
    Docente,
)

import openpyxl

orario_bp = Blueprint("orario", __name__, url_prefix="/orario")

# ===============================
# CONFIGURAZIONE ORARIA
# ===============================

ORA_INIZIO_LEZIONI = time(8, 0)   # 08:00
DURATA_ORA_MINUTI = 60            # ore fisse da 60 minuti

# ===============================
# REPORT VINCOLI
# ===============================

REPORT_VINCOLI = {}  # popolato da genera_calendario_annuale()

# ===============================
# UTILS
# ===============================

def normalizza_giorno(g):
    if not g:
        return None
    g = g.strip().lower()
    mapping = {
        "lun": "Lunedì", "lunedì": "Lunedì", "lunedi": "Lunedì",
        "mar": "Martedì", "martedì": "Martedì", "martedi": "Martedì",
        "mer": "Mercoledì", "mercoledì": "Mercoledì", "mercoledi": "Mercoledì",
        "gio": "Giovedì", "giovedì": "Giovedì", "giovedi": "Giovedì",
        "ven": "Venerdì", "venerdì": "Venerdì", "venerdi": "Venerdì",
        "sab": "Sabato", "sabato": "Sabato",
    }
    return mapping.get(g, g)


def orario_slot(index_ora):
    """
    Ritorna l'orario di inizio di uno slot (datetime.time) dato l'indice (0-based).
    """
    start_dt = datetime.combine(date.today(), ORA_INIZIO_LEZIONI) + timedelta(
        minutes=DURATA_ORA_MINUTI * index_ora
    )
    return start_dt.time()


def intervalli_si_sovrappongono(inizio1, fine1, inizio2, fine2):
    """
    True se [inizio1, fine1) e [inizio2, fine2) si sovrappongono.
    """
    return inizio1 < fine2 and inizio2 < fine1


def docente_disponibile(docente_id, giorno_label, index_ora):
    """
    Controllo vincoli docente:
    - giorno: stringa tipo 'Lunedì'
    - ora: indice slot (0-based)
    """
    if not docente_id:
        return True

    slot_start = orario_slot(index_ora)
    slot_end_dt = datetime.combine(date.today(), slot_start) + timedelta(
        minutes=DURATA_ORA_MINUTI
    )
    slot_end = slot_end_dt.time()

    vincoli = VincoloDocente.query.filter_by(docente_id=docente_id, giorno=giorno_label).all()

    for v in vincoli:
        if v.ora_da and v.ora_a:
            ora_da = v.ora_da
            ora_a = v.ora_a

            if isinstance(ora_da, str):
                ora_da = datetime.strptime(ora_da, "%H:%M").time()
            if isinstance(ora_a, str):
                ora_a = datetime.strptime(ora_a, "%H:%M").time()

            if intervalli_si_sovrappongono(slot_start, slot_end, ora_da, ora_a):
                return False

    return True


def classe_in_stage(classe_id, data_giorno):
    """
    True se la classe è in stage in quella data.
    """
    stage = Stage.query.filter_by(classe_id=classe_id).first()
    if not stage:
        return False

    periodi = [
        (stage.periodo_stage_1_da, stage.periodo_stage_1_a),
        (stage.periodo_stage_2_da, stage.periodo_stage_2_a),
    ]

    for da, a in periodi:
        if da and a and da <= data_giorno <= a:
            return True

    return False


def giorno_speciale_classe(classe_id, data_giorno):
    """
    Ritorna l'eventuale GiornoSpeciale per quella classe e data, altrimenti None.
    """
    return GiornoSpeciale.query.filter_by(
        classe_id=classe_id, data=data_giorno
    ).first()


def periodo_classe(classe, anno):
    """
    Stabilisce il periodo effettivo di calendario per la classe:
    - se la classe ha date proprie, usale
    - altrimenti usa l'anno formativo generale
    """
    data_inizio = getattr(classe, "data_inizio", None) or anno.data_inizio
    data_fine = getattr(classe, "data_fine", None) or anno.data_fine
    return data_inizio, data_fine


def label_giorno_it(dt):
    """
    Converte dt.strftime('%A') in etichetta italiana.
    """
    mapping_it = {
        "Monday": "Lunedì",
        "Tuesday": "Martedì",
        "Wednesday": "Mercoledì",
        "Thursday": "Giovedì",
        "Friday": "Venerdì",
        "Saturday": "Sabato",
        "Sunday": "Domenica",
    }
    return mapping_it.get(dt.strftime("%A"), dt.strftime("%A"))

# ===============================
# CALENDARIO ANNUALE CON RECUPERO INTELLIGENTE
# ===============================

def genera_calendario_annuale():
    """
    Genera direttamente il calendario annuale per ogni classe,
    distribuendo le ore settimanali con recupero intelligente
    (senza usare una settimana tipo fissa).
    """
    global REPORT_VINCOLI
    REPORT_VINCOLI = {}

    anno = AnnoFormativo.query.first()
    if not anno:
        return {}

    classi = Classe.query.order_by(Classe.nome_classe).all()
    materie_dict = {m.id: m.nome for m in Materia.query.all()}

    calendario_per_classe = {}

    for classe in classi:
        # Giorni di lezione
        if classe.giorni_lezione:
            giorni_lezione = [g.strip() for g in classe.giorni_lezione.split(",") if g.strip()]
        else:
            giorni_lezione = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì"]

        ore_giornaliere = classe.ore_massime_giornaliere or 6

        data_inizio, data_fine = periodo_classe(classe, anno)

        # Lista di tutte le date di lezione (solo giorni_lezione)
        giorni_classe = []
        current = data_inizio
        while current <= data_fine:
            giorno_it = label_giorno_it(current)
            if giorno_it in giorni_lezione:
                iso_year, iso_week, _ = current.isocalendar()
                giorni_classe.append({
                    "data": current,
                    "giorno_it": giorno_it,
                    "iso_year": iso_year,
                    "iso_week": iso_week,
                })
            current += timedelta(days=1)

        # Nessun giorno di lezione → passa alla prossima classe
        if not giorni_classe:
            calendario_per_classe[classe.id] = {
                "nome_classe": classe.nome_classe,
                "ore_giornaliere": ore_giornaliere,
                "calendario": [],
            }
            REPORT_VINCOLI[classe.id] = {
                "nome_classe": classe.nome_classe,
                "report": [],
            }
            continue

        # Gruppo per settimana (iso_year, iso_week)
        settimane = {}
        for g in giorni_classe:
            key = (g["iso_year"], g["iso_week"])
            settimane.setdefault(key, []).append(g)

        num_settimane = len(settimane) if settimane else 1

        # Materie della classe
        materie_classe = MateriaClasse.query.filter_by(classe_id=classe.id).all()

        materie_info = {}
        for mc in materie_classe:
            ore_annuali = mc.ore_annuali or 0
            if ore_annuali <= 0:
                continue

            ore_settimanali = max(1, round(ore_annuali / num_settimane))

            docente_nome = mc.docente.nome_docente if getattr(mc, "docente", None) else ""
            docente_id = mc.docente_id if hasattr(mc, "docente_id") else None

            materie_info[mc.materia_id] = {
                "id": mc.materia_id,
                "nome": materie_dict.get(mc.materia_id, "Materia"),
                "docente": docente_nome,
                "docente_id": docente_id,
                "ore_annuali_totali": ore_annuali,
                "ore_settimanali_teoriche": ore_settimanali,
                "ore_assegnate": 0,
                "debito_residuo": ore_annuali,
                "ore_non_piazzate_accumulate": 0,
                "ore_minime_consecutive": mc.ore_minime_consecutive or 1,
            }

        calendario = []

        # Ordino le settimane cronologicamente
        settimane_keys = sorted(settimane.keys())

        for key in settimane_keys:
            giorni_settimana = sorted(settimane[key], key=lambda x: x["data"])

            # Griglia settimanale: data -> [slot]
            griglia_settimana = {}
            for g in giorni_settimana:
                griglia_settimana[g["data"]] = [None] * ore_giornaliere

            # Giorni speciali
            giorni_speciali_map = {}
            for g in giorni_settimana:
                gs = giorno_speciale_classe(classe.id, g["data"])
                if gs:
                    giorni_speciali_map[g["data"]] = gs

            # Giorni fissi per questa classe
            giorni_fissi = GiornoFisso.query.filter_by(classe_id=classe.id).all()

            # Applica stage, giorni speciali, giorni fissi
            for g in giorni_settimana:
                data_giorno = g["data"]
                giorno_it = g["giorno_it"]

                # Stage: giornata bloccata
                if classe_in_stage(classe.id, data_giorno):
                    griglia_settimana[data_giorno] = [
                        {"materia": "STAGE", "docente": "", "docente_id": None}
                        for _ in range(ore_giornaliere)
                    ]
                    continue

                # Giorno speciale
                gs = giorni_speciali_map.get(data_giorno)
                if gs:
                    for i in range(min(gs.ore, ore_giornaliere)):
                        griglia_settimana[data_giorno][i] = {
                            "materia": gs.materia,
                            "docente": gs.docente or "",
                            "docente_id": getattr(gs, "docente_id", None),
                        }

                # Giorni fissi (materie fisse in certe giornate)
                for gf in giorni_fissi:
                    giorno_label = normalizza_giorno(gf.giorno)
                    if giorno_label != giorno_it:
                        continue
                    for i in range(min(gf.ore, ore_giornaliere)):
                        if griglia_settimana[data_giorno][i] is None:
                            griglia_settimana[data_giorno][i] = {
                                "materia": materie_dict.get(gf.materia_id, "Materia"),
                                "docente": "",
                                "docente_id": None,
                            }

            # Piazzamento materie "normali" con recupero intelligente
            for mid, info in materie_info.items():
                if info["debito_residuo"] <= 0:
                    continue

                # ore teoriche + recupero, ma non oltre il debito complessivo
                ore_da_piazzare = info["ore_settimanali_teoriche"] + info["ore_non_piazzate_accumulate"]
                ore_da_piazzare = min(ore_da_piazzare, info["debito_residuo"])

                if ore_da_piazzare <= 0:
                    continue

                ore_piazzate_questa_settimana = 0

                while ore_da_piazzare > 0:
                    piazzata = False

                    for g in giorni_settimana:
                        data_giorno = g["data"]
                        giorno_it = g["giorno_it"]

                        # se tutta la giornata è STAGE, salta
                        if all(
                            slot is not None and slot.get("materia") == "STAGE"
                            for slot in griglia_settimana[data_giorno]
                        ):
                            continue

                        blocco = info["ore_minime_consecutive"]
                        if blocco > ore_da_piazzare:
                            blocco = ore_da_piazzare

                        for start in range(0, ore_giornaliere - blocco + 1):
                            slot_ok = True
                            for i in range(start, start + blocco):
                                slot = griglia_settimana[data_giorno][i]
                                if slot is not None:
                                    slot_ok = False
                                    break

                                if not docente_disponibile(info["docente_id"], giorno_it, i):
                                    slot_ok = False
                                    break

                            if slot_ok:
                                for i in range(start, start + blocco):
                                    griglia_settimana[data_giorno][i] = {
                                        "materia": info["nome"],
                                        "docente": info["docente"],
                                        "docente_id": info["docente_id"],
                                    }
                                ore_da_piazzare -= blocco
                                ore_piazzate_questa_settimana += blocco
                                piazzata = True
                                break  # prossimo blocco / giorno

                        if piazzata:
                            break

                    if not piazzata:
                        # non riesco a piazzare altre ore per questa materia in questa settimana
                        break

                # aggiorno debito e recupero
                info["ore_assegnate"] += ore_piazzate_questa_settimana
                info["debito_residuo"] -= ore_piazzate_questa_settimana
                info["ore_non_piazzate_accumulate"] = (
                    info["ore_settimanali_teoriche"] + info["ore_non_piazzate_accumulate"]
                    - ore_piazzate_questa_settimana
                )
                if info["ore_non_piazzate_accumulate"] < 0:
                    info["ore_non_piazzate_accumulate"] = 0

            # Aggiungo i giorni di questa settimana al calendario
            for g in giorni_settimana:
                data_giorno = g["data"]
                giorno_it = g["giorno_it"]

                lezioni = []
                for idx in range(ore_giornaliere):
                    slot = griglia_settimana[data_giorno][idx]
                    ora = orario_slot(idx)
                    if slot is None:
                        lezioni.append({
                            "ora": ora,
                            "materia": "",
                            "docente": "",
                        })
                    else:
                        lezioni.append({
                            "ora": ora,
                            "materia": slot.get("materia", ""),
                            "docente": slot.get("docente", ""),
                        })

                calendario.append({
                    "data": data_giorno,
                    "giorno_settimana": giorno_it,
                    "lezioni": lezioni,
                })

        # Ordino il calendario per data
        calendario.sort(key=lambda x: x["data"])

        calendario_per_classe[classe.id] = {
            "nome_classe": classe.nome_classe,
            "ore_giornaliere": ore_giornaliere,
            "calendario": calendario,
        }

        # ===============================
        # REPORT VINCOLI PER QUESTA CLASSE
        # ===============================
        report_classe = []
        for mid, info in materie_info.items():
            ore_non_piazzate = info["debito_residuo"]
            if ore_non_piazzate > 0:
                report_classe.append({
                    "materia": info["nome"],
                    "docente": info["docente"],
                    "ore_annuali": info["ore_annuali_totali"],
                    "piazzate": info["ore_assegnate"],
                    "non_piazzate": ore_non_piazzate,
                })

        REPORT_VINCOLI[classe.id] = {
            "nome_classe": classe.nome_classe,
            "report": report_classe,
        }

    return calendario_per_classe

# ===============================
# ROUTE: ANTEPRIMA (prima settimana reale)
# ===============================

@orario_bp.route("/genera")
def genera():
    """
    Mostra una anteprima del calendario:
    per ogni classe, mostra la prima settimana di lezioni trovata.
    """

    calendario = genera_calendario_annuale()

    anteprima = {}

    for cid, dati in calendario.items():
        if not dati["calendario"]:
            continue

        giorni = dati["calendario"]
        first = giorni[0]["data"]
        iso_year, iso_week, _ = first.isocalendar()

        settimana = []
        for g in giorni:
            y, w, _ = g["data"].isocalendar()
            if y == iso_year and w == iso_week:
                settimana.append(g)

        anteprima[cid] = {
            "nome_classe": dati["nome_classe"],
            "ore_giornaliere": dati["ore_giornaliere"],
            "settimana": settimana,
        }

    # DEBUG ora è valido
    print("DEBUG anteprima:", anteprima)

    return render_template("genera_calendario.html", anteprima=anteprima)

# ===============================
# ROUTE: EXPORT XLS CALENDARIO ANNUALE
# ===============================

@orario_bp.route("/export_xls")
def export_xls():
    """
    Genera il calendario annuale completo e lo esporta in XLSX.
    Un foglio per classe, con righe:
    Data | Giorno | Ora | Materia | Docente
    """
    calendario = genera_calendario_annuale()

    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    for classe_id, dati in calendario.items():
        ws = wb.create_sheet(title=dati["nome_classe"][:31])

        # intestazioni
        ws.cell(row=1, column=1, value="Data")
        ws.cell(row=1, column=2, value="Giorno")
        ws.cell(row=1, column=3, value="Ora")
        ws.cell(row=1, column=4, value="Materia")
        ws.cell(row=1, column=5, value="Docente")

        row = 2
        for giorno in dati["calendario"]:
            data_str = giorno["data"].strftime("%d/%m/%Y")
            giorno_label = giorno["giorno_settimana"]

            for lezione in giorno["lezioni"]:
                ora_str = lezione["ora"].strftime("%H:%M")
                ws.cell(row=row, column=1, value=data_str)
                ws.cell(row=row, column=2, value=giorno_label)
                ws.cell(row=row, column=3, value=ora_str)
                ws.cell(row=row, column=4, value=lezione["materia"])
                ws.cell(row=row, column=5, value=lezione["docente"])
                row += 1

        ws.column_dimensions["A"].width = 12
        ws.column_dimensions["B"].width = 12
        ws.column_dimensions["C"].width = 8
        ws.column_dimensions["D"].width = 25
        ws.column_dimensions["E"].width = 25

    output = BytesIO()
    wb.save(output)
    output.seek(0)

    return send_file(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name="calendario_scolastico.xlsx",
    )

# ===============================
# ROUTE: REPORT VINCOLI
# ===============================

@orario_bp.route("/report_vincoli")
def report_vincoli():
    """
    Mostra quante ore non sono state piazzate per ogni materia di ogni classe.
    """
    # Se per qualche motivo non è ancora stato generato, rigenero
    if not REPORT_VINCOLI:
        genera_calendario_annuale()

    return render_template("report_vincoli.html", report=REPORT_VINCOLI)
