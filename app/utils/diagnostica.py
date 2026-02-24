# app/utils/diagnostica.py

import os
import openpyxl
from datetime import datetime
from flask import current_app


def diagnostica_sovrapposizioni(calendario_per_classe):
    """
    Controlla tutte le classi e segnala se un docente è assegnato
    a più classi nello stesso giorno e nella stessa ora.
    """

    conflitti = []
    occupazione = {}  # occupazione[docente][data][ora] = [classi]

    for classe_id, dati in calendario_per_classe.items():
        nome_classe = dati["nome_classe"]

        for giorno in dati["calendario"]:
            data = giorno["data"]
            lezioni = giorno["lezioni"]

            for idx, slot in enumerate(lezioni):
                docente = slot["docente"]
                if not docente:
                    continue

                if docente not in occupazione:
                    occupazione[docente] = {}
                if data not in occupazione[docente]:
                    occupazione[docente][data] = {}
                if idx not in occupazione[docente][data]:
                    occupazione[docente][data][idx] = []

                occupazione[docente][data][idx].append(nome_classe)

    for docente, giorni in occupazione.items():

        # ❌ Ignora DOC EST (docente fittizio)
        if docente.strip().upper() == "DOC EST":
            continue

        for data, ore in giorni.items():
            for ora, classi in ore.items():
                if len(classi) > 1:
                    conflitti.append({
                        "docente": docente,
                        "data": data,
                        "ora": ora,
                        "classi": classi
                    })

    return conflitti



def diagnostica_ultimo_calendario():
    """
    Carica l'ultimo calendario XLS generato e lo converte
    in una struttura identica a quella prodotta dal generatore.
    """

    folder = os.path.join(current_app.root_path, "generated_calendars")
    files = sorted(os.listdir(folder), reverse=True)

    if not files:
        return [{"errore": "Nessun calendario generato."}]

    ultimo = files[0]
    path = os.path.join(folder, ultimo)

    wb = openpyxl.load_workbook(path)

    calendario_per_classe = {}

    for sheet in wb.sheetnames:
        ws = wb[sheet]

        calendario = []
        current_day = None
        lezioni_giorno = []

        for row in ws.iter_rows(min_row=2, values_only=True):
            data_str, giorno_label, ora_str, materia, docente = row

            if not data_str:
                continue

            data = datetime.strptime(data_str, "%d/%m/%Y").date()

            if current_day != data:
                if current_day is not None:
                    calendario.append({
                        "data": current_day,
                        "giorno_settimana": giorno_label_prev,
                        "lezioni": lezioni_giorno
                    })
                current_day = data
                giorno_label_prev = giorno_label
                lezioni_giorno = []

            ora = datetime.strptime(ora_str, "%H:%M").time()
            lezioni_giorno.append({
                "ora": ora,
                "materia": materia,
                "docente": docente
            })

        if current_day is not None:
            calendario.append({
                "data": current_day,
                "giorno_settimana": giorno_label_prev,
                "lezioni": lezioni_giorno
            })

        calendario_per_classe[sheet] = {
            "nome_classe": sheet,
            "ore_giornaliere": 6,
            "calendario": calendario
        }

    return diagnostica_sovrapposizioni(calendario_per_classe)
