from flask import Blueprint, render_template, request, redirect, url_for, flash
from app.models import db, AnnoFormativo, Classe, CalendarioClasse
from datetime import datetime

anni_bp = Blueprint("anni", __name__, url_prefix="/anni")


@anni_bp.route("/", methods=["GET", "POST"])
def gestione_anno():
    anno = AnnoFormativo.query.first()
    classi = Classe.query.order_by(Classe.nome_classe).all()

    # ---------------------------------------------------------
    # POST: SALVATAGGIO ANNO FORMATIVO + AGGIORNAMENTO CLASSI
    # ---------------------------------------------------------
    if request.method == "POST":

        # --- Lettura date generali ---
        data_inizio_raw = request.form.get("data_inizio")
        data_fine_raw = request.form.get("data_fine")

        if not data_inizio_raw or not data_fine_raw:
            flash("Inserisci sia la data di inizio che la data di fine dell'anno formativo.", "danger")
            return redirect(url_for("anni.gestione_anno"))

        data_inizio = datetime.strptime(data_inizio_raw, "%Y-%m-%d").date()
        data_fine = datetime.strptime(data_fine_raw, "%Y-%m-%d").date()

        ora_inizio = request.form.get("ora_inizio")
        ora_fine = request.form.get("ora_fine")
        sabato = request.form.get("sabato") == "on"

        # --- Salvataggio anno formativo generale ---
        if anno:
            anno.data_inizio = data_inizio
            anno.data_fine = data_fine
            anno.ora_inizio = ora_inizio
            anno.ora_fine = ora_fine
            anno.sabato = sabato
        else:
            anno = AnnoFormativo(
                data_inizio=data_inizio,
                data_fine=data_fine,
                ora_inizio=ora_inizio,
                ora_fine=ora_fine,
                sabato=sabato
            )
            db.session.add(anno)

        # ---------------------------------------------------------
        # AGGIORNA AUTOMATICAMENTE TUTTE LE CLASSI
        # ---------------------------------------------------------
        for classe in classi:

            # Se i campi della classe sono vuoti → usa le date generali
            data_i_raw = request.form.get(f"classe_{classe.id}_inizio") or data_inizio_raw
            data_f_raw = request.form.get(f"classe_{classe.id}_fine") or data_fine_raw

            data_i = datetime.strptime(data_i_raw, "%Y-%m-%d").date()
            data_f = datetime.strptime(data_f_raw, "%Y-%m-%d").date()

            ore_max = int(request.form.get(f"classe_{classe.id}_ore"))
            giorni = ",".join(request.form.getlist(f"classe_{classe.id}_giorni"))

            # --- Calendario classe ---
            calendario = CalendarioClasse.query.filter_by(classe_id=classe.id).first()
            if calendario:
                calendario.data_inizio = data_i
                calendario.data_fine = data_f
            else:
                db.session.add(CalendarioClasse(
                    classe_id=classe.id,
                    data_inizio=data_i,
                    data_fine=data_f
                ))

            # --- Impostazioni classe ---
            classe.ore_massime_giornaliere = ore_max
            classe.giorni_lezione = giorni

        db.session.commit()
        flash("Anno formativo e calendari classe salvati!", "success")
        return redirect(url_for("anni.gestione_anno"))

    # ---------------------------------------------------------
    # GET: PREPARA I CALENDARI PER LA PAGINA
    # ---------------------------------------------------------
    calendari = {}
    for classe in classi:
        cal = CalendarioClasse.query.filter_by(classe_id=classe.id).first()
        calendari[classe.id] = cal

    return render_template("anni.html", anno=anno, classi=classi, calendari=calendari)
