import discord, os, json
from discord import app_commands
from discord.ext import commands
from src.db import Database
from dotenv import load_dotenv

load_dotenv()
DEV_ID = int(os.getenv('DEV_ID', 0))

class UtilsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="hello", description="Petit bonjour de Fern")
    async def hello(self, interaction: discord.Interaction, member: discord.Member):
        if member is None:
            await interaction.response.send_message("Veuillez mentionner un membre valide.", ephemeral=True)
            return
        await interaction.response.send_message(f"Hello {member.mention} :kiss:")

    @app_commands.command(name="sql", description="permet l'execution des commande sql directement depuis discord")
    @app_commands.describe(command="command sql")
    async def sql(self, interaction: discord.Interaction, command: str):
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

    @app_commands.command(name="logdata", description="Recupère les log des messages suprimer sur le server ou la commande est executé si autorisé")
    async def logdata(self, interaction: discord.Interaction):
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

    @app_commands.command(name="help", description="Affiche la liste de toutes les commandes et les permissions requises")
    async def help_command(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="📖 Commandes de Fern",
            description="Voici la liste complète des commandes disponibles et le niveau de permission requis pour les utiliser.",
            color=discord.Color.blurple()
        )

        # --- Modération ---
        mod_cmds = (
            "`/ban` — Bannir un membre\n"
            "`/unban` — Débannir un membre\n"
            "`/ban_list` — Voir la liste des bans actifs\n"
            "`/ban_info` — Détails d'un bannissement\n"
            "`/vestige` — Historique complet des sanctions d'un membre\n"
            "`/ban_texte` — Ajouter un texte interdit manuellement\n"
            "` Bannir et Supprimer ` — Menu contextuel (clic droit sur un message)"
        )
        embed.add_field(name="🔨 Modération — `Ban Members` / `Manage Messages`", value=mod_cmds, inline=False)

        # --- Configuration ---
        config_cmds = (
            "`/setup_alerts` — Configurer le salon et rôle d'alertes\n"
            "`/setup_logs` — Configurer le salon de logs publics\n"
            "`/champignon_setup` — Configurer la loterie champignon\n"
            "`/roulette_setup` — Configurer la roulette"
        )
        embed.add_field(name="⚙️ Configuration — `Manage Server`", value=config_cmds, inline=False)

        # --- Logs & Audit ---
        log_cmds = (
            "`/user_full_report` — Rapport JSON complet d'un utilisateur\n"
            "`/sync_history` — Synchroniser les anciens messages dans la DB"
        )
        embed.add_field(name="📊 Logs & Audit — `Administrateur`", value=log_cmds, inline=False)

        # --- Fun ---
        fun_cmds = (
            "`/champignon` — Tirer au sort un gagnant (loterie)\n"
            "`/roulette` — Tirer au sort un membre et le mentionner"
        )
        embed.add_field(name="🎲 Fun — `Manage Server` / `Manage Messages`", value=fun_cmds, inline=False)

        # --- Utilitaires ---
        util_cmds = (
            "`/hello` — Petit bonjour de Fern\n"
            "`/help` — Cette commande"
        )
        embed.add_field(name="🛠️ Utilitaires — Aucune permission requise", value=util_cmds, inline=False)

        # --- Dev only ---
        dev_cmds = (
            "`/sql` — Exécuter une commande SQL\n"
            "`/logdata` — Exporter les données de log"
        )
        embed.add_field(name="🔒 Développeur uniquement", value=dev_cmds, inline=False)

        embed.set_footer(text="Fern 🌿 — Les logs silencieux (messages, éditions, kicks, bans, rôles, salons) fonctionnent automatiquement en arrière-plan.")

        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(UtilsCog(bot))
