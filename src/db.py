import os, sqlite3, hashlib, json, re
from datetime import datetime

class Database:
    PATH = os.path.dirname(os.path.abspath(__file__))
    PATH_DATA = os.path.join(PATH, "database")
    PATH_DB = os.path.join(PATH_DATA, "database.db")

    def check_database():

        if not os.path.exists(Database.PATH_DB): # Si le fichier database.db n'existe pas
            os.makedirs(Database.PATH_DATA) # Alors on crée le chemin vers celui ci 
            with open(Database.PATH_DB, 'w'):
                os.utime(Database.PATH_DB, None) # et on crée le fichier 
            
        Database.create_database(Database.PATH_DB) 
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
                
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS Members (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        guild_id TEXT NOT NULL,
                        user_id TEXT NOT NULL,
                        username TEXT NOT NULL,
                        display_name TEXT,
                        last_seen TEXT,
                        UNIQUE(guild_id, user_id)
                    )
                """)

                cur.execute("""
                    CREATE TABLE IF NOT EXISTS Bans (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        guild_id TEXT NOT NULL,
                        user_id TEXT NOT NULL,
                        username TEXT NOT NULL,
                        banned_by_name TEXT NOT NULL,
                        banned_by_id TEXT NOT NULL,
                        reason TEXT,
                        banned_at TEXT NOT NULL,
                        is_active INTEGER DEFAULT 1,
                        unbanned_by_name TEXT,
                        unbanned_by_id TEXT,
                        unbanned_at TEXT,
                        unban_reason TEXT
                    )
                """)

                # --- NOUVELLES TABLES DE LOGS UNIVERSELS ---
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS MessageLogs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        guild_id TEXT NOT NULL,
                        channel_id TEXT NOT NULL,
                        message_id TEXT NOT NULL,
                        author_id TEXT NOT NULL,
                        author_type TEXT NOT NULL,
                        action TEXT NOT NULL,
                        content TEXT,
                        old_content TEXT,
                        timestamp TEXT NOT NULL
                    )
                """)
                cur.execute("CREATE INDEX IF NOT EXISTS idx_msg_guild ON MessageLogs(guild_id)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_msg_author ON MessageLogs(author_id)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_msg_message ON MessageLogs(message_id)")

                cur.execute("""
                    CREATE TABLE IF NOT EXISTS ModerationLogs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        guild_id TEXT NOT NULL,
                        action_type TEXT NOT NULL,
                        target_id TEXT NOT NULL,
                        actor_id TEXT NOT NULL,
                        reason TEXT,
                        details TEXT,
                        timestamp TEXT NOT NULL
                    )
                """)
                cur.execute("CREATE INDEX IF NOT EXISTS idx_mod_guild ON ModerationLogs(guild_id)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_mod_target ON ModerationLogs(target_id)")

                cur.execute("""
                    CREATE TABLE IF NOT EXISTS GuildEntitiesLogs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        guild_id TEXT NOT NULL,
                        entity_type TEXT NOT NULL, -- 'ROLE' ou 'CHANNEL'
                        entity_id TEXT NOT NULL,
                        action TEXT NOT NULL, -- 'CREATE', 'UPDATE', 'DELETE'
                        name TEXT,
                        extra_data TEXT, -- JSON avec permissions, type, etc.
                        timestamp TEXT NOT NULL
                    )
                """)
                cur.execute("CREATE INDEX IF NOT EXISTS idx_entity_guild ON GuildEntitiesLogs(guild_id)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_entity_id ON GuildEntitiesLogs(entity_id)")

                cur.execute("""
                    CREATE TABLE IF NOT EXISTS MemberStateLogs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        guild_id TEXT NOT NULL,
                        user_id TEXT NOT NULL,
                        action TEXT NOT NULL, -- 'ROLE_ADD', 'ROLE_REMOVE', 'NICKNAME_CHANGE'
                        details TEXT,
                        timestamp TEXT NOT NULL
                    )
                """)
                cur.execute("CREATE INDEX IF NOT EXISTS idx_state_guild ON MemberStateLogs(guild_id)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_state_user ON MemberStateLogs(user_id)")

                cur.execute("""
                    CREATE TABLE IF NOT EXISTS UrlBanned (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        guild_id TEXT NOT NULL,
                        author_id TEXT NOT NULL,
                        moderator_id TEXT NOT NULL,
                        url TEXT,
                        timestamp TEXT NOT NULL,
                        UNIQUE(guild_id, url)
                    )
                """)

                # --- TABLES ROULETTE / TALENTS ---
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS RouletteSettings (
                        guild_id TEXT PRIMARY KEY,
                        max_roll INTEGER DEFAULT 19,
                        updated_at TEXT NOT NULL
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS RouletteTalents (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        guild_id TEXT NOT NULL,
                        number INTEGER NOT NULL,
                        name TEXT NOT NULL,
                        description TEXT NOT NULL,
                        role_id TEXT,
                        UNIQUE(guild_id, number)
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS RouletteHistory (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        guild_id TEXT NOT NULL,
                        user_id TEXT NOT NULL,
                        roll_value INTEGER NOT NULL,
                        talent_name TEXT,
                        timestamp TEXT NOT NULL
                    )
                """)
                cur.execute("CREATE INDEX IF NOT EXISTS idx_roulette_guild ON RouletteTalents(guild_id)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_roulette_hist_guild ON RouletteHistory(guild_id)")

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

    def urlbanned_show(guild_id, asker_id, DEV_ID):
        if asker_id != DEV_ID:
            return 1

        try:
            with sqlite3.connect(Database.PATH_DB) as con:
                cur = con.cursor()

                cur.execute(
                    "SELECT * FROM UrlBanned WHERE guild_id = ?",
                    (guild_id,)
                )
                res = cur.fetchall()

                if not res:
                    return "Aucune donnée"

                filename = f"urlbanned_export_{guild_id}.json"

                export_data = []
                for row in res:
                    export_data.append({
                        "id": row[0],
                        "guild_id": row[1],
                        "author_id": row[2],
                        "moderator_id": row[3],
                        "url": row[4],
                        "timestamp": row[5]
                    })

                with open(filename, "w", encoding="utf-8") as f:
                    json.dump(export_data, f, indent=4, ensure_ascii=False)

                return filename

        except sqlite3.Error as e:
            print(f"Une erreur SQLite : {e}")
            return 1

    def url_lookup(message):
        models = r'(https?://[^\s<>]+)' 
        resultats = re.findall(models, message)
        
        if resultats:
            with sqlite3.connect(Database.PATH_DB) as con:
                cur = con.cursor()
                # On vérifie chaque lien trouvé dans le message
                for url in resultats:
                    cur.execute("SELECT * FROM UrlBanned WHERE url = ?", (url,))
                    res = cur.fetchall()
                    if res:
                        # Dès qu'un seul lien du message est dans la DB, on retourne True
                        return True 
        return False
        
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


    def upsert_member(guild_id, user_id, username, display_name):
        try:
            with sqlite3.connect(Database.PATH_DB) as con:
                cur = con.cursor()
                cur.execute("""
                    INSERT INTO Members (guild_id, user_id, username, display_name, last_seen)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(guild_id, user_id) DO UPDATE SET
                        username = excluded.username,
                        display_name = excluded.display_name,
                        last_seen = excluded.last_seen
                """, (str(guild_id), str(user_id), username, display_name, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                con.commit()
                return True
        except sqlite3.Error as e:
            print(f"Erreur SQLite (upsert_member) : {e}")
            return False

    def search_members(guild_id, query):
        try:
            with sqlite3.connect(Database.PATH_DB) as con:
                con.row_factory = sqlite3.Row
                cur = con.cursor()
                if not query:
                    cur.execute("SELECT user_id, username, display_name FROM Members WHERE guild_id = ? LIMIT 25", (str(guild_id),))
                else:
                    cur.execute("""
                        SELECT user_id, username, display_name FROM Members 
                        WHERE guild_id = ? AND (username LIKE ? OR display_name LIKE ?) 
                        LIMIT 25
                    """, (str(guild_id), f"%{query}%", f"%{query}%"))
                return [dict(row) for row in cur.fetchall()]
        except sqlite3.Error as e:
            print(f"Erreur SQLite (search_members) : {e}")
            return []

    def search_banned_members(guild_id, query):
        try:
            with sqlite3.connect(Database.PATH_DB) as con:
                con.row_factory = sqlite3.Row
                cur = con.cursor()
                sql = """
                    SELECT Bans.user_id,
                           CASE WHEN Bans.username = 'Utilisateur Inconnu' AND Members.username IS NOT NULL THEN Members.username ELSE Bans.username END as username
                    FROM Bans
                    LEFT JOIN Members ON Bans.guild_id = Members.guild_id AND Bans.user_id = Members.user_id
                    WHERE Bans.guild_id = ? AND Bans.is_active = 1
                """
                if not query:
                    cur.execute(sql + " LIMIT 25", (str(guild_id),))
                else:
                    cur.execute(sql + " AND (Bans.username LIKE ? OR Members.username LIKE ?) LIMIT 25", (str(guild_id), f"%{query}%", f"%{query}%"))
                return [dict(row) for row in cur.fetchall()]
        except sqlite3.Error as e:
            print(f"Erreur SQLite (search_banned_members) : {e}")
            return []

    def add_ban(guild_id, user_id, username, banned_by_name, banned_by_id, reason):
        try:
            with sqlite3.connect(Database.PATH_DB) as con:
                cur = con.cursor()
                # Sécurité : Si un ban était resté actif par erreur dans la DB, on le désactive avant d'insérer le nouveau
                cur.execute("UPDATE Bans SET is_active = 0 WHERE guild_id = ? AND user_id = ? AND is_active = 1", (str(guild_id), str(user_id)))
                
                # System d'historique préservé
                cur.execute("""
                    INSERT INTO Bans (guild_id, user_id, username, banned_by_name, banned_by_id, reason, banned_at, is_active)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                """, (str(guild_id), str(user_id), username, banned_by_name, str(banned_by_id), reason, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                con.commit()
                return True
        except sqlite3.Error as e:
            print(f"Erreur SQLite (add_ban) : {e}")
            return False

    def remove_ban(guild_id, user_id, unbanned_by_name, unbanned_by_id, unban_reason):
        try:
            with sqlite3.connect(Database.PATH_DB) as con:
                cur = con.cursor()
                # On met à jour le ban actif en y ajoutant la raison du déban
                cur.execute("""
                    UPDATE Bans 
                    SET is_active = 0, unbanned_by_name = ?, unbanned_by_id = ?, unbanned_at = ?, unban_reason = ?
                    WHERE guild_id = ? AND user_id = ? AND is_active = 1
                """, (unbanned_by_name, str(unbanned_by_id), datetime.now().strftime("%Y-%m-%d %H:%M:%S"), unban_reason, str(guild_id), str(user_id)))
                con.commit()
                return cur.rowcount > 0
        except sqlite3.Error as e:
            print(f"Erreur SQLite (remove_ban) : {e}")
            return False
    
    def get_ban_info(guild_id, user_id):
        try:
            with sqlite3.connect(Database.PATH_DB) as con:
                con.row_factory = sqlite3.Row
                cur = con.cursor()
                cur.execute("""
                    SELECT Bans.user_id,
                           CASE WHEN Bans.username = 'Utilisateur Inconnu' AND Members.username IS NOT NULL THEN Members.username ELSE Bans.username END as username,
                           Bans.banned_by_name, Bans.banned_by_id, Bans.reason, Bans.banned_at
                    FROM Bans 
                    LEFT JOIN Members ON Bans.guild_id = Members.guild_id AND Bans.user_id = Members.user_id
                    WHERE Bans.guild_id = ? AND Bans.user_id = ? AND Bans.is_active = 1
                """, (str(guild_id), str(user_id)))
                row = cur.fetchone()
                return dict(row) if row else None
        except sqlite3.Error as e:
            print(f"Erreur SQLite (get_ban_info) : {e}")
            return None

    def get_all_active_bans(guild_id):
        try:
            with sqlite3.connect(Database.PATH_DB) as con:
                con.row_factory = sqlite3.Row
                cur = con.cursor()
                cur.execute("""
                    SELECT Bans.user_id,
                           CASE WHEN Bans.username = 'Utilisateur Inconnu' AND Members.username IS NOT NULL THEN Members.username ELSE Bans.username END as username,
                           Bans.reason, Bans.banned_at, Bans.banned_by_name 
                    FROM Bans 
                    LEFT JOIN Members ON Bans.guild_id = Members.guild_id AND Bans.user_id = Members.user_id
                    WHERE Bans.guild_id = ? AND Bans.is_active = 1
                    ORDER BY Bans.banned_at DESC
                """, (str(guild_id),))
                return [dict(row) for row in cur.fetchall()]
        except sqlite3.Error as e:
            print(f"Erreur SQLite (get_all_active_bans) : {e}")
            return []

    def get_user_history(guild_id, user_id):
        """Récupère TOUT l'historique des bans (actifs et passés) d'un utilisateur"""
        try:
            with sqlite3.connect(Database.PATH_DB) as con:
                con.row_factory = sqlite3.Row
                cur = con.cursor()
                cur.execute("""
                    SELECT Bans.*,
                           CASE WHEN Bans.username = 'Utilisateur Inconnu' AND Members.username IS NOT NULL THEN Members.username ELSE Bans.username END as real_username
                    FROM Bans
                    LEFT JOIN Members ON Bans.guild_id = Members.guild_id AND Bans.user_id = Members.user_id
                    WHERE Bans.guild_id = ? AND Bans.user_id = ?
                    ORDER BY Bans.banned_at DESC
                """, (str(guild_id), str(user_id)))
                return [dict(row) for row in cur.fetchall()]
        except sqlite3.Error as e:
            print(f"Erreur SQLite (get_user_history) : {e}")
            return []

    # --- LOGGING METHODS ---
    def log_message(guild_id, channel_id, message_id, author_id, author_type, action, content, old_content=None):
        try:
            with sqlite3.connect(Database.PATH_DB) as con:
                cur = con.cursor()
                cur.execute("""
                    INSERT INTO MessageLogs (guild_id, channel_id, message_id, author_id, author_type, action, content, old_content, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (str(guild_id), str(channel_id), str(message_id), str(author_id), author_type, action, content, old_content, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                con.commit()
        except sqlite3.Error as e:
            print(f"Erreur SQLite (log_message) : {e}")

    def log_moderation(guild_id, action_type, target_id, actor_id, reason, details=""):
        try:
            with sqlite3.connect(Database.PATH_DB) as con:
                cur = con.cursor()
                cur.execute("""
                    INSERT INTO ModerationLogs (guild_id, action_type, target_id, actor_id, reason, details, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (str(guild_id), action_type, str(target_id), str(actor_id), reason, details, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                con.commit()
        except sqlite3.Error as e:
            print(f"Erreur SQLite (log_moderation) : {e}")

    def log_guild_entity(guild_id, entity_type, entity_id, action, name, extra_data=""):
        try:
            with sqlite3.connect(Database.PATH_DB) as con:
                cur = con.cursor()
                cur.execute("""
                    INSERT INTO GuildEntitiesLogs (guild_id, entity_type, entity_id, action, name, extra_data, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (str(guild_id), entity_type, str(entity_id), action, name, extra_data, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                con.commit()
        except sqlite3.Error as e:
            print(f"Erreur SQLite (log_guild_entity) : {e}")

    def log_member_state(guild_id, user_id, action, details=""):
        try:
            with sqlite3.connect(Database.PATH_DB) as con:
                cur = con.cursor()
                cur.execute("""
                    INSERT INTO MemberStateLogs (guild_id, user_id, action, details, timestamp)
                    VALUES (?, ?, ?, ?, ?)
                """, (str(guild_id), str(user_id), action, details, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                con.commit()
        except sqlite3.Error as e:
            print(f"Erreur SQLite (log_member_state) : {e}")

    def get_user_full_report(guild_id, user_id):
        # Récupère tous les logs pour un user_id donné
        try:
            report = {}
            with sqlite3.connect(Database.PATH_DB) as con:
                con.row_factory = sqlite3.Row
                cur = con.cursor()
                
                # Member info
                cur.execute("SELECT * FROM Members WHERE guild_id = ? AND user_id = ?", (str(guild_id), str(user_id)))
                member = cur.fetchone()
                report['member_info'] = dict(member) if member else None
                
                # Messages limités pour ne pas faire crash
                cur.execute("SELECT * FROM MessageLogs WHERE guild_id = ? AND author_id = ? ORDER BY timestamp DESC LIMIT 500", (str(guild_id), str(user_id)))
                report['recent_messages'] = [dict(row) for row in cur.fetchall()]
                
                # Moderation (as target)
                cur.execute("SELECT * FROM ModerationLogs WHERE guild_id = ? AND target_id = ? ORDER BY timestamp DESC", (str(guild_id), str(user_id)))
                report['moderation_history'] = [dict(row) for row in cur.fetchall()]

                # Moderation (as actor)
                cur.execute("SELECT * FROM ModerationLogs WHERE guild_id = ? AND actor_id = ? ORDER BY timestamp DESC", (str(guild_id), str(user_id)))
                report['actions_performed'] = [dict(row) for row in cur.fetchall()]

                # State changes
                cur.execute("SELECT * FROM MemberStateLogs WHERE guild_id = ? AND user_id = ? ORDER BY timestamp DESC", (str(guild_id), str(user_id)))
                report['state_changes'] = [dict(row) for row in cur.fetchall()]

                return report
        except sqlite3.Error as e:
            print(f"Erreur SQLite (get_user_full_report) : {e}")
            return None

    def ban_url(guild_id, author_id, moderator_id, url):
        try:
            with sqlite3.connect(Database.PATH_DB) as con:
                cur = con.cursor()
                cur.execute("""INSERT OR IGNORE INTO UrlBanned (guild_id, author_id, moderator_id, url, timestamp) VALUES (?, ?, ?, ?, ?)""", 
                            (str(guild_id), str(author_id), moderator_id, url, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                con.commit()
                return True, "Url bien archivé"
        except sqlite3.Error as e:
                    print(f"Erreur SQLite (log_member_state) : {e}")

    # --- MÉTHODES ROULETTE & TALENTS ---
    DEFAULT_TALENTS = [
        (1, "💪 Force décuplée", "Vous êtes très endurant et avez des muscles capables de soulever une bonne centaine de kilos à bout de bras même si votre carrure ne semble pas vous en donner les capacités. Attention lorsque vous serrez la main aux autres personnes de l'académie."),
        (2, "🥀 Système immunitaire renforcé", "Vous êtes totalement insensible aux poisons. Vous ne tombez jamais malade."),
        (3, "🔥 Berserk", "Plus vous êtes en mauvais état physique et plus vos pouvoirs augmentent, pouvant jusqu'à doubler s'il vous manque plusieurs membres. Votre détermination vous permet de faire face à l'adversité avec plus de courage que la majorité des autres personnes de votre grade. N'oubliez cependant pas que vous n'êtes pas immortel, et que des blessures graves peuvent entraîner votre décès."),
        (4, "🦥 Sans talent", "Vous n'avez hélas pas de talent particulier. Vous pouvez toujours essayer d'implorer les fondateurs. (Ça ne hard carry pas, ne vous en faites pas !)"),
        (5, "🛜 Transmission de pensées", "Vous avez la capacité de communiquer par télépathie avec les personnes de votre choix qui se situent à moins de 50 mètres de vous, mais pas à plus de trois autres personnes à la fois. Ce talent ne sert qu'à envoyer des pensées, pas à en recevoir ou en écouter."),
        (6, "⌛ Maîtrise économe", "Vous avez deux points de DAG supplémentaire, ce qui vous permet d'utiliser vos pouvoirs plus longtemps."),
        (7, "👄 Mégapolyglotte", "Vous avez la capacité de parler et comprendre n'importe quelle langue de façon purement instinctive, y compris celle des animaux."),
        (8, "🐾 Familier inné", "Vous êtes en capacité d'invoquer un familier lorsque vous le souhaitez. Les familiers ne peuvent pas être humains. Pensez à l'ajouter à votre fiche et à le faire valider."),
        (9, "👻 Invisibilité discrète", "Tant que vous retenez votre souffle, vous êtes invisible (mais pas vos habits). Qu'allez-vous faire de ce talent ?"),
        (10, "🗡 Invocation d'objet", "Vous êtes en capacité de faire apparaître ou disparaître un seul et unique objet. Pensez à le mettre dans votre fiche et à le faire valider."),
        (11, "🌀 Respiration augmentée", "Vous pouvez cependant rester sous l'eau une trentaine de minutes sans respirer et vous mouvoir sans consommer plus d'oxygène que si vous étiez immobile. Cette capacité vous donne également un très bon souffle sur terre."),
        (12, "✋ Toucher augmenté", "Ce talent vous permet de ressentir aisément les vibrations des choses que vous touchez comme celles du sol. Il vous procure aussi de façon général un meilleur toucher."),
        (13, "📏 Élasticité", "Vos cinq membres ont la faculté de s'allonger légèrement (d'une quarantaine de centimètres), ce qui vous permet d'avoir plus d'allonge sans toutefois influer sur vos capacités physiques."),
        (14, "🍀 Lucky Luke", "Hola cowboy ! Vous êtes naturellement très chanceux. Lorsque vous effectuez un roll inrp ou pour obtenir un talent, vous pouvez le faire deux fois et choisir le résultat que vous préférez (celui-ci ne compte pas, il vous est attribué de suite)."),
        (15, "🐙 Agilité boostée", "Votre souplesse, votre vitesse et votre agilité sont hors du commun. Les personnes de votre grade ou moins ont énormément de mal à suivre vos mouvements. Vous vous déplacez à une vitesse impressionnante et pouvez effectuer les acrobaties les plus improbables sans mal."),
        (16, "🐰 Ouïe amplifiée", "Ce talent vous permet d'entendre bien plus aisément les bruits qui vous entourent et vous permet également de les distinguer les uns des autres. Cela veut dire que vous pouvez, par exemple, entendre des sons provenant de plus loin. En revanche, ce talent est accompagné d'une plus grande vulnérabilité aux bruits forts."),
        (17, "👀 Vision accrue", "Vos yeux ont une facilité déconcertante à suivre les mouvements des autres en plus d'avoir une acuité d'environ 25/10."),
        (18, "🐘 Sniffeur", "Votre odorat est surdéveloppé, vous permettant d'identifier très facilement une personne à son odeur et de différencier les odeurs qui vous entourent. Vous pouvez également sentir des odeurs moins concentrées dans l'air."),
        (19, "⚡ Hacker", "Vous possédez des compétences informatiques hors du commun.")
    ]

    def get_roulette_max_roll(guild_id):
        try:
            with sqlite3.connect(Database.PATH_DB) as con:
                cur = con.cursor()
                cur.execute("SELECT max_roll FROM RouletteSettings WHERE guild_id = ?", (str(guild_id),))
                row = cur.fetchone()
                return row[0] if row else 19
        except sqlite3.Error as e:
            print(f"Erreur SQLite (get_roulette_max_roll) : {e}")
            return 19

    def set_roulette_max_roll(guild_id, max_roll):
        try:
            with sqlite3.connect(Database.PATH_DB) as con:
                cur = con.cursor()
                cur.execute("""
                    INSERT INTO RouletteSettings (guild_id, max_roll, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(guild_id) DO UPDATE SET
                        max_roll = excluded.max_roll,
                        updated_at = excluded.updated_at
                """, (str(guild_id), int(max_roll), datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                con.commit()
                return True
        except sqlite3.Error as e:
            print(f"Erreur SQLite (set_roulette_max_roll) : {e}")
            return False

    def get_talent(guild_id, number):
        try:
            with sqlite3.connect(Database.PATH_DB) as con:
                con.row_factory = sqlite3.Row
                cur = con.cursor()
                cur.execute("SELECT * FROM RouletteTalents WHERE guild_id = ? AND number = ?", (str(guild_id), int(number)))
                row = cur.fetchone()
                return dict(row) if row else None
        except sqlite3.Error as e:
            print(f"Erreur SQLite (get_talent) : {e}")
            return None

    def get_all_talents(guild_id):
        try:
            with sqlite3.connect(Database.PATH_DB) as con:
                con.row_factory = sqlite3.Row
                cur = con.cursor()
                cur.execute("SELECT * FROM RouletteTalents WHERE guild_id = ? ORDER BY number ASC", (str(guild_id),))
                return [dict(row) for row in cur.fetchall()]
        except sqlite3.Error as e:
            print(f"Erreur SQLite (get_all_talents) : {e}")
            return []

    def set_talent(guild_id, number, name, description, role_id=None):
        try:
            with sqlite3.connect(Database.PATH_DB) as con:
                cur = con.cursor()
                role_id_str = str(role_id) if role_id else None
                cur.execute("""
                    INSERT INTO RouletteTalents (guild_id, number, name, description, role_id)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(guild_id, number) DO UPDATE SET
                        name = excluded.name,
                        description = excluded.description,
                        role_id = excluded.role_id
                """, (str(guild_id), int(number), name, description, role_id_str))
                con.commit()
                return True
        except sqlite3.Error as e:
            print(f"Erreur SQLite (set_talent) : {e}")
            return False

    def delete_talent(guild_id, number):
        try:
            with sqlite3.connect(Database.PATH_DB) as con:
                cur = con.cursor()
                cur.execute("DELETE FROM RouletteTalents WHERE guild_id = ? AND number = ?", (str(guild_id), int(number)))
                con.commit()
                return cur.rowcount > 0
        except sqlite3.Error as e:
            print(f"Erreur SQLite (delete_talent) : {e}")
            return False

    def init_default_talents(guild_id):
        try:
            with sqlite3.connect(Database.PATH_DB) as con:
                cur = con.cursor()
                # Configurer max_roll à 19
                cur.execute("""
                    INSERT INTO RouletteSettings (guild_id, max_roll, updated_at)
                    VALUES (?, 19, ?)
                    ON CONFLICT(guild_id) DO UPDATE SET
                        max_roll = 19,
                        updated_at = excluded.updated_at
                """, (str(guild_id), datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                
                # Inserer/Mettre à jour les 19 talents par défaut
                for num, name, desc in Database.DEFAULT_TALENTS:
                    cur.execute("""
                        INSERT INTO RouletteTalents (guild_id, number, name, description, role_id)
                        VALUES (?, ?, ?, ?, NULL)
                        ON CONFLICT(guild_id, number) DO UPDATE SET
                            name = excluded.name,
                            description = excluded.description
                    """, (str(guild_id), num, name, desc))
                con.commit()
                return True
        except sqlite3.Error as e:
            print(f"Erreur SQLite (init_default_talents) : {e}")
            return False

    def log_roulette_roll(guild_id, user_id, roll_value, talent_name):
        try:
            with sqlite3.connect(Database.PATH_DB) as con:
                cur = con.cursor()
                cur.execute("""
                    INSERT INTO RouletteHistory (guild_id, user_id, roll_value, talent_name, timestamp)
                    VALUES (?, ?, ?, ?, ?)
                """, (str(guild_id), str(user_id), int(roll_value), talent_name, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                con.commit()
                return True
        except sqlite3.Error as e:
            print(f"Erreur SQLite (log_roulette_roll) : {e}")
            return False

class Utils:
    async def get_image_hash(attachment):
        try:
            data = await attachment.read()
            sha256_hash = hashlib.sha256(data).hexdigest()
            return sha256_hash
        except Exception as e:
            print(f"Impossible de hasher l'image : {e}")
            return None