# app/routes/classi.py
from flask import Blueprint, render_template, request, redirect, url_for, flash
from app.models import db, Classe, Docente, Materia, MateriaClasse

classi_bp = Blueprint("classi", __name__, url_prefix="/classi")


# ---------------------------------------------------------
# LISTA CLASSI + CREA CLASSE
# ---------------------------------------------------------
@classi_bp.route("/", methods=["GET", "POST"])
def lista_classi():
    if request.method == "POST":
        nome = request.form.get("nome_classe")
        if not nome:
            flash("Il nome della classe è obbligatorio", "danger")
            return redirect(url_for("classi.lista_classi"))

        nuova = Classe(nome_classe=nome)
        db.session.add(nuova)
        db.session.commit()

        flash("Classe creata!", "success")
        return redirect(url_for("classi.lista_classi"))

    classi = Classe.query.order_by(Classe.nome_classe).all()
    return render_template("classi.html", classi=classi)


# ---------------------------------------------------------
# ELIMINA CLASSE
# ---------------------------------------------------------
@classi_bp.route("/elimina/<int:classe_id>", methods=["POST"])
def elimina_classe(classe_id):
    classe = Classe.query.get_or_404(classe_id)
    db.session.delete(classe)
    db.session.commit()

    flash("Classe eliminata!", "success")
    return redirect(url_for("classi.lista_classi"))


# ---------------------------------------------------------
# PAGINA MATERIE DELLA CLASSE
# ---------------------------------------------------------
@classi_bp.route("/<int:classe_id>/materie")
def materie_classe(classe_id):
    classe = Classe.query.get_or_404(classe_id)

    materie = Materia.query.order_by(Materia.nome).all()
    docenti = Docente.query.order_by(Docente.nome_docente).all()
    materie_classe = MateriaClasse.query.filter_by(classe_id=classe_id).all()

    return render_template(
        "classi_materie.html",
        classe=classe,
        materie=materie,
        docenti=docenti,
        materie_classe=materie_classe
    )


# ---------------------------------------------------------
# CREA MATERIA PER LA CLASSE (ORE ANNUALI)
# ---------------------------------------------------------
@classi_bp.route("/<int:classe_id>/materie/crea", methods=["POST"])
def crea_materia_classe(classe_id):
    materia_id = request.form.get("materia_id")
    ore_annuali = request.form.get("ore_annuali")
    docente_id = request.form.get("docente_id")
    ore_minime = request.form.get("ore_minime_consecutive")

    if not materia_id or not ore_annuali or not docente_id or not ore_minime:
        flash("Compila tutti i campi", "danger")
        return redirect(url_for("classi.materie_classe", classe_id=classe_id))

    nuova = MateriaClasse(
        classe_id=classe_id,
        materia_id=int(materia_id),
        ore_annuali=int(ore_annuali),
        docente_id=int(docente_id),
        ore_minime_consecutive=int(ore_minime)
    )

    db.session.add(nuova)
    db.session.commit()

    flash("Materia aggiunta alla classe!", "success")
    return redirect(url_for("classi.materie_classe", classe_id=classe_id))


# ---------------------------------------------------------
# ELIMINA MATERIA DALLA CLASSE
# ---------------------------------------------------------
@classi_bp.route("/materie/elimina/<int:materia_classe_id>", methods=["POST"])
def elimina_materia_classe(materia_classe_id):
    mc = MateriaClasse.query.get_or_404(materia_classe_id)
    classe_id = mc.classe_id

    db.session.delete(mc)
    db.session.commit()

    flash("Materia rimossa dalla classe!", "success")
    return redirect(url_for("classi.materie_classe", classe_id=classe_id))
