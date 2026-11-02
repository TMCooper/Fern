import discord, os, subprocess
from dotenv import load_dotenv
from discord import app_commands
from discord.ext import commands
from src.db import Database

load_dotenv()
TOKEN = os.getenv('TOKEN')
DEV_GUILD_ID = os.getenv('DEV_GUILD_ID')
_raw_dev_id = os.getenv('DEV_ID', '').strip()
DEV_ID = int(_raw_dev_id) if _raw_dev_id.isdigit() else 0


def ensure_single_instance():
    """Garantit qu'une seule instance locale du bot tourne à la fois pour éviter les erreurs 40060 (Interaction already acknowledged)."""
    pid_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".bot.pid")
    current_pid = os.getpid()
    parent_pid = os.getppid()

    if os.path.exists(pid_file):
        try:
            with open(pid_file, "r", encoding="utf-8") as f:
                old_pids = [int(p.strip()) for p in f.read().split(",") if p.strip().isdigit()]
            for old_pid in old_pids:
                if old_pid not in (current_pid, parent_pid) and old_pid > 0:
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(old_pid)],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )
        except Exception:
            pass

    try:
        with open(pid_file, "w", encoding="utf-8") as f:
            f.write(f"{current_pid},{parent_pid}")
    except Exception:
        pass


Database.check_database()

# Configuration du bot
intents = discord.Intents.all()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def setup_hook():
    # Chargement dynamique des Cogs
    cogs_dir = os.path.join(os.path.dirname(__file__), "src", "cogs")
    if os.path.exists(cogs_dir):
        for filename in os.listdir(cogs_dir):
            if filename.endswith(".py") and not filename.startswith("__"):
                try:
                    await bot.load_extension(f"src.cogs.{filename[:-3]}")
                    print(f"✅ Extension chargée: {filename}")
                except Exception as e:
                    print(f"❌ Erreur lors du chargement de {filename}: {e}")


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


@bot.event
async def on_app_command_completion(interaction: discord.Interaction, command: app_commands.Command | app_commands.ContextMenu):
    # Enregistrement automatique de l'utilisation de chaque commande slash ou menu contextuel
    guild_id = str(interaction.guild.id) if interaction.guild else "DM"
    channel_id = str(interaction.channel.id) if interaction.channel else "0"
    user_id = str(interaction.user.id)
    user_name = interaction.user.display_name or interaction.user.name
    cmd_name = command.qualified_name

    Database.log_command_usage(guild_id, channel_id, user_id, user_name, cmd_name)


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
    # Extraire l'erreur sous-jacente si encapsulée dans CommandInvokeError
    original = getattr(error, "original", error)

    # Si l'interaction a déjà été acquittée (40060), ne pas retenter d'envoyer une réponse d'erreur
    if isinstance(original, discord.HTTPException) and original.code == 40060:
        return

    # Si l'interaction a expiré (10062 / NotFound)
    if isinstance(original, discord.NotFound) or (isinstance(original, discord.HTTPException) and original.code == 10062):
        print("⚠️ Impossible d'envoyer la réponse à l'interaction : elle a expiré (plus de 3 secondes).")
        return

    if isinstance(error, discord.app_commands.MissingPermissions):
        message_text = "❌ Vous n'avez pas les permissions nécessaires pour utiliser cette commande."
    elif isinstance(error, discord.app_commands.BotMissingPermissions):
        message_text = "❌ Je n'ai pas les permissions nécessaires sur le serveur pour exécuter cette action."
    elif isinstance(error, discord.app_commands.CommandOnCooldown):
        message_text = f"⏳ Cette commande est en cooldown. Réessayez dans {error.retry_after:.1f}s."
    else:
        message_text = f"❌ Une erreur est survenue : {original}"

    try:
        if interaction.response.is_done():
            await interaction.followup.send(message_text, ephemeral=True)
        else:
            await interaction.response.send_message(message_text, ephemeral=True)
    except discord.HTTPException as e:
        if e.code == 40060:
            try:
                await interaction.followup.send(message_text, ephemeral=True)
            except Exception:
                pass
        elif e.code == 10062:
            print("⚠️ Impossible d'envoyer la réponse à l'interaction : elle a expiré (plus de 3 secondes).")
        else:
            print(f"Erreur HTTP dans le gestionnaire d'erreurs : {e}")
    except Exception as e:
        print(f"Erreur imprévue dans le gestionnaire d'erreurs : {e}")


if __name__ == '__main__':
    ensure_single_instance()
    bot.run(TOKEN)
