# init_db.py
from app import create_app
from app.models import db, AnnoFormativo, Classe, Docente, MateriaDocente, Stage, Vincolo, VincoloDocente, OrarioGenerato
from datetime import date

def init_database():
    app = create_app()

    with app.app_context():
        print("🔧 Creazione del database...")
        db.drop_all()      # Se vuoi ricreare tutto da zero, altrimenti commentalo
        db.create_all()

        print("📦 Popolamento dati iniziali...")

        # --- CLASSI DI ESEMPIO ---
        classi_base = ["1A", "1B", "2A", "2B", "3A", "3B"]
        for nome in classi_base:
            db.session.add(Classe(nome_classe=nome))

        # --- DOCENTI DI ESEMPIO ---
        docenti_base = ["Rossi", "Bianchi", "Verdi"]
        for nome in docenti_base:
            db.session.add(Docente(nome_docente=nome))

        db.session.commit()

        # --- MATERIE DOCENTI DI ESEMPIO ---
        docente_rossi = Docente.query.filter_by(nome_docente="Rossi").first()
        classe_1A = Classe.query.filter_by(nome_classe="1A").first()

        if docente_rossi and classe_1A:
            db.session.add(MateriaDocente(
                docente_id=docente_rossi.id,
                materia="Matematica",
                classe_id=classe_1A.id,
                monte_ore_annuo=120
            ))

        db.session.commit()

        print("✅ Database inizializzato con successo!")

if __name__ == "__main__":
    init_database()
