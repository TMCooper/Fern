import discord
import os
import random
import json
from datetime import datetime
from dotenv import load_dotenv
from discord import app_commands
from discord.ext import commands
from src.db import Database

load_dotenv()
_raw_dev_id = os.getenv('DEV_ID', '').strip()
DEV_ID = int(_raw_dev_id) if _raw_dev_id.isdigit() else 0


# ==========================================
# AUTOCOMPLÉTION DES COMMANDES
# ==========================================

async def categorie_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    if not interaction.guild:
        return []

    cats = interaction.guild.categories
    choices: list[app_commands.Choice[str]] = []

    # Gestion de la saisie multiple séparée par des virgules
    if "," in current:
        prefix = current[:current.rfind(",") + 1] + " "
        query = current[current.rfind(",") + 1:].strip().lower()
    else:
        prefix = ""
        query = current.strip().lower()

    # Proposer les modes spéciaux uniquement sur le premier token
    if not prefix:
        if not query or "manuel".startswith(query) or "manuel" in query:
            choices.append(app_commands.Choice(name="✍️ Manuel (Sélection manuelle des salons)", value="manuel"))
        if not query or "toutes".startswith(query) or "toutes" in query or "all".startswith(query):
            choices.append(app_commands.Choice(name="📁 Toutes les catégories du serveur", value="toutes"))

    for cat in cats:
        # Éviter de reproposer une catégorie déjà saisie dans le préfixe
        if str(cat.id) in prefix or cat.name.lower() in prefix.lower():
            continue

        if not query or query in cat.name.lower():
            display_name = f"{prefix}📁 {cat.name}"[:100]
            val = f"{prefix}{cat.id}".strip()
            choices.append(app_commands.Choice(name=display_name, value=val))

    return choices[:25]


async def exclure_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    if not interaction.guild:
        return []

    cat_arg = getattr(interaction.namespace, 'categorie', None) or ""
    cat_arg_clean = cat_arg.strip().lower()

    if cat_arg_clean == "manuel":
        return [app_commands.Choice(name="⚠️ L'exclusion ne s'applique qu'au mode catégories", value="none")]

    # Déterminer les catégories cibles
    if not cat_arg_clean or cat_arg_clean in ("toutes", "all"):
        target_cats = interaction.guild.categories
    else:
        tokens = [t.strip().lower() for t in cat_arg.split(",") if t.strip()]
        target_cats = []
        for cat in interaction.guild.categories:
            if str(cat.id) in tokens or cat.name.lower() in tokens:
                target_cats.append(cat)

    candidate_channels = []
    for cat in target_cats:
        for ch in cat.channels:
            if not isinstance(ch, discord.CategoryChannel):
                candidate_channels.append(ch)

    if "," in current:
        prefix = current[:current.rfind(",") + 1] + " "
        query = current[current.rfind(",") + 1:].strip().lower()
    else:
        prefix = ""
        query = current.strip().lower()

    choices: list[app_commands.Choice[str]] = []
    for ch in candidate_channels:
        if str(ch.id) in prefix or ch.name.lower() in prefix.lower():
            continue

        if not query or query in ch.name.lower():
            cat_name = ch.category.name if ch.category else "Sans catégorie"
            display_name = f"{prefix}#{ch.name} (📁 {cat_name})"[:100]
            val = f"{prefix}{ch.id}".strip()
            choices.append(app_commands.Choice(name=display_name, value=val))

    return choices[:25]


async def salons_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    if not interaction.guild:
        return []

    if "," in current:
        prefix = current[:current.rfind(",") + 1] + " "
        query = current[current.rfind(",") + 1:].strip().lower()
    else:
        prefix = ""
        query = current.strip().lower()

    choices: list[app_commands.Choice[str]] = []
    for ch in interaction.guild.channels:
        if isinstance(ch, discord.CategoryChannel):
            continue

        if str(ch.id) in prefix or ch.name.lower() in prefix.lower():
            continue

        if not query or query in ch.name.lower():
            cat_info = f" [📁 {ch.category.name}]" if ch.category else ""
            display_name = f"{prefix}#{ch.name}{cat_info}"[:100]
            val = f"{prefix}{ch.id}".strip()
            choices.append(app_commands.Choice(name=display_name, value=val))

    return choices[:25]


# ==========================================
# FONCTIONS UTILITAIRES DE PARSING
# ==========================================

def parse_category_inputs(guild: discord.Guild, raw_input: str) -> list[discord.CategoryChannel]:
    raw_input = raw_input.strip()
    if raw_input.lower() in ("toutes", "all"):
        return list(guild.categories)

    tokens = [t.strip() for t in raw_input.split(",") if t.strip()]
    found: list[discord.CategoryChannel] = []
    seen_ids = set()

    for token in tokens:
        # Recherche par ID
        if token.isdigit():
            cat = guild.get_channel(int(token))
            if isinstance(cat, discord.CategoryChannel) and cat.id not in seen_ids:
                found.append(cat)
                seen_ids.add(cat.id)
                continue

        # Recherche par nom insensible à la casse
        for cat in guild.categories:
            if cat.id not in seen_ids and cat.name.lower() == token.lower():
                found.append(cat)
                seen_ids.add(cat.id)
                break

    return found


def parse_channel_inputs(guild: discord.Guild, raw_input: str) -> list[discord.abc.GuildChannel]:
    tokens = [t.strip() for t in raw_input.split(",") if t.strip()]
    found: list[discord.abc.GuildChannel] = []
    seen_ids = set()

    for token in tokens:
        clean_token = token.replace("<#", "").replace(">", "").strip()

        # Recherche par ID
        if clean_token.isdigit():
            ch = guild.get_channel(int(clean_token))
            if ch and not isinstance(ch, discord.CategoryChannel) and ch.id not in seen_ids:
                found.append(ch)
                seen_ids.add(ch.id)
                continue

        # Recherche par nom
        for ch in guild.channels:
            if not isinstance(ch, discord.CategoryChannel) and ch.id not in seen_ids:
                if ch.name.lower() == clean_token.lower() or ch.name.lower() == token.lower():
                    found.append(ch)
                    seen_ids.add(ch.id)
                    break

    return found


def format_timestamp(ts_str: str) -> str:
    try:
        dt = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
        unix_ts = int(dt.timestamp())
        return f"<t:{unix_ts}:f> (<t:{unix_ts}:R>)"
    except Exception:
        return ts_str


# ==========================================
# VUES INTERACTIVES (UI VIEWS)
# ==========================================

class SafeSalonView(discord.ui.View):
    async def on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item) -> None:
        if isinstance(error, discord.HTTPException) and error.code in (40060, 10062):
            return
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ Une erreur est survenue : {error}", ephemeral=True)
            else:
                await interaction.followup.send(f"❌ Une erreur est survenue : {error}", ephemeral=True)
        except Exception:
            pass


class ManualSetupInteractiveView(SafeSalonView):
    def __init__(self, author_id: int):
        super().__init__(timeout=180)
        self.author_id = author_id
        self.selected_channel_ids: list[str] = []

        self.channel_select = discord.ui.ChannelSelect(
            channel_types=[
                discord.ChannelType.text,
                discord.ChannelType.voice,
                discord.ChannelType.news,
                discord.ChannelType.stage_voice,
                discord.ChannelType.forum
            ],
            placeholder="✍️ Sélectionnez les salons éligibles (jusqu'à 25)...",
            min_values=1,
            max_values=25
        )
        self.channel_select.callback = self.on_channel_select
        self.add_item(self.channel_select)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Seul l'administrateur ayant lancé cette configuration peut l'utiliser.", ephemeral=True)
            return False
        return True

    async def on_channel_select(self, interaction: discord.Interaction):
        self.selected_channel_ids = [str(ch.id) for ch in self.channel_select.values]
        await interaction.response.defer()

    @discord.ui.button(label="Valider et Enregistrer", style=discord.ButtonStyle.success, emoji="✅", row=1)
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.selected_channel_ids:
            return await interaction.response.send_message("⚠️ Veuillez sélectionner au moins un salon dans le menu ci-dessus.", ephemeral=True)

        guild = interaction.guild
        user = interaction.user

        details = f"Mode Manuel : {len(self.selected_channel_ids)} salon(s) configuré(s)"
        success = Database.set_salon_manual(
            guild.id,
            self.selected_channel_ids,
            user.id,
            user.display_name or user.name,
            details_text=details
        )

        if not success:
            return await interaction.response.send_message("❌ Une erreur est survenue lors de l'enregistrement en base de données.", ephemeral=True)

        mentions_str = ", ".join(f"<#{cid}>" for cid in self.selected_channel_ids)
        embed = discord.Embed(
            title="✅ Configuration enregistrée avec succès !",
            description="La liste des salons pour la commande `/salon` a été mise à jour en mode **Manuel**.",
            color=discord.Color.green()
        )
        embed.add_field(name="📌 Mode", value="`✍️ Manuel`", inline=True)
        embed.add_field(name="📊 Salons configurés", value=f"{len(self.selected_channel_ids)} salon(s)", inline=True)
        embed.add_field(name="💬 Liste des salons", value=mentions_str[:1024] if mentions_str else "Aucun", inline=False)
        embed.set_footer(text=f"Configuré par {user.display_name}")

        await interaction.response.edit_message(content=None, embed=embed, view=None)

    @discord.ui.button(label="Annuler", style=discord.ButtonStyle.secondary, emoji="❌", row=1)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="❌ Configuration annulée.", embed=None, view=None)


class CategorySetupInteractiveView(SafeSalonView):
    def __init__(self, author_id: int):
        super().__init__(timeout=180)
        self.author_id = author_id
        self.selected_categories: list[discord.CategoryChannel] = []
        self.excluded_channel_ids: list[str] = []

        # Sélection des catégories
        self.cat_select = discord.ui.ChannelSelect(
            channel_types=[discord.ChannelType.category],
            placeholder="1️⃣ Choisissez une ou plusieurs catégories...",
            min_values=1,
            max_values=25
        )
        self.cat_select.callback = self.on_categories_selected
        self.add_item(self.cat_select)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Seul l'administrateur ayant lancé cette configuration peut l'utiliser.", ephemeral=True)
            return False
        return True

    async def on_categories_selected(self, interaction: discord.Interaction):
        guild = interaction.guild
        self.selected_categories = [guild.get_channel(ch.id) for ch in self.cat_select.values if isinstance(guild.get_channel(ch.id), discord.CategoryChannel)]

        # Collecter les salons présents dans ces catégories
        channels_in_cats = []
        for cat in self.selected_categories:
            for ch in cat.channels:
                if not isinstance(ch, discord.CategoryChannel):
                    channels_in_cats.append(ch)

        # Nettoyer les items existants pour reconstruire l'étape 2
        self.clear_items()
        self.add_item(self.cat_select)

        if channels_in_cats:
            options = []
            for ch in channels_in_cats[:25]:
                cat_name = ch.category.name if ch.category else ""
                options.append(discord.SelectOption(
                    label=f"#{ch.name}"[:100],
                    value=str(ch.id),
                    description=f"📁 {cat_name}"[:100]
                ))

            self.exclude_select = discord.ui.Select(
                placeholder="2️⃣ (Optionnel) Sélectionnez les salons à exclure...",
                min_values=0,
                max_values=len(options),
                options=options
            )
            self.exclude_select.callback = self.on_exclude_selected
            self.add_item(self.exclude_select)

        # Bouton de validation
        confirm_btn = discord.ui.Button(label="Valider et Enregistrer", style=discord.ButtonStyle.success, emoji="✅", row=2)
        confirm_btn.callback = self.on_confirm
        self.add_item(confirm_btn)

        # Bouton d'annulation
        cancel_btn = discord.ui.Button(label="Annuler", style=discord.ButtonStyle.secondary, emoji="❌", row=2)
        cancel_btn.callback = self.on_cancel
        self.add_item(cancel_btn)

        cat_names = ", ".join(f"**{c.name}**" for c in self.selected_categories)
        msg = f"📁 **Catégories sélectionnées :** {cat_names}\n"
        if channels_in_cats:
            msg += f"👉 Vous pouvez exclure certains salons via le menu ci-dessous, puis cliquer sur **Valider**."
        else:
            msg += "⚠️ Aucun salon trouvé dans ces catégories pour le moment."

        await interaction.response.edit_message(content=msg, view=self)

    async def on_exclude_selected(self, interaction: discord.Interaction):
        self.excluded_channel_ids = self.exclude_select.values
        await interaction.response.defer()

    async def on_confirm(self, interaction: discord.Interaction):
        if not self.selected_categories:
            return await interaction.response.send_message("⚠️ Veuillez sélectionner au moins une catégorie.", ephemeral=True)

        guild = interaction.guild
        user = interaction.user

        cat_ids = [str(c.id) for c in self.selected_categories]
        details = f"Mode Catégories : {len(cat_ids)} catégorie(s), {len(self.excluded_channel_ids)} exclusion(s)"

        success = Database.set_salon_categories(
            guild.id,
            cat_ids,
            self.excluded_channel_ids,
            user.id,
            user.display_name or user.name,
            details_text=details
        )

        if not success:
            return await interaction.response.send_message("❌ Erreur lors de l'enregistrement en base de données.", ephemeral=True)

        # Calculer les salons résultants
        resulting_channels = []
        for cat in self.selected_categories:
            for ch in cat.channels:
                if not isinstance(ch, discord.CategoryChannel) and str(ch.id) not in self.excluded_channel_ids:
                    resulting_channels.append(ch)

        embed = discord.Embed(
            title="✅ Configuration enregistrée avec succès !",
            description="La liste des salons pour la commande `/salon` a été mise à jour en mode **Catégories**.",
            color=discord.Color.green()
        )
        embed.add_field(name="📌 Mode", value="`📁 Par Catégories`", inline=True)
        embed.add_field(name="📁 Catégories incluses", value=", ".join(f"**{c.name}**" for c in self.selected_categories), inline=True)
        
        excl_str = ", ".join(f"<#{cid}>" for cid in self.excluded_channel_ids) if self.excluded_channel_ids else "Aucun"
        embed.add_field(name="🚫 Salons exclus", value=excl_str[:1024], inline=False)

        res_str = ", ".join(str(ch.mention) for ch in resulting_channels) if resulting_channels else "⚠️ Aucun salon actif"
        embed.add_field(name=f"💬 Salons éligibles ({len(resulting_channels)})", value=res_str[:1024], inline=False)
        embed.set_footer(text=f"Configuré par {user.display_name}")

        await interaction.response.edit_message(content=None, embed=embed, view=None)

    async def on_cancel(self, interaction: discord.Interaction):
        await interaction.response.edit_message(content="❌ Configuration annulée.", embed=None, view=None)


class SalonHubView(SafeSalonView):
    def __init__(self, author_id: int):
        super().__init__(timeout=120)
        self.author_id = author_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Seul l'administrateur ayant lancé cette commande peut interagir.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Par Catégories", style=discord.ButtonStyle.primary, emoji="📁", row=0)
    async def mode_categories_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = CategorySetupInteractiveView(self.author_id)
        msg = "📁 **Configuration par Catégories**\nSélectionnez une ou plusieurs catégories dans le menu ci-dessous :"
        await interaction.response.edit_message(content=msg, embed=None, view=view)

    @discord.ui.button(label="Sélection Manuelle", style=discord.ButtonStyle.secondary, emoji="✍️", row=0)
    async def mode_manual_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = ManualSetupInteractiveView(self.author_id)
        msg = "✍️ **Configuration Manuelle des Salons**\nChoisissez directement les salons que vous souhaitez inclure dans le tirage :"
        await interaction.response.edit_message(content=msg, embed=None, view=view)

    @discord.ui.button(label="Réinitialiser", style=discord.ButtonStyle.danger, emoji="🗑️", row=0)
    async def reset_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        user = interaction.user
        success = Database.reset_salon_settings(guild.id, user.id, user.display_name or user.name)

        if success:
            embed = discord.Embed(
                title="🔄 Configuration réinitialisée",
                description="La configuration des salons a été supprimée. La commande `/salon` est désormais désactivée jusqu'à nouvelle configuration.",
                color=discord.Color.orange()
            )
            embed.set_footer(text=f"Réinitialisé par {user.display_name}")
            await interaction.response.edit_message(content=None, embed=embed, view=None)
        else:
            await interaction.response.send_message("❌ Erreur lors de la réinitialisation.", ephemeral=True)

    @discord.ui.button(label="Fermer", style=discord.ButtonStyle.secondary, emoji="✖️", row=1)
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Configuration fermée.", embed=None, view=None)


# ==========================================
# COG PRINCIPAL : SALON
# ==========================================

class SalonCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ----------------------------------------------------
    # COMMANDE 1 : /salon (Accessible à tous sans restriction)
    # ----------------------------------------------------
    @app_commands.command(name="salon", description="Tire un salon au hasard parmi les salons configurés")
    @app_commands.guild_only()
    async def salon(self, interaction: discord.Interaction):
        if not interaction.guild:
            return await interaction.response.send_message("❌ Cette commande doit être exécutée dans un serveur.", ephemeral=True)

        settings = Database.get_salon_settings(interaction.guild.id)
        if not settings:
            return await interaction.response.send_message(
                "⚠️ Aucun salon n'a encore été configuré pour le tirage au sort sur ce serveur.\n"
                "Un administrateur peut configurer les salons avec la commande `/salon_setup`.",
                ephemeral=True
            )

        mode = settings.get("mode")
        available_channels: list[discord.abc.GuildChannel] = []

        if mode == "CATEGORIES":
            cat_ids = set(settings.get("categories", []))
            excl_ids = set(settings.get("excluded_channels", []))

            for ch in interaction.guild.channels:
                if isinstance(ch, discord.CategoryChannel):
                    continue
                if str(getattr(ch, "category_id", None)) in cat_ids:
                    if str(ch.id) not in excl_ids:
                        available_channels.append(ch)

        elif mode == "MANUAL":
            manual_ids = set(settings.get("manual_channels", []))
            for cid in manual_ids:
                try:
                    ch = interaction.guild.get_channel(int(cid))
                    if ch and not isinstance(ch, discord.CategoryChannel):
                        available_channels.append(ch)
                except ValueError:
                    continue

        if not available_channels:
            return await interaction.response.send_message(
                "⚠️ Aucun salon valide n'a été trouvé parmi ceux configurés "
                "(ils ont peut-être été supprimés ou rendus inaccessibles).\n"
                "Un administrateur peut mettre à jour la configuration avec `/salon_setup`.",
                ephemeral=True
            )

        # Tirage au sort d'un salon aléatoire
        chosen_channel = random.choice(available_channels)

        # Envoi au format demandé : <#{id_salon}>
        await interaction.response.send_message(f"<#{chosen_channel.id}>")

    # ----------------------------------------------------
    # COMMANDE 2 : /salon_setup (Administrateurs uniquement)
    # ----------------------------------------------------
    @app_commands.command(name="salon_setup", description="Configure les salons éligibles pour le tirage /salon (Admins)")
    @app_commands.describe(
        categorie="Catégorie(s) ou 'manuel' pour choisir des salons (laisser vide pour ouvrir le menu interactif)",
        exclure="Salon(s) à exclure de la/des catégorie(s) sélectionnée(s)",
        salons="En mode manuel : salon(s) à inclure (séparés par des virgules si plusieurs)"
    )
    @app_commands.autocomplete(
        categorie=categorie_autocomplete,
        exclure=exclure_autocomplete,
        salons=salons_autocomplete
    )
    @app_commands.guild_only()
    async def salon_setup(
        self,
        interaction: discord.Interaction,
        categorie: str = None,
        exclure: str = None,
        salons: str = None
    ):
        if not interaction.guild:
            return await interaction.response.send_message("❌ Cette commande doit être exécutée dans un serveur.", ephemeral=True)

        is_dev = (DEV_ID != 0 and interaction.user.id == DEV_ID)
        is_admin = interaction.user.guild_permissions.administrator or interaction.user.guild_permissions.manage_guild or is_dev
        if not is_admin:
            return await interaction.response.send_message("❌ Vous devez être administrateur (ou avoir la permission 'Gérer le serveur') pour exécuter cette commande.", ephemeral=True)

        guild = interaction.guild
        user = interaction.user

        # CAS 1 : Aucun argument fourni -> Ouverture du menu interactif complet
        if not categorie and not salons:
            embed = discord.Embed(
                title="⚙️ Configuration du Tirage au Sort (/salon)",
                description=(
                    "Bienvenue dans le panneau de configuration des salons éligibles.\n\n"
                    "Choisissez une option ci-dessous :\n"
                    "• **📁 Par Catégories** : Sélectionnez une ou plusieurs catégories et excluez éventuellement certains salons.\n"
                    "• **✍️ Sélection Manuelle** : Choisissez individuellement les salons de votre choix.\n"
                    "• **🗑️ Réinitialiser** : Effacer la configuration existante."
                ),
                color=discord.Color.blue()
            )
            embed.set_footer(text="Fern 🌿 • Configuration des salons")
            view = SalonHubView(user.id)
            return await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

        # CAS 2 : Mode Manuel
        if (categorie and categorie.strip().lower() == "manuel") or (not categorie and salons):
            # Si des salons ont été fournis directement en argument
            if salons:
                target_channels = parse_channel_inputs(guild, salons)
                if not target_channels:
                    return await interaction.response.send_message(
                        "❌ Aucun salon valide n'a été reconnu dans votre saisie.\n"
                        "Veuillez mentionner les salons (ex: `#général, #gaming`) ou saisir leurs IDs.",
                        ephemeral=True
                    )

                channel_ids = [str(ch.id) for ch in target_channels]
                details = f"Mode Manuel : {len(channel_ids)} salon(s) configuré(s)"
                success = Database.set_salon_manual(
                    guild.id,
                    channel_ids,
                    user.id,
                    user.display_name or user.name,
                    details_text=details
                )

                if not success:
                    return await interaction.response.send_message("❌ Erreur lors de l'enregistrement en base de données.", ephemeral=True)

                mentions_str = ", ".join(str(ch.mention) for ch in target_channels)
                embed = discord.Embed(
                    title="✅ Configuration enregistrée avec succès !",
                    description="La liste des salons pour `/salon` a été mise à jour en mode **Manuel**.",
                    color=discord.Color.green()
                )
                embed.add_field(name="📌 Mode", value="`✍️ Manuel`", inline=True)
                embed.add_field(name="📊 Salons configurés", value=f"{len(target_channels)} salon(s)", inline=True)
                embed.add_field(name="💬 Salons éligibles", value=mentions_str[:1024], inline=False)
                embed.set_footer(text=f"Configuré par {user.display_name}")

                return await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                # Ouvre le sélecteur interactif manuel
                view = ManualSetupInteractiveView(user.id)
                return await interaction.response.send_message(
                    "✍️ **Configuration Manuelle des Salons**\nSélectionnez les salons souhaités dans le menu ci-dessous puis validez :",
                    view=view,
                    ephemeral=True
                )

        # CAS 3 : Mode Catégories (avec ou sans exclusions)
        categories_found = parse_category_inputs(guild, categorie)
        if not categories_found:
            return await interaction.response.send_message(
                f"❌ Aucune catégorie valide correspondant à `{categorie}` n'a été trouvée sur ce serveur.",
                ephemeral=True
            )

        cat_ids = [str(c.id) for c in categories_found]

        # Salons exclus
        excluded_channels = parse_channel_inputs(guild, exclure) if exclure else []
        excluded_ids = [str(ch.id) for ch in excluded_channels]

        # Calculer les salons résultants
        resulting_channels: list[discord.abc.GuildChannel] = []
        for cat in categories_found:
            for ch in cat.channels:
                if not isinstance(ch, discord.CategoryChannel) and str(ch.id) not in excluded_ids:
                    resulting_channels.append(ch)

        if not resulting_channels:
            return await interaction.response.send_message(
                "⚠️ Attention : aucun salon actif ne correspond à cette sélection (tous les salons sont peut-être exclus ou les catégories sont vides).",
                ephemeral=True
            )

        details = f"Mode Catégories : {len(cat_ids)} catégorie(s), {len(excluded_ids)} exclusion(s)"
        success = Database.set_salon_categories(
            guild.id,
            cat_ids,
            excluded_ids,
            user.id,
            user.display_name or user.name,
            details_text=details
        )

        if not success:
            return await interaction.response.send_message("❌ Erreur lors de l'enregistrement en base de données.", ephemeral=True)

        embed = discord.Embed(
            title="✅ Configuration enregistrée avec succès !",
            description="La liste des salons pour `/salon` a été mise à jour en mode **Catégories**.",
            color=discord.Color.green()
        )
        embed.add_field(name="📌 Mode", value="`📁 Par Catégories`", inline=True)
        embed.add_field(name="📁 Catégories incluses", value=", ".join(f"**{c.name}**" for c in categories_found), inline=True)

        excl_str = ", ".join(str(ch.mention) for ch in excluded_channels) if excluded_channels else "Aucun"
        embed.add_field(name="🚫 Salons exclus", value=excl_str[:1024], inline=False)

        res_str = ", ".join(str(ch.mention) for ch in resulting_channels)
        embed.add_field(name=f"💬 Salons éligibles au tirage ({len(resulting_channels)})", value=res_str[:1024], inline=False)
        embed.set_footer(text=f"Configuré par {user.display_name}")

        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ----------------------------------------------------
    # COMMANDE 3 : /salon_info (Administrateurs uniquement)
    # ----------------------------------------------------
    @app_commands.command(name="salon_info", description="Affiche la configuration actuelle des salons et l'historique des modifications (Admins)")
    @app_commands.guild_only()
    async def salon_info(self, interaction: discord.Interaction):
        if not interaction.guild:
            return await interaction.response.send_message("❌ Cette commande doit être exécutée dans un serveur.", ephemeral=True)

        is_dev = (DEV_ID != 0 and interaction.user.id == DEV_ID)
        is_admin = interaction.user.guild_permissions.administrator or interaction.user.guild_permissions.manage_guild or is_dev
        if not is_admin:
            return await interaction.response.send_message("❌ Vous devez être administrateur (ou avoir la permission 'Gérer le serveur') pour voir la configuration des salons.", ephemeral=True)

        guild = interaction.guild
        settings = Database.get_salon_settings(guild.id)
        history = Database.get_salon_history(guild.id, limit=5)

        if not settings:
            embed = discord.Embed(
                title="📋 Configuration des Salons — Aucune configuration active",
                description=(
                    "⚠️ Aucun salon n'est actuellement configuré pour le tirage au sort `/salon` sur ce serveur.\n\n"
                    "Utilisez `/salon_setup` pour en configurer un par catégories ou manuellement."
                ),
                color=discord.Color.gold()
            )
            if history:
                hist_lines = []
                for entry in history:
                    ts = format_timestamp(entry["timestamp"])
                    hist_lines.append(f"• {ts} — <@{entry['user_id']}> : `{entry['action']}` ({entry['details']})")
                embed.add_field(name="📜 Historique récent des modifications", value="\n".join(hist_lines), inline=False)

            return await interaction.response.send_message(embed=embed, ephemeral=True)

        mode = settings.get("mode")
        embed = discord.Embed(
            title="📋 Configuration Actuelle des Salons (/salon)",
            description="Voici le paramétrage actuellement actif ainsi que l'historique de traçabilité des modifications.",
            color=discord.Color.blue()
        )

        embed.add_field(
            name="📌 Mode Actif",
            value=f"`📁 Par Catégories`" if mode == "CATEGORIES" else f"`✍️ Manuel`",
            inline=True
        )

        # Calcul des salons éligibles en direct
        available_channels: list[discord.abc.GuildChannel] = []

        if mode == "CATEGORIES":
            cat_ids = settings.get("categories", [])
            excl_ids = settings.get("excluded_channels", [])

            cat_names = []
            for cid in cat_ids:
                try:
                    c = guild.get_channel(int(cid))
                    if c:
                        cat_names.append(f"📁 {c.name}")
                    else:
                        cat_names.append(f"📁 *(Inconnu/Supprimé: {cid})*")
                except ValueError:
                    cat_names.append(f"📁 {cid}")

            excl_mentions = []
            for eid in excl_ids:
                try:
                    ch = guild.get_channel(int(eid))
                    if ch:
                        excl_mentions.append(str(ch.mention))
                    else:
                        excl_mentions.append(f"<#{eid}>")
                except ValueError:
                    excl_mentions.append(f"<#{eid}>")

            embed.add_field(name="📁 Catégories configurées", value=", ".join(cat_names) if cat_names else "Aucune", inline=False)
            embed.add_field(name="🚫 Salons exclus", value=", ".join(excl_mentions) if excl_mentions else "Aucun", inline=False)

            for ch in guild.channels:
                if not isinstance(ch, discord.CategoryChannel):
                    if str(getattr(ch, "category_id", None)) in cat_ids and str(ch.id) not in excl_ids:
                        available_channels.append(ch)

        elif mode == "MANUAL":
            manual_ids = settings.get("manual_channels", [])
            manual_mentions = []
            for cid in manual_ids:
                try:
                    ch = guild.get_channel(int(cid))
                    if ch:
                        manual_mentions.append(str(ch.mention))
                        available_channels.append(ch)
                    else:
                        manual_mentions.append(f"<#{cid}> *(introuvable)*")
                except ValueError:
                    manual_mentions.append(f"<#{cid}>")

            embed.add_field(name="💬 Salons configurés", value=", ".join(manual_mentions) if manual_mentions else "Aucun", inline=False)

        # Salons éligibles trouvés
        res_mentions = ", ".join(str(ch.mention) for ch in available_channels) if available_channels else "⚠️ Aucun salon actif"
        embed.add_field(
            name=f"🎲 Salons actuellement éligibles au tirage ({len(available_channels)})",
            value=res_mentions[:1024],
            inline=False
        )

        # Auteur de la dernière modification
        updater_id = settings.get("last_updated_by_id", "0")
        updater_name = settings.get("last_updated_by_name", "Inconnu")
        updated_at_str = format_timestamp(settings.get("last_updated_at", ""))
        embed.add_field(
            name="👤 Dernière modification",
            value=f"• **Par :** <@{updater_id}> (`{updater_name}`)\n• **Date :** {updated_at_str}",
            inline=False
        )

        # Historique de traçabilité
        if history:
            hist_lines = []
            for entry in history:
                ts = format_timestamp(entry["timestamp"])
                action_badge = {
                    "SETUP_CATEGORIES": "📁 Catégories",
                    "SETUP_MANUAL": "✍️ Manuel",
                    "RESET": "🔄 Réinitialisation"
                }.get(entry["action"], entry["action"])
                hist_lines.append(f"• {ts} — <@{entry['user_id']}> : **{action_badge}**\n  ↳ *{entry['details']}*")
            embed.add_field(
                name="📜 Historique des configurations (Traçabilité)",
                value="\n".join(hist_lines)[:1024],
                inline=False
            )

        embed.set_footer(text="Fern 🌿 • Traçabilité et configuration des salons")
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(SalonCog(bot))
