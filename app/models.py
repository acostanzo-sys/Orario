from app import db
from datetime import date

class Classe(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome_classe = db.Column(db.String(50), nullable=False, unique=True)

    ore_massime_giornaliere = db.Column(db.Integer, default=6)
    giorni_lezione = db.Column(db.String(50), default="lun,mar,mer,gio,ven")

    # Relazione corretta (nessun conflitto)
    materie_assegnate = db.relationship("MateriaClasse", backref="classe", cascade="all, delete-orphan")

    calendario = db.relationship("CalendarioClasse", backref="classe", uselist=False, cascade="all, delete-orphan")


class Docente(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome_docente = db.Column(db.String(100), nullable=False)

    insegnamenti = db.relationship("MateriaClasse", backref="docente_rel", cascade="all, delete-orphan")


class MateriaClasse(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    # Collegamento alla classe
    classe_id = db.Column(db.Integer, db.ForeignKey("classe.id"), nullable=False)

    # Collegamento alla materia
    materia_id = db.Column(db.Integer, db.ForeignKey("materia.id"), nullable=False)
    materia = db.relationship("Materia")

    # Ore annuali (nuovo campo)
    ore_annuali = db.Column(db.Integer, nullable=False)

    # Docente assegnato
    docente_id = db.Column(db.Integer, db.ForeignKey("docente.id"), nullable=False)
    docente = db.relationship("Docente")

    # Ore minime consecutive richieste
    ore_minime_consecutive = db.Column(db.Integer, nullable=False, default=1)


class AnnoFormativo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    data_inizio = db.Column(db.Date, nullable=False)
    data_fine = db.Column(db.Date, nullable=False)

    ora_inizio = db.Column(db.String(5), default="08:00")
    ora_fine = db.Column(db.String(5), default="14:00")
    sabato = db.Column(db.Boolean, default=False)


class CalendarioClasse(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    classe_id = db.Column(db.Integer, db.ForeignKey("classe.id"), nullable=False)
    data_inizio = db.Column(db.Date, nullable=False)
    data_fine = db.Column(db.Date, nullable=False)


class Stage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    classe_id = db.Column(db.Integer, db.ForeignKey("classe.id"), nullable=False)

    periodo_stage_1_da = db.Column(db.Date)
    periodo_stage_1_a = db.Column(db.Date)
    periodo_stage_2_da = db.Column(db.Date)
    periodo_stage_2_a = db.Column(db.Date)

    classe = db.relationship("Classe")



class Vincolo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    descrizione = db.Column(db.String(255), nullable=False)


class VincoloDocente(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    docente_id = db.Column(db.Integer, db.ForeignKey("docente.id"), nullable=False)
    giorno = db.Column(db.String(20), nullable=False)
    ora_da = db.Column(db.String(5), nullable=False)
    ora_a = db.Column(db.String(5), nullable=False)

    docente = db.relationship("Docente", backref="disponibilita")


class OrarioGenerato(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    classe_id = db.Column(db.Integer, db.ForeignKey("classe.id"), nullable=False)
    giorno = db.Column(db.String(10), nullable=False)
    ora = db.Column(db.Integer, nullable=False)
    materia = db.Column(db.String(100), nullable=False)
    docente = db.Column(db.String(100), nullable=False)


class Festivita(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    data_inizio = db.Column(db.Date, nullable=False)
    data_fine = db.Column(db.Date, nullable=False)
    descrizione = db.Column(db.String(255), nullable=True)


class GiornoSpeciale(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    classe_id = db.Column(db.Integer, db.ForeignKey("classe.id"), nullable=False)
    data = db.Column(db.Date, nullable=False)
    materia = db.Column(db.String(100), nullable=False)
    ore = db.Column(db.Integer, nullable=False)
    docente = db.Column(db.String(100), nullable=True)

    classe = db.relationship("Classe", backref="giorni_speciali")


class Materia(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False, unique=True)
    colore = db.Column(db.String(20), default="#007bff")

class DisponibilitaAnnua(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    docente_id = db.Column(db.Integer, db.ForeignKey("docente.id"), nullable=False)

    data_da = db.Column(db.Date, nullable=False)
    data_a = db.Column(db.Date, nullable=False)

    docente = db.relationship("Docente", backref="disponibilita_annua")


class GiornoFisso(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    classe_id = db.Column(db.Integer, db.ForeignKey("classe.id"), nullable=False)
    materia_id = db.Column(db.Integer, db.ForeignKey("materia.id"), nullable=False)

    giorno = db.Column(db.String(10), nullable=False)  # lun, mar, mer, gio, ven, sab
    ore = db.Column(db.Integer, nullable=False, default=1)

    classe = db.relationship("Classe")
    materia = db.relationship("Materia")
