# app/utils/calendario_generator.py

from .class_setup import prepara_classi
from .stage_handler import apply_stage
from app.utils.festivita_handler import apply_festivita
from .special_days_handler import apply_special_days
from .fixed_days_handler import apply_fixed_days
from .ordinary_placement import apply_ordinary, inizializza_occupazione_globale_da_locale

from app.utils.orario_utils import (
    crea_griglia_settimanale,
    costruisci_settimana,
    salva_calendari,
    sincronizza_classi_associate
)

from app.utils.utils_scheduler import (
    docente_ok_wrapper,
    # ottimizza_settimana_classe  # ❌ NON SERVE PIÙ
)

import app.utils.occupazione as occ

print(">>> VERSIONE PATCHATA DEFINITIVA")


def genera_calendario_annuale():

    # 🔹 0) PULISCI OCCUPAZIONE GLOBALE UNA VOLTA SOLA
    occ.OCCUPAZIONE_DOCENTI_GLOBALE.clear()

    (
        classi_info,
        classi,
        materie_dict,
        docenti_dict,
        nomi_non_prof,
        occupazione_docenti
    ) = prepara_classi()

    # 🔹 0bis) INIZIALIZZA OCCUPAZIONE GLOBALE DAI DATI LOCALI (UNA VOLTA SOLA)
    inizializza_occupazione_globale_da_locale(occupazione_docenti)

    for cid, info in classi_info.items():

        classe = info["classe"]
        settimane_classe = info["settimane_classe"]
        ore_giornaliere = info["ore_giornaliere"]
        materie_info = info["materie_info"]
        giorni_fissi_classe = info["giorni_fissi"]

        # Ogni classe deve avere un calendario indipendente
        calendario = []
        info["calendario"] = calendario

        # 1) CREA GRIGLIE
        griglie = {}
        for key in sorted(settimane_classe.keys()):
            giorni_settimana = sorted(settimane_classe[key], key=lambda x: x["data"])
            griglie[key] = crea_griglia_settimanale(giorni_settimana, ore_giornaliere)

        # 2) STAGE, FESTIVITÀ, SPECIALI, FISSI
        for key in sorted(settimane_classe.keys()):
            giorni_settimana = sorted(settimane_classe[key], key=lambda x: x["data"])

            apply_stage(griglie[key], giorni_settimana, classe)
            apply_festivita(griglie[key], giorni_settimana)

            apply_special_days(
                griglie[key],
                giorni_settimana,
                classe,
                materie_info,
                materie_dict,
                occupazione_docenti,
                docente_ok_wrapper
            )

            apply_fixed_days(
                griglie[key],
                giorni_settimana,
                classe,
                materie_info,
                materie_dict,
                occupazione_docenti,
                giorni_fissi_classe,
                docente_ok_wrapper
            )

        # 3) ORDINARIO (NUOVO MOTORE GLOBALE)
        apply_ordinary(
            griglie,
            settimane_classe,
            classe,
            materie_info,
            materie_dict,
            docenti_dict,
            occupazione_docenti,
            docente_ok_wrapper
        )

        # 4) COSTRUISCI SETTIMANE FINALI (calendario vero)
        for key in sorted(settimane_classe.keys()):
            giorni_settimana = sorted(settimane_classe[key], key=lambda x: x["data"])
            costruisci_settimana(
                griglie[key],
                giorni_settimana,
                ore_giornaliere,
                calendario
            )

        # 6) SALVA GRIGLIE REALI PER VALIDATORE
        info["griglie"] = griglie

    # 7) CALENDARIO FINALE
    calendario_per_classe = salva_calendari(classi_info)

    # 8) DUPLICAZIONE PARALLELE
    from app.utils.associazioni_loader import carica_associazioni_parallele, genera_doc_est_map
    associazioni = carica_associazioni_parallele()
    doc_est_map = genera_doc_est_map(associazioni)

    from app.utils.duplica_classi_parallele import duplica_classi_parallele

    #if associazioni:
        #calendario_per_classe = duplica_classi_parallele(
        #calendario_per_classe,
        #associazioni,
        #doc_est_map
    #)

    # 9) VALIDATORE
    from app.utils.validator import set_validator_cache
    set_validator_cache(calendario_per_classe, classi_info)

    
    from app.utils.validator import valida_motore

    errori = valida_motore(griglie, settimane_classe, classe.ore_massime_giornaliere)

    if errori:
        print("\n=== ERRORI TROVATI ===")
        for e in errori:
            print(e)
    else:
        print("\n=== TUTTO COERENTE ===")

    
    
    return calendario_per_classe
