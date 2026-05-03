from src.db import Database, Utils
from src.music import Music
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
        print(f"Synced {len(synced)} command(s) synchroniser")
    except Exception as e:
        print(f"Erreur lors de la synchronisation des commandes : {e}")

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
        str_hashes
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
        ""
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
    description="Configure le rôle pour la commande champignon"
)
@app_commands.describe(
    role="role cible"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def champ_setup(interaction: discord.Interaction, role: discord.Role):
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
        
    data[guild_id]["champignon_role_id"] = role.id

    try:
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        
        await interaction.response.send_message(
            f"✅ Le rôle {role.mention} a été configuré pour la commande champignon.",
            ephemeral=True
        )
    except Exception as e:
        await interaction.response.send_message(f"Erreur lors de l'écriture du fichier : {e}", ephemeral=True)

@bot.tree.command(
    name="champignon",
    description="Tire au sort un membre ayant le rôle configuré (loterie)"
)
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
    if guild_id not in data or "champignon_role_id" not in data[guild_id]:
        return await interaction.response.send_message("Le rôle champignon n'est pas configuré. Utilisez `/champignon_setup`.", ephemeral=True)
        
    role_id = data[guild_id]["champignon_role_id"]
    role = interaction.guild.get_role(role_id)
    
    if not role:
        return await interaction.response.send_message("Le rôle configuré n'existe plus sur le serveur.", ephemeral=True)
        
    members_with_role = role.members
    if not members_with_role:
        return await interaction.response.send_message(f"Aucun membre ne possède le rôle {role.name}.", ephemeral=True)
        
    winner = random.choice(members_with_role)
    await interaction.response.send_message(f"Le grand gagnant est {winner.mention} !")

bot.run(TOKEN)