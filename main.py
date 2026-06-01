import discord, os, subprocess
from dotenv import load_dotenv
from discord import app_commands
from discord.ext import commands
from src.db import Database

load_dotenv()
TOKEN = os.getenv('TOKEN')
DEV_GUILD_ID = os.getenv('DEV_GUILD_ID')
DEV_ID = int(os.getenv('DEV_ID', 0))
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

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
    if isinstance(error, discord.app_commands.MissingPermissions):
        message_text = "❌ Vous n'avez pas les permissions nécessaires pour utiliser cette commande."
    else:
        message_text = f"❌ Une erreur est survenue : {error}"

    try:
        if interaction.response.is_done():
            await interaction.followup.send(message_text, ephemeral=True)
        else:
            await interaction.response.send_message(message_text, ephemeral=True)
    except discord.errors.NotFound:
        print(f"⚠️ Impossible d'envoyer la réponse à l'interaction : elle a expiré (plus de 3 secondes).")
    except Exception as e:
        print(f"Erreur imprévue dans le gestionnaire d'erreurs : {e}")

if __name__ == '__main__':
    bot.run(TOKEN)