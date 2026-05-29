from src.db import Database, Utils
from src.music import Music
from src.BanListPagination import BanListPagination
import discord, os, subprocess, json, asyncio, re
from dotenv import load_dotenv
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone, timedelta
import random

load_dotenv()
TOKEN = os.getenv('TOKEN')
DEV_GUILD_ID = os.getenv('DEV_GUILD_ID')
DEV_ID = int(os.getenv('DEV_ID'))
Database.check_database()

# Configuration du bot
intents = discord.Intents.all()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    subprocess.run('cls', shell=True)  # Efface la console (Windows uniquement)
    print(f"{bot.user} est Réveillé !\n")
    print(f"ID du serveur configuré : {DEV_GUILD_ID}")

    try:
        synced = await bot.tree.sync()
        print("Mise à jour du registre interne des membres...")
        for guild in bot.guilds:
            if not guild.chunked:
                try:
                    await guild.chunk()
                except:
                    pass
            for member in guild.members:
                Database.upsert_member(guild.id, member.id, member.name, member.display_name)
        print("Registre interne des membres initialisé avec succès !\n")
        print(f"Synced {len(synced)} command(s) synchroniser")
    except Exception as e:
        print(f"Erreur lors de la synchronisation des commandes : {e}")

@bot.event
async def on_member_join(member):
    # Dès qu'un utilisateur rejoint, on l'indexe dans la DB
    Database.upsert_member(member.guild.id, member.id, member.name, member.display_name)

@bot.event
async def on_member_update(before, after):
    # Si quelqu'un change de pseudo ou de surnom, on met à jour la DB
    if before.name != after.name or before.display_name != after.display_name:
        Database.upsert_member(after.guild.id, after.id, after.name, after.display_name)

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        if not interaction.response.is_done():
            await interaction.response.send_message("Vous n'avez pas les permissions nécessaires pour utiliser cette commande.", ephemeral=True)
    else:
        print(f"Erreur d'application : {error}")
        if not interaction.response.is_done():
            await interaction.response.send_message("Une erreur est survenue lors de l'exécution de la commande.", ephemeral=True)

@bot.event
async def on_message(message):
    if message.author == bot.user or message.webhook_id is not None:
        return

    # Calcul du hash si il y a une ou plusieurs images
    current_hash = None
    if message.attachments:
        attachment = message.attachments[0]
        if attachment.content_type and attachment.content_type.startswith('image/'):
            current_hash = await Utils.get_image_hash(attachment)

    # Vérification dans la db
    already_banned = Database.database_lookup(message.guild.id, message.content, current_hash)

    if already_banned:
        try:
            with open("config.json", "r") as f:
                config = json.load(f)
            
            serv_id = str(message.guild.id)
            
            if serv_id in config:
                conf = config[serv_id]
                target_channel = bot.get_channel(conf["channel_id"])
                role_ping = f"<@&{conf['role_id']}>"

                if target_channel:
                    jump_link = message.jump_url
                    await target_channel.send(
                        f"{role_ping} **Contenue déjà supprimé**\n"
                        f"**Auteur :** {message.author.mention} (`{message.author.id}`)\n"
                        f"**Salon :** {message.channel.mention}\n"
                        f"**Action :** [Cliquer ici pour voir le message]({jump_link})"
                    )
                else:
                    print("Erreur : Le channel ID dans le JSON est introuvable.")
            else:
                print(f"Le serveur {serv_id} n'est pas configuré dans le JSON.")
        
        except Exception as e:
            print(f"Erreur lors de l'envoi de l'alerte config : {e}")

    await bot.process_commands(message)

@bot.tree.context_menu(name="Bannir et Supprimer")
@app_commands.checks.has_permissions(manage_messages=True)
async def ban_and_delete(interaction: discord.Interaction, message: discord.Message):
    # On calcule les hash si images
    hashes_found = []
    for attachment in message.attachments:
        if attachment.content_type and attachment.content_type.startswith('image/'):
            try:
                file_hash = await Utils.get_image_hash(attachment)
                hashes_found.append(file_hash)
            except:
                continue

    str_hashes = ",".join(hashes_found) if hashes_found else ""

    # Ajout à la base de données
    success, msg = Database.database_incrementation(
        interaction.guild.id,
        interaction.guild.name,
        message.content,
        message.author.name,
        message.author.id,
        interaction.user.name,
        interaction.user.id,
        str_hashes,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )
    
    # Suppression du message
    try:
        await message.delete()
        if success:
            await interaction.response.send_message(f"Le message de {message.author.mention} a été supprimé et ajouté à la base de données.", ephemeral=True)
        else:
            await interaction.response.send_message(f"Le message de {message.author.mention} a été supprimé, mais non ajouté à la db : {msg}", ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message(f"Le message a été ajouté (Status: {msg}) mais je n'ai pas la permission de le supprimer.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Erreur lors de la suppression : {e}", ephemeral=True)

@bot.tree.command(name="ban_texte", description="Ajoute manuellement un texte à la base de données des messages interdits")
@app_commands.describe(texte="Le texte à bannir")
@app_commands.checks.has_permissions(manage_messages=True)
async def ban_texte(interaction: discord.Interaction, texte: str):
    success, msg = Database.database_incrementation(
        interaction.guild.id,
        interaction.guild.name,
        texte,
        "Ajout Manuel",
        "0",
        interaction.user.name,
        interaction.user.id,
        "",
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )
    if success:
        await interaction.response.send_message("Le texte a été ajouté à la base de données des messages interdits.", ephemeral=True)
    else:
        await interaction.response.send_message(f"Impossible d'ajouter : {msg}", ephemeral=True)

@bot.tree.command(
    name="hello",
    description="Petit bonjour de Fern",
)
async def hello(interaction: discord.Interaction, member: discord.Member):
    if member is None:
        await interaction.response.send_message("Veuillez mentionner un membre valide.", ephemeral=True)
        return
    await interaction.response.send_message(f"Hello {member.mention} :kiss:")

@bot.tree.command(
    name="logdata",
    description="Recupère les log des messages suprimer sur le server ou la commande est executé si autorisé",
)
async def logdata(interaction: discord.Interaction):
    if interaction.user.id != DEV_ID:
        return await interaction.response.send_message("Vous n'avez pas les permissions pour executer cette commande", ephemeral=True)

    await interaction.response.defer(thinking=True, ephemeral=True)
    filename = Database.database_show(interaction.guild.id, interaction.user.id, DEV_ID)

    if isinstance(filename, str) and os.path.exists(filename):
        await interaction.followup.send(
            content="Voici l'export de toutes les alertes :", 
            file=discord.File(filename)
        )
        os.remove(filename)
    
    else:
        error_msg = "Accès refusé ou aucune donnée trouvée."
        await interaction.followup.send(error_msg)

@bot.tree.command(
    name="setup_alerts", 
    description="Configure le salon et le rôle pour les alertes de modération"
)
@app_commands.describe(
    channel="Le salon où envoyer les alertes", 
    role="Le rôle à mentionner (ping)"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def setup_alerts(interaction: discord.Interaction, channel: discord.TextChannel, role: discord.Role):
    config_file = "config.json"
    
    data = {}
    if os.path.exists(config_file):
        with open(config_file, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                data = {}

    guild_id = str(interaction.guild.id)
    if guild_id not in data:
        data[guild_id] = {}
        
    data[guild_id]["channel_id"] = channel.id
    data[guild_id]["role_id"] = role.id

    try:
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        
        await interaction.response.send_message(
            f"**Configuration réussie !**\n"
            f"• Salon : {channel.mention}\n"
            f"• Rôle notifié : {role.mention}\n"
            f"Désormais, tous contenue déjà banni sera signalée ici.",
            ephemeral=True
        )

    except Exception as e:
        await interaction.response.send_message(f"Erreur lors de l'écriture du fichier : {e}", ephemeral=True)

@bot.tree.command(name="play", description="Joue une musique depuis YouTube")
async def play(interaction: discord.Interaction, url: str):
    member = interaction.user

    # Vérification du salon vocal
    if not member.voice or not member.voice.channel:
        return await interaction.response.send_message(
            "Tu dois être dans un salon vocal", 
            ephemeral=True
        )

    # On "diffère" la réponse car le téléchargement peut prendre plus de 3 secondes
    await interaction.response.defer()

    vocal_channel = member.voice.channel
    vc = interaction.guild.voice_client

    # Connexion ou déplacement
    if vc:
        if vc.channel != vocal_channel:
            await vc.move_to(vocal_channel)
    else:
        vc = await vocal_channel.connect()

    try:
        title, file_path = await Music.download(url)

        # Lecture de l'audio
        if vc.is_playing():
            vc.stop()
        
        def after_playing(error):
            if error:
                print(f"Erreur lors de la lecture : {error}")
            
            # On vérifie si le fichier existe et on le supprime
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    print(f"Fichier supprimé : {file_path}")
                except Exception as e:
                    print(f"Impossible de supprimer le fichier : {e}")

        vc.play(discord.FFmpegPCMAudio(file_path), after=after_playing)
        
        await interaction.followup.send(f"En train de jouer : **{title}**")

    except Exception as e:
        print(f"Erreur: {e}")
        await interaction.followup.send("Une erreur est survenue lors du téléchargement.")

@bot.tree.command(name="stop", description="Déconnecte le bot proprement")
async def stop(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    
    if not vc:
        return await interaction.response.send_message("Je ne suis pas connecté à un salon vocal.", ephemeral=True)

    try:
        await interaction.response.send_message("Déconnexion en cours...")

        if vc.is_playing() or vc.is_paused():
            vc.stop()

        path_to_clean = getattr(vc, "current_file", None)

        await vc.disconnect()

        if path_to_clean and os.path.exists(path_to_clean):
            await asyncio.sleep(0.5)
            try:
                os.remove(path_to_clean)
                print(f"Fichier nettoyé : {path_to_clean}")
            except Exception as e:
                print(f"Erreur nettoyage : {e}")

    except Exception as e:
        print(f"Erreur lors du stop : {e}")

        if not interaction.response.is_done():
            await interaction.response.send_message("Une erreur est survenue lors de la déconnexion.")

@bot.tree.command(
    name="sql", 
    description="permet l'execution des commande sql directement depuis discord"
)
@app_commands.describe(
    command="command sql"
)
async def sql(interaction: discord.Interaction, command: str):
    if interaction.user.id == DEV_ID:
        success, result = Database.execute_query(command)
        if success:
            if isinstance(result, list):
                if not result:
                    msg = "Aucun résultat."
                else:
                    msg = "\n".join(str(row) for row in result)
            else:
                msg = str(result)
                
            response_text = f"**Commande exécutée avec succès :**\n```\n{msg}\n```"
            if len(response_text) > 2000:
                response_text = response_text[:1990] + "...\n```"
                
            await interaction.response.send_message(response_text)
        else:
            await interaction.response.send_message(f"**Erreur SQL :**\n```\n{result}\n```")
    else:
        return await interaction.response.send_message("Vous n'avez pas les permissions pour executer cette commande", ephemeral=True)

@bot.tree.command(
    name="champignon_setup",
    description="Configure les rôles pour la loterie champignon"
)
@app_commands.describe(
    role_cible="Le rôle parmi lequel tirer au sort",
    role_recompense="Le rôle à donner a la personne tirer au sort"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def champ_setup(interaction: discord.Interaction, role_cible: discord.Role, role_recompense: discord.Role):
    config_file = "config.json"
    data = {}
    if os.path.exists(config_file):
        with open(config_file, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                data = {}
    
    guild_id = str(interaction.guild.id)
    if guild_id not in data:
        data[guild_id] = {}
        
    data[guild_id]["champignon_role_cible_id"] = role_cible.id
    data[guild_id]["champignon_role_recompense_id"] = role_recompense.id

    try:
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        
        await interaction.response.send_message(
            f"✅ Configuration réussie :\n"
            f"• Rôle ciblé : {role_cible.mention}\n"
            f"• Rôle récompense : {role_recompense.mention}",
            ephemeral=True
        )
    except Exception as e:
        await interaction.response.send_message(f"Erreur lors de l'écriture du fichier : {e}", ephemeral=True)

@bot.tree.command(
    name="champignon",
    description="Tire au sort un membre et lui donne le rôle récompense"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def champignon(interaction: discord.Interaction):
    config_file = "config.json"
    if not os.path.exists(config_file):
        return await interaction.response.send_message("Le bot n'est pas encore configuré sur ce serveur.", ephemeral=True)
        
    with open(config_file, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            data = {}
            
    guild_id = str(interaction.guild.id)
    if guild_id not in data or "champignon_role_cible_id" not in data[guild_id] or "champignon_role_recompense_id" not in data[guild_id]:
        return await interaction.response.send_message("Les rôles champignon ne sont pas configurés. Utilisez `/champignon_setup`.", ephemeral=True)
        
    role_cible_id = data[guild_id]["champignon_role_cible_id"]
    role_recompense_id = data[guild_id]["champignon_role_recompense_id"]
    
    role_cible = interaction.guild.get_role(role_cible_id)
    role_recompense = interaction.guild.get_role(role_recompense_id)
    
    if not role_cible or not role_recompense:
        return await interaction.response.send_message("L'un des rôles configurés n'existe plus sur le serveur.", ephemeral=True)
        
    members_with_role = role_cible.members
    if not members_with_role:
        return await interaction.response.send_message(f"Aucun membre ne possède le rôle {role_cible.name}.", ephemeral=True)
        
    winner = random.choice(members_with_role)
    
    try:
        await winner.add_roles(role_recompense)
        await interaction.response.send_message(f"Le grand gagnant est {winner.mention} ! Il a reçu le rôle {role_recompense.mention}.")
    except discord.Forbidden:
        await interaction.response.send_message(f"Le grand gagnant est {winner.mention} ! Erreur : Je n'ai pas les permissions pour lui donner le rôle {role_recompense.name}.")
    except Exception as e:
        await interaction.response.send_message(f"Le grand gagnant est {winner.mention} ! Erreur lors de l'ajout du rôle : {e}")

@bot.tree.command(
    name="roulette_setup",
    description="Configure le rôle pour la commande roulette"
)
@app_commands.describe(
    role_cible="Le rôle parmi lequel tirer au sort"
)
@app_commands.checks.has_permissions(manage_messages=True)
async def roulette_setup(interaction: discord.Interaction, role_cible: discord.Role):
    config_file = "config.json"
    data = {}
    if os.path.exists(config_file):
        with open(config_file, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                data = {}
    
    guild_id = str(interaction.guild.id)
    if guild_id not in data:
        data[guild_id] = {}
        
    data[guild_id]["roulette_role_cible_id"] = role_cible.id

    try:
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        
        await interaction.response.send_message(
            f"Configuration de la roulette réussie :\n"
            f"• Rôle ciblé : {role_cible.mention}",
            ephemeral=True
        )
    except Exception as e:
        await interaction.response.send_message(f"Erreur lors de l'écriture du fichier : {e}", ephemeral=True)

@bot.tree.command(
    name="roulette",
    description="Tire au sort un membre ayant le rôle configuré et le mentionne"
)
@app_commands.checks.has_permissions(manage_messages=True)
async def roulette(interaction: discord.Interaction):
    config_file = "config.json"
    if not os.path.exists(config_file):
        return await interaction.response.send_message("Le bot n'est pas encore configuré sur ce serveur.", ephemeral=True)
        
    with open(config_file, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            data = {}
            
    guild_id = str(interaction.guild.id)
    if guild_id not in data or "roulette_role_cible_id" not in data[guild_id]:
        return await interaction.response.send_message("Le rôle pour la roulette n'est pas configuré. Utilisez `/roulette_setup`.", ephemeral=True)
        
    role_cible_id = data[guild_id]["roulette_role_cible_id"]
    
    role_cible = interaction.guild.get_role(role_cible_id)
    
    if not role_cible:
        return await interaction.response.send_message("Le rôle configuré n'existe plus sur le serveur.", ephemeral=True)
        
    members_with_role = role_cible.members
    if not members_with_role:
        return await interaction.response.send_message(f"Aucun membre ne possède le rôle {role_cible.name}.", ephemeral=True)
        
    winner = random.choice(members_with_role)
    
    await interaction.response.send_message(f"La roulette a tourné... et s'arrête sur {winner.mention} !")

# --- CONFIGURATION DES AUTOCOMPLETES ---
async def ban_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    members = Database.search_members(interaction.guild.id, current)
    return [
        app_commands.Choice(
            name=f"{m['display_name'] or m['username']} ({m['username']}) — ID: {m['user_id']}", 
            value=str(m['user_id'])
        )
        for m in members
    ][:25]

async def unban_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    banned_members = Database.search_banned_members(interaction.guild.id, current)
    return [
        app_commands.Choice(
            name=f"{m['username']} — ID: {m['user_id']}", 
            value=str(m['user_id'])
        )
        for m in banned_members
    ][:25]

@bot.tree.command(name="ban", description="Bannir un membre (présent ou ayant quitté le serveur).")
@app_commands.autocomplete(user_id=ban_autocomplete)
@app_commands.describe(user_id="Le membre ou l'ID à bannir", reason="Raison du bannissement")
@app_commands.checks.has_permissions(ban_members=True)
async def ban_member(interaction: discord.Interaction, user_id: str, reason: str = "Aucune raison fournie"):
    await interaction.response.defer()
    try:
        user = await bot.fetch_user(int(user_id))
        await interaction.guild.ban(user, reason=reason)
        
        db_members = Database.search_members(interaction.guild.id, user_id)
        db_member = next((m for m in db_members if str(m['user_id']) == str(user_id)), None)
        username = db_member['username'] if db_member else user.name

        Database.add_ban(
            guild_id=interaction.guild.id,
            user_id=user_id,
            username=username,
            banned_by_name=interaction.user.name,
            banned_by_id=interaction.user.id,
            reason=reason
        )
        
        embed = discord.Embed(title="Membre Banni", color=discord.Color.red(), timestamp=datetime.now())
        if user.display_avatar:
            embed.set_thumbnail(url=user.display_avatar.url)
        embed.add_field(name="Utilisateur", value=f"{user.mention} (`{user.name}`)", inline=True)
        embed.add_field(name="ID", value=f"`{user_id}`", inline=True)
        embed.add_field(name="Modérateur", value=interaction.user.mention, inline=False)
        embed.add_field(name="Raison", value=f"*{reason}*", inline=False)
        
        await interaction.followup.send(embed=embed)
        
    except discord.Forbidden:
        await interaction.followup.send("Je n'ai pas les permissions nécessaires pour bannir cet utilisateur.", ephemeral=True)
    except (discord.NotFound, ValueError):
        await interaction.followup.send("Impossible de trouver cet utilisateur sur Discord.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"Une erreur est survenue : {e}", ephemeral=True)


@bot.tree.command(name="unban", description="Débannir un membre via la base de données ou son ID.")
@app_commands.autocomplete(user_id=unban_autocomplete)
@app_commands.describe(user_id="Le membre banni ou son ID", reason="Raison du débannissement")
@app_commands.checks.has_permissions(ban_members=True)
async def unban_member(interaction: discord.Interaction, user_id: str, reason: str = "Aucune raison fournie"):
    await interaction.response.defer()
    try:
        user = await bot.fetch_user(int(user_id))
        await interaction.guild.unban(user, reason=reason)
        
        # Transmission de la raison du déban à la base de données
        success = Database.remove_ban(
            guild_id=interaction.guild.id,
            user_id=user_id,
            unbanned_by_name=interaction.user.name,
            unbanned_by_id=interaction.user.id,
            unban_reason=reason
        )
        
        embed = discord.Embed(title="Membre Débanni", color=discord.Color.green(), timestamp=datetime.now())
        if user.display_avatar:
            embed.set_thumbnail(url=user.display_avatar.url)
        embed.add_field(name="Utilisateur", value=f"{user.mention} (`{user.name}`)", inline=True)
        embed.add_field(name="ID", value=f"`{user_id}`", inline=True)
        embed.add_field(name="Modérateur", value=interaction.user.mention, inline=False)
        embed.add_field(name="Raison du déban", value=f"*{reason}*", inline=False)
        
        if not success:
            embed.set_footer(text="Note: Ce ban n'était pas actif dans le registre persistant.")
            
        await interaction.followup.send(embed=embed)
        
    except discord.NotFound:
        await interaction.followup.send("Cet utilisateur n'est pas banni de ce serveur.", ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send("Je n'ai pas la permission de débannir des membres.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"Une erreur est survenue : {e}", ephemeral=True)


@bot.tree.command(name="ban_list", description="Afficher la liste des membres actuellement bannis.")
@app_commands.checks.has_permissions(ban_members=True)
async def ban_list(interaction: discord.Interaction):
    bans = Database.get_all_active_bans(interaction.guild.id)
    view = BanListPagination(bans, per_page=5)
    await interaction.response.send_message(embed=view.get_embed(), view=view)


@bot.tree.command(name="ban_info", description="Voir les détails et la raison du bannissement d'un membre.")
@app_commands.autocomplete(user_id=unban_autocomplete)
@app_commands.describe(user_id="Le membre banni")
@app_commands.checks.has_permissions(ban_members=True)
async def ban_info(interaction: discord.Interaction, user_id: str):
    ban = Database.get_ban_info(interaction.guild.id, user_id)
    if not ban:
        return await interaction.response.send_message("Aucune information trouvée dans la base de données.", ephemeral=True)
    
    try:
        user = await bot.fetch_user(int(user_id))
        avatar_url = user.display_avatar.url if user.display_avatar else None
    except:
        avatar_url = None

    embed = discord.Embed(title=f"ℹ Infos Bannissement — {ban['username']}", color=discord.Color.orange())
    if avatar_url:
        embed.set_thumbnail(url=avatar_url)
        
    embed.add_field(name="Membre", value=f"<@{user_id}>", inline=True)
    embed.add_field(name="ID Utilisateur", value=f"`{user_id}`", inline=True)
    embed.add_field(name="Banni par", value=f"{ban['banned_by_name']} (<@{ban['banned_by_id']}>)", inline=False)
    embed.add_field(name="Date du ban", value=f"`{ban['banned_at']}`", inline=True)
    embed.add_field(name="Raison spécifiée", value=f"*{ban['reason']}*", inline=False)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="vestige", description="Consulter l'historique complet des sanctions d'un utilisateur.")
@app_commands.autocomplete(user_id=ban_autocomplete)
@app_commands.describe(user_id="L'utilisateur à vérifier (sélectionne ou entre un ID)")
@app_commands.checks.has_permissions(ban_members=True)
async def vestige(interaction: discord.Interaction, user_id: str):
    await interaction.response.defer()
    
    # Récupération de l'historique complet
    history = Database.get_user_history(interaction.guild.id, user_id)
    
    try:
        user = await bot.fetch_user(int(user_id))
        username = user.name
        avatar_url = user.display_avatar.url if user.display_avatar else None
    except:
        username = history[0]['real_username'] if history else "Utilisateur Inconnu"
        avatar_url = None

    if not history:
        return await interaction.followup.send(f"Aucun historique de bannissement trouvé pour **{username}** (`{user_id}`).", ephemeral=True)
    
    total_bans = len(history)
    active_ban = next((b for b in history if b['is_active'] == 1), None)
    
    embed = discord.Embed(
        title=f"📜 Historique de Modération — {username}",
        description=f"**ID :** `{user_id}`\n**Nombre total de bans :** `{total_bans}`\n**Statut actuel :** {'🔴 Actuellement banni' if active_ban else '🟢 Non banni'}",
        color=discord.Color.orange(),
        timestamp=datetime.now()
    )
    if avatar_url:
        embed.set_thumbnail(url=avatar_url)
        
    # On affiche les 5 sanctions les plus récentes pour éviter de dépasser la limite de caractères de Discord
    for i, ban in enumerate(history[:5], 1):
        status_str = "🔴 [Toujours Actif]" if ban['is_active'] == 1 else "🟢 [Débanni]"
        
        ban_details = f"**Banni le :** `{ban['banned_at']}` par {ban['banned_by_name']}\n"
        ban_details += f"└ **Raison du ban :** *{ban['reason']}*\n"
        
        if ban['is_active'] == 0 and ban['unbanned_at']:
            ban_details += f"└ **Débanni le :** `{ban['unbanned_at']}` par {ban['unbanned_by_name']}\n"
            ban_details += f"└ **Raison du déban :** *{ban['unban_reason'] or 'Aucune raison'}*\n"
            
        # Le calcul (total_bans - i + 1) permet d'afficher le bon numéro d'ordre (ex: Sanction #1, Sanction #2...)
        embed.add_field(
            name=f"Sanction #{total_bans - i + 1} {status_str}",
            value=ban_details,
            inline=False
        )
        
    if total_bans > 5:
        embed.set_footer(text=f"Affichage des 5 bans les plus récents sur un total de {total_bans}.")
        
    await interaction.followup.send(embed=embed)

bot.run(TOKEN)