from src.db import Database, Utils
import discord, os, subprocess, json, asyncio
from dotenv import load_dotenv
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone, timedelta

load_dotenv()
TOKEN = os.getenv('TOKEN')
DEV_GUILD_ID = os.getenv('DEV_GUILD_ID')
DEV_ID = int(os.getenv('DEV_ID'))
Database.check_database()

pending_deletes = {}
IGNORED_IDS = [431544605209788416, 276060004262477825]

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

@bot.event
async def on_message(message):
    if message.author == bot.user or message.webhook_id is not None:
        return

    # Si c'est un webhook qui reposte (Tupper), on nettoie le pending
    if message.webhook_id and message.author.bot:
        to_remove = [
            mid for mid, msg in pending_deletes.items()
            if msg.content and msg.content.split(".", 1)[-1].strip() == message.content
        ]
        for mid in to_remove:
            del pending_deletes[mid]

        await bot.process_commands(message)
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

@bot.event
async def on_message_delete(message):
    if not message.guild:
        return

    # On met le message en attente 2 secondes
    pending_deletes[message.id] = message
    await asyncio.sleep(2)

    # Si le message a été retiré du pending (= Tupper détecté), on ignore
    if message.id not in pending_deletes:
        return

    # Suppression normale, on log
    del pending_deletes[message.id]

    try:
        hashes_found = []
        for attachment in message.attachments:
            if attachment.content_type and attachment.content_type.startswith('image/'):
                try:
                    file_hash = await Utils.get_image_hash(attachment)
                    hashes_found.append(file_hash)
                except:
                    continue

        str_hashes = ",".join(hashes_found) if hashes_found else None

        async for entry in message.guild.audit_logs(limit=5, action=discord.AuditLogAction.message_delete):
            if entry.target.id == message.author.id:
                if entry.user.id in IGNORED_IDS:
                    return

                # On ignore si l'auteur du message supprimé est un bot
                if message.author.bot:
                    return

                # On vérifie que le log a moins de 5 secondes
                age = datetime.now(timezone.utc) - entry.created_at
                if age > timedelta(seconds=5):
                    return

                Database.database_incrementation(
                    message.guild.id,
                    message.guild.name,
                    message.content,
                    message.author.name,
                    message.author.id,
                    entry.user.name,
                    entry.user.id,
                    str_hashes
                )
                print(f"Log enregistré : {entry.user.name} a supprimé le message de {message.author.name}")
                return

    except discord.Forbidden:
        print("Erreur : Je n'ai pas la permission de voir les logs d'audit.")
    except Exception as e:
        print(f"Erreur imprévue : {e}")
    
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

    data[str(interaction.guild.id)] = {
        "channel_id": channel.id,
        "role_id": role.id
    }

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

bot.run(TOKEN)