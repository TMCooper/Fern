import os, sqlite3, hashlib, json

class Database:
    PATH = os.path.dirname(os.path.abspath(__file__))
    PATH_DATA = os.path.join(PATH, "database")
    PATH_DB = os.path.join(PATH_DATA, "database.db")
    
    def check_database():

        if not os.path.exists(Database.PATH_DB): # Si le fichier database.db n'existe pas
            os.makedirs(Database.PATH_DATA) # Alors on crée le chemin vers celui ci 
            with open(Database.PATH_DB, 'w'):
                os.utime(Database.PATH_DB, None) # et on crée le fichier 
            
            Database.create_database(Database.PATH_DB) # Ensuite on interagie avec le fichier pour crée les base de nos data
        return True
        
    
    def create_database(PATH_DB):
        try:

            with sqlite3.connect(PATH_DB) as con:
                cur = con.cursor()

                cur.execute("""
                        CREATE TABLE IF NOT EXISTS Alert (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            id_server TEXT,
                            name_server TEXT,
                            message_content TEXT,
                            message_author TEXT,
                            message_author_id TEXT,
                            deleter_name TEXT,
                            deleter_id TEXT,
                            image_hashes TEXT,
                            deleted_at TEXT,
                            UNIQUE(id_server, message_content, image_hashes)
                        )
                    """) # Creation de la table contenant nos données si celle ci n'existe pas

                con.commit() # commit permet de valider nos modifications
                res = cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='Alert'") # Permet de verifier

                if res.fetchall(): # Si notre verification a obtenue quelque chose alors on l'affiche 
                    print(f"Base de données '{PATH_DB}' prête.")
                else:
                    print("Erreur dans la creation de la database")

        except sqlite3.Error as e:
            print(f"Une erreur SQLite est survenue : {e}")

    def database_incrementation(id_server, name_server, message_content, message_author, message_author_id, deleter_name, deleter_id, hashes, deleted_at):
        try:
            with sqlite3.connect(Database.PATH_DB) as con:
                cur = con.cursor()
                cur.execute("INSERT INTO Alert VALUES (NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (str(id_server), name_server, message_content, message_author, message_author_id, deleter_name, deleter_id, hashes, deleted_at)) # Les ? permette d'eviter une injection sql
                con.commit() # On valide notre entrée
                return True, "Ajouté avec succès"
        except sqlite3.IntegrityError:
            return False, "Ce contenu est déjà dans la base de données (doublon)."
        except sqlite3.Error as e:
            print(f"Une erreur SQLite est survenue : {e}")
            return False, "Erreur de base de données."

    def database_show(id_server, asker_id, DEV_ID):
        if asker_id != DEV_ID:
            return 1
        try:
            with sqlite3.connect(Database.PATH_DB) as con:
                cur = con.cursor()
                res = cur.execute("SELECT * FROM Alert WHERE id_server = ?", (id_server,)) # Les ? permette d'eviter une injection sql
                res = cur.fetchall()
                
                if not res:
                    return "Aucune donnée"
                filename = f"export_{id_server}.json"
                
                export_data = []
                for row in res:
                    export_data.append({
                        "id": row[0],
                        "id_server": row[1],
                        "name_server": row[2],
                        "message_content": row[3],
                        "message_author": row[4],
                        "message_author_id": row[5],
                        "deleter_name": row[6],
                        "deleter_id": row[7],
                        "image_hashes": row[8],
                        "deleted_at": row[9] if len(row) > 9 else None
                    })

                with open(filename, "w", encoding="utf-8") as f:
                    json.dump(export_data, f, indent=4, ensure_ascii=False)

                return filename

        except sqlite3.Error as e:
            print(f"Une erreur SQLite : {e}")
            return 1
        
    def database_lookup(id_server, message_content, attachment_hash):
        try:
                with sqlite3.connect(Database.PATH_DB) as con:
                    cur = con.cursor()
                    
                    # On ne récupère que ce qui nous intéresse pour gagner en performance
                    # Colonne 3: message_content | Colonne 8: image_hashes
                    cur.execute("SELECT message_content, image_hashes FROM Alert WHERE id_server = ?", (str(id_server),))
                    rows = cur.fetchall()

                    if not rows:
                        return False

                    for row in rows:
                        db_content = row[0]
                        db_hashes = row[1] # C'est notre chaîne "hash1,hash2..."

                        # 1. Vérification du contenu du message
                        # On ignore les messages vides pour éviter les faux positifs
                        if message_content and message_content.strip() != "":
                            if db_content == message_content:
                                print(f"Match trouvé sur le texte : {message_content}")
                                return True

                        # 2. Vérification du hash de l'image
                        if attachment_hash and db_hashes:
                            # On transforme la chaîne de la DB en liste pour comparer proprement
                            list_hashes_in_db = db_hashes.split(",")
                            if attachment_hash in list_hashes_in_db:
                                print(f"Match trouvé sur le hash d'image : {attachment_hash}")
                                return True

                    return False # Rien n'a été trouvé après avoir parcouru toute la DB

        except sqlite3.Error as e:
            print(f"Une erreur SQLite est survenue lors du lookup : {e}")
            return False
    
    def execute_query(command):
        try:
            with sqlite3.connect(Database.PATH_DB) as con:
                cur = con.cursor()
                cur.execute(command)
                
                if command.strip().upper().startswith("SELECT"):
                    res = cur.fetchall()
                    return True, res
                else:
                    # Pour UPDATE, INSERT, DELETE...
                    return True, f"Lignes affectées : {cur.rowcount}"
        except sqlite3.Error as e:
            return False, str(e)
        except Exception as e:
            return False, str(e)

class Utils:
    async def get_image_hash(attachment):
        try:
            data = await attachment.read()
            sha256_hash = hashlib.sha256(data).hexdigest()
            return sha256_hash
        except Exception as e:
            print(f"Impossible de hasher l'image : {e}")
            return None