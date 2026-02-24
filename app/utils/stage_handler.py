# app/utils/stage_handler.py

from app.utils.orario_utils import giorno_festivo, classe_in_stage_giorno
import app.utils.occupazione as occ


def apply_stage(griglia, giorni_settimana, classe):
    """
    STAGE (hard lock totale):
    - riempie tutta la giornata con 'STAGE'
    - mantiene la griglia come dict {ora: slot}
    - registra l’occupazione globale come blocco speciale
    - impedisce al motore di vedere buchi
    """

    for g in giorni_settimana:
        data_g = g["data"]

        # Salta festivi veri
        if giorno_festivo(data_g):
            continue

        # Se la classe è in stage → hard-lock totale
        if classe_in_stage_giorno(classe.id, data_g):

            # Assicuriamoci che la griglia sia un dict
            row = griglia[data_g]
            if isinstance(row, list):
                row = {i: row[i] for i in range(len(row))}
                griglia[data_g] = row

            ore_giornaliere = len(row)

            # Riempie la giornata con blocchi STAGE
            for ora in range(ore_giornaliere):
                row[ora] = {
                    "materia": "STAGE",
                    "materia_id": None,
                    "docente": "",
                    "docente_id": None,
                    "fisso": True,
                    "tipo": "STAGE"
                }

            # 🔥 Registra occupazione globale nel formato corretto
            occ.OCCUPAZIONE_DOCENTI_GLOBALE.setdefault("STAGE", {})
            occ.OCCUPAZIONE_DOCENTI_GLOBALE["STAGE"].setdefault(data_g, {})

            for ora in range(ore_giornaliere):
                occ.OCCUPAZIONE_DOCENTI_GLOBALE["STAGE"][data_g][ora] = True
