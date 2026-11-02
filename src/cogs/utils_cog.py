import discord, os, json
from datetime import datetime
from discord import app_commands
from discord.ext import commands
from src.db import Database
from dotenv import load_dotenv

load_dotenv()
_raw_dev_id = os.getenv('DEV_ID', '').strip()
DEV_ID = int(_raw_dev_id) if _raw_dev_id.isdigit() else 0


def _format_discord_ts(ts_str: str, style: str = "R") -> str:
    if not ts_str:
        return "Jamais"
    try:
        dt = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
        return f"<t:{int(dt.timestamp())}:{style}>"
    except Exception:
        return ts_str


async def stats_command_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    choices: list[app_commands.Choice[str]] = []
    seen = set()
    query = current.lstrip("/").strip().lower()

    # 1. Commandes déjà enregistrées dans les statistiques
    guild_id = str(interaction.guild.id) if interaction.guild else None
    stats = Database.get_command_usage_stats(guild_id=guild_id)
    if stats and stats.get("commands"):
        for cmd_row in stats["commands"]:
            name = cmd_row["command_name"]
            if not query or query in name.lower():
                seen.add(name)
                label = f"/{name} ({cmd_row['total']} utilisations)"[:100]
                choices.append(app_commands.Choice(name=label, value=name))

    # 2. Autres commandes enregistrées sur l'arbre du bot
    for cmd in interaction.client.tree.walk_commands():
        name = cmd.qualified_name
        if name not in seen and (not query or query in name.lower()):
            seen.add(name)
            choices.append(app_commands.Choice(name=f"/{name}"[:100], value=name))

    return choices[:25]


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
        if DEV_ID != 0 and interaction.user.id == DEV_ID:
            await interaction.response.defer(ephemeral=True)
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

                await interaction.followup.send(response_text, ephemeral=True)
            else:
                await interaction.followup.send(f"**Erreur SQL :**\n```\n{result}\n```", ephemeral=True)
        else:
            return await interaction.response.send_message("Vous n'avez pas les permissions pour executer cette commande", ephemeral=True)

    @app_commands.command(name="logdata", description="Recupère les log des messages suprimer sur le server ou la commande est executé si autorisé")
    async def logdata(self, interaction: discord.Interaction):
        if DEV_ID == 0 or interaction.user.id != DEV_ID:
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

    @app_commands.command(name="url_database", description="Recupère les log des url suprimer sur le server")
    async def url_database(self, interaction: discord.Interaction):
        if DEV_ID == 0 or interaction.user.id != DEV_ID:
            return await interaction.response.send_message("Vous n'avez pas les permissions pour executer cette commande", ephemeral=True)

        await interaction.response.defer(thinking=True, ephemeral=True)
        filename = Database.urlbanned_show(interaction.guild.id, interaction.user.id, DEV_ID)

        if isinstance(filename, str) and os.path.exists(filename):
            await interaction.followup.send(
                content="Voici l'export des urls :",
                file=discord.File(filename)
            )
            os.remove(filename)
        else:
            error_msg = "Accès refusé ou aucune donnée trouvée."
            await interaction.followup.send(error_msg)

    @app_commands.command(name="stats", description="Affiche les statistiques d'utilisation et la fréquence des commandes (Admins & Dev)")
    @app_commands.describe(
        commande="Filtrer les statistiques sur une commande précise (optionnel)",
        portee="Afficher les statistiques du serveur actuel ou globales sur tous les serveurs"
    )
    @app_commands.autocomplete(commande=stats_command_autocomplete)
    @app_commands.choices(portee=[
        app_commands.Choice(name="🏠 Serveur actuel", value="serveur"),
        app_commands.Choice(name="🌍 Global (Tous les serveurs)", value="global")
    ])
    async def stats_command(
        self,
        interaction: discord.Interaction,
        commande: str = None,
        portee: str = "serveur"
    ):
        # Vérification des permissions : Administrateur du serveur OU Développeur du bot (si DEV_ID est renseigné)
        raw_dev = os.getenv('DEV_ID', '').strip()
        current_dev_id = int(raw_dev) if raw_dev.isdigit() else 0

        is_dev = (current_dev_id != 0 and interaction.user.id == current_dev_id)
        is_admin = bool(interaction.guild and interaction.user.guild_permissions.administrator)

        if not is_admin and not is_dev:
            return await interaction.response.send_message(
                "❌ Accès refusé : seuls les **administrateurs** du serveur et le **développeur du bot** peuvent consulter les statistiques des commandes.",
                ephemeral=True
            )

        await interaction.response.defer(ephemeral=True)

        target_guild_id = None
        if portee == "serveur" and interaction.guild:
            target_guild_id = str(interaction.guild.id)

        clean_cmd = commande.lstrip("/").strip() if commande else None
        data = Database.get_command_usage_stats(guild_id=target_guild_id, command_name=clean_cmd)

        if not data or data["total_uses"] == 0:
            embed = discord.Embed(
                title="📊 Statistiques d'utilisation des commandes",
                description="ℹ️ Aucune commande n'a encore été enregistrée dans le système de tracking pour cette sélection.",
                color=discord.Color.blurple()
            )
            return await interaction.followup.send(embed=embed, ephemeral=True)

        scope_label = f"Serveur : {interaction.guild.name}" if target_guild_id and interaction.guild else "Global (Tous les serveurs)"

        # CAS 1 : Vue détaillée sur une commande spécifique
        if clean_cmd:
            cmd_info = next((c for c in data["commands"] if c["command_name"].lower() == clean_cmd.lower()), None)
            if not cmd_info:
                return await interaction.followup.send(
                    f"⚠️ Aucune statistique enregistrée pour la commande `/{clean_cmd}` ({scope_label}).",
                    ephemeral=True
                )

            embed = discord.Embed(
                title=f"📊 Statistiques détaillées : /{cmd_info['command_name']}",
                description=f"**Portée :** `{scope_label}`\nVoici l'analyse de fréquence et d'utilisation de cette commande.",
                color=discord.Color.teal(),
                timestamp=datetime.now()
            )

            embed.add_field(
                name="🏆 Classement & Part",
                value=(
                    f"• **Rang :** `#{cmd_info['rank']}` sur `{len(data['commands'])}` commandes actives\n"
                    f"• **Part d'utilisation :** `{cmd_info['percentage']}%` du total"
                ),
                inline=True
            )
            embed.add_field(
                name="📈 Volume & Fréquence",
                value=(
                    f"• **Total :** `{cmd_info['total']}` exécution(s)\n"
                    f"• **Dernières 24h :** `{cmd_info['count_24h']}`\n"
                    f"• **7 derniers jours :** `{cmd_info['count_7d']}`\n"
                    f"• **30 derniers jours :** `{cmd_info['count_30d']}`\n"
                    f"• **Moyenne :** `{cmd_info['avg_per_day']}` / jour"
                ),
                inline=True
            )
            embed.add_field(
                name="⏰ Activité temporelle",
                value=(
                    f"• **Heure de pointe :** `{data['peak_hour']}`\n"
                    f"• **Première utilisation :** {_format_discord_ts(cmd_info['first_used'], 'f')}\n"
                    f"• **Dernière utilisation :** {_format_discord_ts(cmd_info['last_used'], 'R')}"
                ),
                inline=False
            )

            if data["top_users"]:
                users_lines = [
                    f"`{i}.` <@{u['user_id']}> (`{u['user_name']}`) — **{u['total']}** fois"
                    for i, u in enumerate(data["top_users"], 1)
                ]
                embed.add_field(name="👥 Top Utilisateurs de cette commande", value="\n".join(users_lines), inline=False)

            if data["recent_logs"]:
                recent_lines = []
                for log in data["recent_logs"]:
                    ch_mention = f"<#{log['channel_id']}>" if log["channel_id"] != "0" else "`MP`"
                    recent_lines.append(f"• {_format_discord_ts(log['timestamp'], 'R')} par <@{log['user_id']}> dans {ch_mention}")
                embed.add_field(name="🕒 5 dernières exécutions", value="\n".join(recent_lines), inline=False)

            embed.set_footer(text="Fern 🌿 • Tracking & Analyse des commandes")
            return await interaction.followup.send(embed=embed, ephemeral=True)

        # CAS 2 : Vue globale de toutes les commandes
        embed = discord.Embed(
            title="📊 Statistiques & Fréquence des Commandes",
            description=(
                f"**Portée :** `{scope_label}`\n"
                f"Suivi en temps réel des commandes les plus utilisées et de leur fréquence d'exécution."
            ),
            color=discord.Color.blurple(),
            timestamp=datetime.now()
        )

        embed.add_field(
            name="📈 Bilans & Fréquences",
            value=(
                f"• **Total enregistré :** `{data['total_uses']}` commandes\n"
                f"• **Dernières 24h :** `{data['uses_24h']}` (`{data['avg_per_hour_24h']}/h`)\n"
                f"• **7 derniers jours :** `{data['uses_7d']}`\n"
                f"• **30 derniers jours :** `{data['uses_30d']}`\n"
                f"• **Moyenne globale :** `{data['avg_per_day']}` cmd/jour\n"
                f"• **Heure de pointe :** `{data['peak_hour']}`"
            ),
            inline=False
        )

        # Top 10 des commandes
        medals = ["🥇", "🥈", "🥉"]
        cmd_lines = []
        for idx, c in enumerate(data["commands"][:10]):
            badge = medals[idx] if idx < 3 else f"`#{idx + 1}`"
            last_ts = _format_discord_ts(c["last_used"], "R")
            cmd_lines.append(
                f"{badge} **`/{c['command_name']}`** — **{c['total']}** fois (`{c['percentage']}%`)\n"
                f"  ↳ *24h : `{c['count_24h']}` | 7j : `{c['count_7d']}` | Moy : `{c['avg_per_day']}/j` • Dernière : {last_ts}*"
            )

        embed.add_field(
            name=f"🏆 Commandes les plus utilisées (Top {min(10, len(data['commands']))}/{len(data['commands'])})",
            value="\n".join(cmd_lines)[:1024] if cmd_lines else "Aucune donnée",
            inline=False
        )

        # Top 5 des utilisateurs
        if data["top_users"]:
            user_lines = [
                f"`{i}.` <@{u['user_id']}> (`{u['user_name']}`) — **{u['total']}** cmd(s)"
                for i, u in enumerate(data["top_users"], 1)
            ]
            embed.add_field(name="👥 Membres les plus actifs", value="\n".join(user_lines)[:1024], inline=False)

        embed.set_footer(text="Fern 🌿 • Astuce : utilisez /stats commande:<nom> pour inspecter une commande en détail.")
        await interaction.followup.send(embed=embed, ephemeral=True)

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
            "` Bannir et Supprimer ` — Menu contextuel (clic droit sur un message)\n"
            "` Supprimer et Archiver l'url ` — Menu contextuel (clic droit sur un message)"
        )
        embed.add_field(name="🔨 Modération — `Ban Members` / `Manage Messages`", value=mod_cmds, inline=False)

        # --- Configuration ---
        config_cmds = (
            "`/setup_alerts` — Configurer le salon et rôle d'alertes\n"
            "`/setup_logs` — Configurer le salon de logs publics\n"
            "`/roulette_setup` / `/champignon_setup` — Configurer le rôle cible pour la loterie membres\n"
            "`/setup_talents` — Configurer la roulette des talents (0 à N, noms, descriptions, rôles)\n"
            "`/salon_setup` — Configurer les catégories ou salons pour `/salon`\n"
            "`/salon_info` — Voir la configuration et la traçabilité des salons"
        )
        embed.add_field(name="⚙️ Configuration — `Manage Server`", value=config_cmds, inline=False)

        # --- Logs & Audit ---
        log_cmds = (
            "`/user_full_report` — Rapport JSON complet d'un utilisateur\n"
            "`/sync_history` — Synchroniser les anciens messages dans la DB\n"
            "`/stats` — Statistiques et fréquence d'utilisation des commandes"
        )
        embed.add_field(name="📊 Logs & Audit — `Administrateur` / `Développeur`", value=log_cmds, inline=False)

        # --- Fun & Jeux ---
        fun_cmds = (
            "`/roulette` / `/champignon` — Tirer au sort un membre au hasard parmi le rôle configuré\n"
            "`/roll_talent` — Lancer la roulette des talents (chiffre 0 à N, description & rôle)\n"
            "`/salon` — Tirer un salon au hasard parmi la sélection configurée"
        )
        embed.add_field(name="🎲 Fun & Jeux — Tous les membres", value=fun_cmds, inline=False)

        # --- Utilitaires ---
        util_cmds = (
            "`/hello` — Petit bonjour de Fern\n"
            "`/help` — Cette commande"
        )
        embed.add_field(name="🛠️ Utilitaires — Aucune permission requise", value=util_cmds, inline=False)

        # --- Dev only ---
        dev_cmds = (
            "`/sql` — Exécuter une commande SQL\n"
            "`/logdata` — Exporter les données de log\n"
            "`/url_database` — Récupère l'export des URL bloquées sur le serveur"
        )
        embed.add_field(name="🔒 Développeur uniquement", value=dev_cmds, inline=False)

        embed.set_footer(text="Fern 🌿 — Les logs silencieux (messages, éditions, kicks, bans, rôles, salons) fonctionnent automatiquement en arrière-plan.")

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(UtilsCog(bot))
