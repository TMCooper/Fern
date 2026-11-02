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
# RÉCUPÉRATION COMPLÈTE & PARSING INTELLIGENT
# ==========================================

async def fetch_all_guild_channels(guild: discord.Guild) -> tuple[list[discord.CategoryChannel], list[discord.abc.GuildChannel]]:
    """Récupère l'intégralité des catégories et salons directement depuis l'API Discord (évite les caches incomplets)."""
    try:
        all_channels = await guild.fetch_channels()
    except Exception:
        all_channels = list(guild.channels)

    categories = [c for c in all_channels if isinstance(c, discord.CategoryChannel)]
    categories.sort(key=lambda c: getattr(c, "position", 0))

    non_categories = [c for c in all_channels if not isinstance(c, discord.CategoryChannel)]
    cat_pos_map = {c.id: idx for idx, c in enumerate(categories)}

    def channel_sort_key(ch):
        cat_order = cat_pos_map.get(getattr(ch, "category_id", None), 9999)
        is_voice = 1 if isinstance(ch, (discord.VoiceChannel, discord.StageChannel)) else 0
        return (cat_order, is_voice, getattr(ch, "position", 0), ch.name.lower())

    non_categories.sort(key=channel_sort_key)
    return categories, non_categories


def get_channels_for_categories(
    categories: list[discord.CategoryChannel],
    all_non_cat_channels: list[discord.abc.GuildChannel]
) -> list[discord.abc.GuildChannel]:
    """Retourne tous les salons appartenant aux catégories sélectionnées."""
    cat_ids = {c.id for c in categories}
    return [ch for ch in all_non_cat_channels if getattr(ch, "category_id", None) in cat_ids]


def parse_category_inputs(
    guild: discord.Guild,
    raw_input: str,
    categories_list: list[discord.CategoryChannel] = None
) -> list[discord.CategoryChannel]:
    if not raw_input:
        return []
    cats_pool = categories_list if categories_list is not None else list(guild.categories)
    raw_clean = raw_input.strip()
    if raw_clean.lower() in ("toutes", "all", "*"):
        return list(cats_pool)

    tokens = [t.strip() for t in raw_clean.split(",") if t.strip()]
    found: list[discord.CategoryChannel] = []
    seen_ids = set()

    for token in tokens:
        clean_t = token.lstrip("#📁 ").strip()
        if clean_t.isdigit():
            cid = int(clean_t)
            cat = next((c for c in cats_pool if c.id == cid), None) or guild.get_channel(cid)
            if isinstance(cat, discord.CategoryChannel) and cat.id not in seen_ids:
                found.append(cat)
                seen_ids.add(cat.id)
                continue

        # 1. Correspondance exacte (insensible à la casse)
        matched = False
        for cat in cats_pool:
            if cat.id not in seen_ids and (cat.name.lower() == clean_t.lower() or cat.name.lower() == token.lower()):
                found.append(cat)
                seen_ids.add(cat.id)
                matched = True
                break

        # 2. Correspondance partielle si non trouvé
        if not matched and clean_t:
            for cat in cats_pool:
                if cat.id not in seen_ids and clean_t.lower() in cat.name.lower():
                    found.append(cat)
                    seen_ids.add(cat.id)
                    break

    return found


def parse_channel_inputs(
    guild: discord.Guild,
    raw_input: str,
    channels_pool: list[discord.abc.GuildChannel] = None
) -> list[discord.abc.GuildChannel]:
    if not raw_input:
        return []
    pool = channels_pool if channels_pool is not None else [
        c for c in guild.channels if not isinstance(c, discord.CategoryChannel)
    ]

    tokens = [t.strip() for t in raw_input.split(",") if t.strip()]
    found: list[discord.abc.GuildChannel] = []
    seen_ids = set()

    for token in tokens:
        clean_token = token.replace("<#", "").replace(">", "").lstrip("#").strip()
        if not clean_token:
            continue

        # 1. Recherche par ID
        if clean_token.isdigit():
            cid = int(clean_token)
            ch = next((c for c in pool if c.id == cid), None) or guild.get_channel(cid)
            if ch and not isinstance(ch, discord.CategoryChannel) and ch.id not in seen_ids:
                found.append(ch)
                seen_ids.add(ch.id)
                continue

        # 2. Recherche par nom exact
        matched = False
        for ch in pool:
            if ch.id not in seen_ids:
                if ch.name.lower() == clean_token.lower() or ch.name.lower() == token.lower():
                    found.append(ch)
                    seen_ids.add(ch.id)
                    matched = True
                    break

        # 3. Recherche partielle (ex: salon avec emoji ou tirets)
        if not matched:
            for ch in pool:
                if ch.id not in seen_ids and clean_token.lower() in ch.name.lower():
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
# AUTOCOMPLÉTION DES COMMANDES SLASH
# ==========================================

async def categorie_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    if not interaction.guild:
        return []

    cats = interaction.guild.categories
    choices: list[app_commands.Choice[str]] = []

    if "," in current:
        prefix = current[:current.rfind(",") + 1] + " "
        query = current[current.rfind(",") + 1:].strip().lower()
    else:
        prefix = ""
        query = current.strip().lower()

    if not prefix:
        if not query or "manuel".startswith(query) or "manuel" in query:
            choices.append(app_commands.Choice(name="✍️ Manuel (Sélection manuelle des salons)", value="manuel"))
        if not query or "toutes".startswith(query) or "toutes" in query or "all".startswith(query):
            choices.append(app_commands.Choice(name="📁 Toutes les catégories du serveur", value="toutes"))

    for cat in cats:
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

    if not cat_arg_clean or cat_arg_clean in ("toutes", "all"):
        target_cats = list(interaction.guild.categories)
    else:
        target_cats = parse_category_inputs(interaction.guild, cat_arg)
        if not target_cats:
            target_cats = list(interaction.guild.categories)

    target_cat_ids = {c.id for c in target_cats}
    candidate_channels = [
        ch for ch in interaction.guild.channels
        if not isinstance(ch, discord.CategoryChannel) and getattr(ch, "category_id", None) in target_cat_ids
    ]

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

        cat_name = ch.category.name if ch.category else "Sans catégorie"
        if not query or query in ch.name.lower() or query in cat_name.lower():
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

        cat_name = ch.category.name if ch.category else ""
        if not query or query in ch.name.lower() or query in cat_name.lower():
            cat_info = f" [📁 {cat_name}]" if cat_name else ""
            display_name = f"{prefix}#{ch.name}{cat_info}"[:100]
            val = f"{prefix}{ch.id}".strip()
            choices.append(app_commands.Choice(name=display_name, value=val))

    return choices[:25]


# ==========================================
# VUES INTERACTIVES & MODALS (INTERFACE GRAPHIQUE)
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


class ManualChannelTextModal(discord.ui.Modal, title="✍️ Saisir les salons par nom ou ID"):
    channels_input = discord.ui.TextInput(
        label="Noms ou IDs des salons (séparés par virgule)",
        style=discord.TextStyle.paragraph,
        placeholder="Ex: général, demo, bot-test, free (recherche dans toutes les catégories)",
        required=True,
        max_length=1500
    )

    def __init__(self, parent_view: "ManualSetupInteractiveView"):
        super().__init__()
        self.parent_view = parent_view
        if parent_view.selected_channel_ids:
            names = []
            for cid in parent_view.selected_channel_ids:
                ch = next((c for c in parent_view.all_channels if str(c.id) == cid), None)
                names.append(ch.name if ch else cid)
            self.channels_input.default = ", ".join(names)[:1500]

    async def on_submit(self, interaction: discord.Interaction):
        matched = parse_channel_inputs(
            interaction.guild,
            self.channels_input.value,
            channels_pool=self.parent_view.all_channels
        )
        if not matched:
            return await interaction.response.send_message(
                "❌ Aucun salon trouvé avec ces noms. Vérifiez l'orthographe (séparez plusieurs salons par des virgules).",
                ephemeral=True
            )

        # On fusionne ou met à jour la sélection
        self.parent_view.selected_channel_ids = [str(ch.id) for ch in matched]
        self.parent_view.rebuild_components()
        await interaction.response.edit_message(
            content=self.parent_view.build_status_text(),
            view=self.parent_view
        )


class ManualSetupInteractiveView(SafeSalonView):
    """Vue graphique complète en mode manuel : affiche TOUS les salons de toutes les catégories (jusqu'à 75 par page + pagination + saisie texte)."""

    def __init__(self, author_id: int, all_categories: list[discord.CategoryChannel], all_channels: list[discord.abc.GuildChannel]):
        super().__init__(timeout=300)
        self.author_id = author_id
        self.all_categories = all_categories
        self.all_channels = all_channels
        self.cat_map = {c.id: c.name for c in all_categories}
        self.selected_channel_ids: list[str] = []
        self.page = 0
        self.per_page = 75  # 3 menus déroulants de 25 salons = 75 salons affichés simultanément !
        self.rebuild_components()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Seul l'administrateur ayant lancé cette configuration peut l'utiliser.", ephemeral=True)
            return False
        return True

    def build_status_text(self) -> str:
        total_ch = len(self.all_channels)
        total_pages = max(1, (total_ch - 1) // self.per_page + 1)
        header = (
            f"✍️ **Configuration Manuelle des Salons** ({total_ch} salons récupérés sur le serveur)\n"
            f"👉 Cochez les salons dans le(s) menu(s) ci-dessous **OU** cliquez sur **⌨️ Écrire les noms** pour les saisir directement.\n"
        )
        if total_pages > 1:
            header += f"📄 **Page {self.page + 1}/{total_pages}**\n"

        if self.selected_channel_ids:
            mentions = ", ".join(f"<#{cid}>" for cid in self.selected_channel_ids[:30])
            extra = f" *(+{len(self.selected_channel_ids) - 30} autres)*" if len(self.selected_channel_ids) > 30 else ""
            header += f"✅ **Salons sélectionnés ({len(self.selected_channel_ids)}) :** {mentions}{extra}"
        else:
            header += "ℹ️ *Aucun salon sélectionné pour le moment.*"
        return header

    def rebuild_components(self):
        self.clear_items()

        start_idx = self.page * self.per_page
        page_channels = self.all_channels[start_idx:start_idx + self.per_page]

        # Découper en tranches de 25 salons (jusqu'à 3 menus sur les lignes 0, 1, 2)
        chunks = [page_channels[i:i + 25] for i in range(0, len(page_channels), 25)]

        for row_idx, chunk in enumerate(chunks[:3]):
            chunk_ids = {str(ch.id) for ch in chunk}
            options = []
            for ch in chunk:
                cat_name = self.cat_map.get(getattr(ch, "category_id", None), "Sans catégorie")
                icon = "🔊" if isinstance(ch, (discord.VoiceChannel, discord.StageChannel)) else "#"
                options.append(discord.SelectOption(
                    label=f"{icon}{ch.name}"[:100],
                    value=str(ch.id),
                    description=f"📁 {cat_name}"[:100],
                    default=(str(ch.id) in self.selected_channel_ids)
                ))

            first_num = start_idx + row_idx * 25 + 1
            last_num = first_num + len(chunk) - 1
            select = discord.ui.Select(
                placeholder=f"✍️ Salons {first_num} à {last_num} (sur {len(self.all_channels)})...",
                min_values=0,
                max_values=len(options),
                options=options,
                row=row_idx
            )

            def make_chunk_callback(c_select: discord.ui.Select, c_ids: set[str]):
                async def _callback(interaction: discord.Interaction):
                    # Conserver les sélections des autres menus/pages et mettre à jour cette tranche
                    kept = [cid for cid in self.selected_channel_ids if cid not in c_ids]
                    self.selected_channel_ids = kept + list(c_select.values)
                    self.rebuild_components()
                    await interaction.response.edit_message(content=self.build_status_text(), view=self)
                return _callback

            select.callback = make_chunk_callback(select, chunk_ids)
            self.add_item(select)

        # Ligne 3 : Pagination si > 75 salons
        total_pages = max(1, (len(self.all_channels) - 1) // self.per_page + 1)
        if total_pages > 1:
            prev_btn = discord.ui.Button(
                label="◀ Salons préc.",
                style=discord.ButtonStyle.secondary,
                disabled=(self.page <= 0),
                row=3
            )
            next_btn = discord.ui.Button(
                label="Salons suiv. ▶",
                style=discord.ButtonStyle.secondary,
                disabled=(self.page >= total_pages - 1),
                row=3
            )

            async def on_prev(interaction: discord.Interaction):
                self.page = max(0, self.page - 1)
                self.rebuild_components()
                await interaction.response.edit_message(content=self.build_status_text(), view=self)

            async def on_next(interaction: discord.Interaction):
                self.page = min(total_pages - 1, self.page + 1)
                self.rebuild_components()
                await interaction.response.edit_message(content=self.build_status_text(), view=self)

            prev_btn.callback = on_prev
            next_btn.callback = on_next
            self.add_item(prev_btn)
            self.add_item(next_btn)

        # Ligne 4 : Actions principales
        confirm_btn = discord.ui.Button(
            label=f"Valider et Enregistrer ({len(self.selected_channel_ids)})",
            style=discord.ButtonStyle.success,
            emoji="✅",
            row=4
        )
        confirm_btn.callback = self.on_confirm
        self.add_item(confirm_btn)

        modal_btn = discord.ui.Button(
            label="Écrire les noms",
            style=discord.ButtonStyle.primary,
            emoji="⌨️",
            row=4
        )
        modal_btn.callback = self.on_open_modal
        self.add_item(modal_btn)

        if self.selected_channel_ids:
            clear_btn = discord.ui.Button(
                label="Tout décocher",
                style=discord.ButtonStyle.secondary,
                emoji="🧹",
                row=4
            )
            clear_btn.callback = self.on_clear_selection
            self.add_item(clear_btn)

        cancel_btn = discord.ui.Button(
            label="Annuler",
            style=discord.ButtonStyle.secondary,
            emoji="❌",
            row=4
        )
        cancel_btn.callback = self.on_cancel
        self.add_item(cancel_btn)

    async def on_open_modal(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ManualChannelTextModal(self))

    async def on_clear_selection(self, interaction: discord.Interaction):
        self.selected_channel_ids = []
        self.rebuild_components()
        await interaction.response.edit_message(content=self.build_status_text(), view=self)

    async def on_confirm(self, interaction: discord.Interaction):
        if not self.selected_channel_ids:
            return await interaction.response.send_message("⚠️ Veuillez sélectionner au moins un salon.", ephemeral=True)

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

    async def on_cancel(self, interaction: discord.Interaction):
        await interaction.response.edit_message(content="❌ Configuration annulée.", embed=None, view=None)


class CategoryExcludeTextModal(discord.ui.Modal, title="⌨️ Saisir catégories et salons à exclure"):
    categories_input = discord.ui.TextInput(
        label="Catégories à inclure (ou 'toutes')",
        style=discord.TextStyle.short,
        placeholder="Ex: Salons textuels, tikets (ou 'toutes')",
        required=True,
        max_length=500
    )
    exclude_input = discord.ui.TextInput(
        label="Salons à exclure (noms ou IDs, toute catég.)",
        style=discord.TextStyle.paragraph,
        placeholder="Ex: général, demo, bot-test, captcha (laisser vide si aucune exclusion)",
        required=False,
        max_length=1500
    )

    def __init__(self, parent_view: "CategorySetupInteractiveView"):
        super().__init__()
        self.parent_view = parent_view
        if parent_view.selected_categories:
            self.categories_input.default = ", ".join(c.name for c in parent_view.selected_categories)[:500]
        if parent_view.excluded_channel_ids:
            excl_names = []
            for eid in parent_view.excluded_channel_ids:
                ch = next((c for c in parent_view.all_channels if str(c.id) == eid), None)
                excl_names.append(ch.name if ch else eid)
            self.exclude_input.default = ", ".join(excl_names)[:1500]

    async def on_submit(self, interaction: discord.Interaction):
        cats = parse_category_inputs(
            interaction.guild,
            self.categories_input.value,
            categories_list=self.parent_view.all_categories
        )
        if not cats:
            return await interaction.response.send_message(
                "❌ Aucune catégorie valide trouvée avec ce nom. Vérifiez l'orthographe ou tapez `toutes`.",
                ephemeral=True
            )

        self.parent_view.selected_categories = cats
        channels_in_cats = get_channels_for_categories(cats, self.parent_view.all_channels)

        if self.exclude_input.value and self.exclude_input.value.strip():
            # Cherche d'abord dans les catégories sélectionnées, puis dans tout le serveur si besoin
            excl_matched = parse_channel_inputs(
                interaction.guild,
                self.exclude_input.value,
                channels_pool=channels_in_cats if channels_in_cats else self.parent_view.all_channels
            )
            self.parent_view.excluded_channel_ids = [str(ch.id) for ch in excl_matched]
        else:
            self.parent_view.excluded_channel_ids = []

        self.parent_view.exclude_page = 0
        self.parent_view.rebuild_components()
        await interaction.response.edit_message(
            content=self.parent_view.build_status_text(),
            view=self.parent_view
        )


class CategorySetupInteractiveView(SafeSalonView):
    """
    Vue graphique complète en mode Catégories :
    - Récupère toutes les catégories et tous leurs salons depuis l'API Discord.
    - Affiche jusqu'à 3 menus déroulants d'exclusion simultanés (75 salons visibles d'un coup) + pagination si > 75 salons.
    - Conserve les sélections entre les menus et les catégories.
    - Propose un bouton '⌨️ Écrire les noms' (Modal) pour saisir directement les salons ou catégories par leur nom.
    """

    def __init__(self, author_id: int, all_categories: list[discord.CategoryChannel], all_channels: list[discord.abc.GuildChannel]):
        super().__init__(timeout=300)
        self.author_id = author_id
        self.all_categories = all_categories
        self.all_channels = all_channels
        self.cat_map = {c.id: c.name for c in all_categories}
        self.selected_categories: list[discord.CategoryChannel] = []
        self.excluded_channel_ids: list[str] = []
        self.exclude_page = 0
        self.per_page = 75  # 3 menus de 25 salons = 75 salons affichés par page
        self.rebuild_components()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Seul l'administrateur ayant lancé cette configuration peut l'utiliser.", ephemeral=True)
            return False
        return True

    def get_candidate_channels(self) -> list[discord.abc.GuildChannel]:
        return get_channels_for_categories(self.selected_categories, self.all_channels)

    def build_status_text(self) -> str:
        if not self.selected_categories:
            return (
                "📁 **Configuration par Catégories**\n"
                "1️⃣ Sélectionnez une ou plusieurs catégories dans le menu ci-dessous (ou cliquez sur **⌨️ Écrire les noms**)."
            )

        candidates = self.get_candidate_channels()
        cat_names = ", ".join(f"**{c.name}**" for c in self.selected_categories)
        eligible_count = sum(1 for ch in candidates if str(ch.id) not in self.excluded_channel_ids)

        msg = (
            f"📁 **Catégories sélectionnées ({len(self.selected_categories)}) :** {cat_names}\n"
            f"📊 **Salons trouvés dans ces catégories :** `{len(candidates)}` salon(s) au total (`{eligible_count}` éligibles, `{len(self.excluded_channel_ids)}` exclus)\n"
        )
        if self.excluded_channel_ids:
            excl_mentions = ", ".join(f"<#{eid}>" for eid in self.excluded_channel_ids[:25])
            extra = f" *(+{len(self.excluded_channel_ids) - 25} autres)*" if len(self.excluded_channel_ids) > 25 else ""
            msg += f"🚫 **Salons exclus :** {excl_mentions}{extra}\n"

        msg += "👉 *Cochez les salons à exclure dans le(s) menu(s) ci-dessous ou utilisez **⌨️ Écrire les noms**, puis cliquez sur **Valider**.*"
        return msg

    def rebuild_components(self):
        self.clear_items()

        # --- LIGNE 0 : Menu de sélection des catégories (StringSelect avec toutes les catégories récupérées) ---
        selected_cat_ids = {c.id for c in self.selected_categories}
        cat_options = [
            discord.SelectOption(
                label="🌟 Toutes les catégories du serveur",
                value="ALL_CATEGORIES",
                description=f"Inclure les {len(self.all_categories)} catégories du serveur",
                default=(len(self.all_categories) > 0 and len(selected_cat_ids) == len(self.all_categories))
            )
        ]

        for cat in self.all_categories[:24]:
            ch_count = sum(1 for ch in self.all_channels if getattr(ch, "category_id", None) == cat.id)
            cat_options.append(discord.SelectOption(
                label=f"📁 {cat.name}"[:100],
                value=str(cat.id),
                description=f"{ch_count} salon(s) dans cette catégorie"[:100],
                default=(cat.id in selected_cat_ids)
            ))

        cat_select = discord.ui.Select(
            placeholder="1️⃣ Choisissez une ou plusieurs catégories...",
            min_values=1,
            max_values=len(cat_options),
            options=cat_options,
            row=0
        )
        cat_select.callback = self.on_categories_selected
        self.add_item(cat_select)

        # --- LIGNES 1, 2, 3 : Menus déroulants d'exclusion (affiche TOUS les salons des catégories sélectionnées !) ---
        candidates = self.get_candidate_channels()
        if candidates:
            total_pages = max(1, (len(candidates) - 1) // self.per_page + 1)
            self.exclude_page = min(self.exclude_page, total_pages - 1)

            start_idx = self.exclude_page * self.per_page
            page_channels = candidates[start_idx:start_idx + self.per_page]
            chunks = [page_channels[i:i + 25] for i in range(0, len(page_channels), 25)]

            for idx, chunk in enumerate(chunks[:3]):
                chunk_ids = {str(ch.id) for ch in chunk}
                options = []
                for ch in chunk:
                    cat_name = self.cat_map.get(getattr(ch, "category_id", None), "Sans catégorie")
                    icon = "🔊" if isinstance(ch, (discord.VoiceChannel, discord.StageChannel)) else "#"
                    options.append(discord.SelectOption(
                        label=f"{icon}{ch.name}"[:100],
                        value=str(ch.id),
                        description=f"📁 {cat_name}"[:100],
                        default=(str(ch.id) in self.excluded_channel_ids)
                    ))

                first_num = start_idx + idx * 25 + 1
                last_num = first_num + len(chunk) - 1
                if len(chunks) == 1 and total_pages == 1:
                    ph = f"2️⃣ (Optionnel) Exclure des salons ({len(candidates)} disponibles)..."
                else:
                    # Indiquer les catégories présentes dans cette tranche pour repérage immédiat
                    chunk_cats = list(dict.fromkeys(self.cat_map.get(getattr(c, "category_id", None), "") for c in chunk))
                    cats_hint = ", ".join(c for c in chunk_cats if c)[:40]
                    ph = f"2️⃣ Exclure salons {first_num}-{last_num}/{len(candidates)} ({cats_hint})..."[:100]

                excl_select = discord.ui.Select(
                    placeholder=ph,
                    min_values=0,
                    max_values=len(options),
                    options=options,
                    row=idx + 1
                )

                def make_excl_callback(e_select: discord.ui.Select, c_ids: set[str]):
                    async def _callback(interaction: discord.Interaction):
                        kept = [eid for eid in self.excluded_channel_ids if eid not in c_ids]
                        self.excluded_channel_ids = kept + list(e_select.values)
                        self.rebuild_components()
                        await interaction.response.edit_message(content=self.build_status_text(), view=self)
                    return _callback

                excl_select.callback = make_excl_callback(excl_select, chunk_ids)
                self.add_item(excl_select)

        # --- LIGNE 4 : Boutons d'action (Valider, Écrire les noms, Pagination si > 75 salons, Annuler) ---
        confirm_btn = discord.ui.Button(
            label="Valider et Enregistrer",
            style=discord.ButtonStyle.success,
            emoji="✅",
            disabled=(len(self.selected_categories) == 0),
            row=4
        )
        confirm_btn.callback = self.on_confirm
        self.add_item(confirm_btn)

        modal_btn = discord.ui.Button(
            label="Écrire les noms",
            style=discord.ButtonStyle.primary,
            emoji="⌨️",
            row=4
        )
        modal_btn.callback = self.on_open_modal
        self.add_item(modal_btn)

        if len(candidates) > self.per_page:
            total_pages = max(1, (len(candidates) - 1) // self.per_page + 1)
            prev_btn = discord.ui.Button(
                label=f"◀ Page {self.exclude_page + 1}/{total_pages}",
                style=discord.ButtonStyle.secondary,
                disabled=(self.exclude_page <= 0),
                row=4
            )
            next_btn = discord.ui.Button(
                label="Page suiv. ▶",
                style=discord.ButtonStyle.secondary,
                disabled=(self.exclude_page >= total_pages - 1),
                row=4
            )

            async def on_prev(interaction: discord.Interaction):
                self.exclude_page = max(0, self.exclude_page - 1)
                self.rebuild_components()
                await interaction.response.edit_message(content=self.build_status_text(), view=self)

            async def on_next(interaction: discord.Interaction):
                self.exclude_page = min(total_pages - 1, self.exclude_page + 1)
                self.rebuild_components()
                await interaction.response.edit_message(content=self.build_status_text(), view=self)

            prev_btn.callback = on_prev
            next_btn.callback = on_next
            self.add_item(prev_btn)
            self.add_item(next_btn)

        cancel_btn = discord.ui.Button(
            label="Annuler",
            style=discord.ButtonStyle.secondary,
            emoji="❌",
            row=4
        )
        cancel_btn.callback = self.on_cancel
        self.add_item(cancel_btn)

    async def on_categories_selected(self, interaction: discord.Interaction):
        values = interaction.data.get("values", [])
        if "ALL_CATEGORIES" in values:
            self.selected_categories = list(self.all_categories)
        else:
            chosen_ids = {int(v) for v in values if v.isdigit()}
            self.selected_categories = [c for c in self.all_categories if c.id in chosen_ids]

        # Nettoyer les exclusions qui ne font plus partie des catégories sélectionnées
        valid_candidate_ids = {str(ch.id) for ch in self.get_candidate_channels()}
        self.excluded_channel_ids = [eid for eid in self.excluded_channel_ids if eid in valid_candidate_ids]
        self.exclude_page = 0

        self.rebuild_components()
        await interaction.response.edit_message(content=self.build_status_text(), view=self)

    async def on_open_modal(self, interaction: discord.Interaction):
        await interaction.response.send_modal(CategoryExcludeTextModal(self))

    async def on_confirm(self, interaction: discord.Interaction):
        if not self.selected_categories:
            return await interaction.response.send_message("⚠️ Veuillez sélectionner au moins une catégorie.", ephemeral=True)

        guild = interaction.guild
        user = interaction.user

        candidates = self.get_candidate_channels()
        resulting_channels = [ch for ch in candidates if str(ch.id) not in self.excluded_channel_ids]

        if not resulting_channels:
            return await interaction.response.send_message(
                "⚠️ Aucun salon actif ne reste après exclusion. Veuillez laisser au moins un salon éligible.",
                ephemeral=True
            )

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

        embed = discord.Embed(
            title="✅ Configuration enregistrée avec succès !",
            description="La liste des salons pour la commande `/salon` a été mise à jour en mode **Catégories**.",
            color=discord.Color.green()
        )
        embed.add_field(name="📌 Mode", value="`📁 Par Catégories`", inline=True)
        embed.add_field(name="📁 Catégories incluses", value=", ".join(f"**{c.name}**" for c in self.selected_categories)[:1024], inline=True)

        excl_str = ", ".join(f"<#{cid}>" for cid in self.excluded_channel_ids) if self.excluded_channel_ids else "Aucun"
        embed.add_field(name=f"🚫 Salons exclus ({len(self.excluded_channel_ids)})", value=excl_str[:1024], inline=False)

        res_str = ", ".join(str(ch.mention) for ch in resulting_channels) if resulting_channels else "⚠️ Aucun salon actif"
        embed.add_field(name=f"💬 Salons éligibles ({len(resulting_channels)})", value=res_str[:1024], inline=False)
        embed.set_footer(text=f"Configuré par {user.display_name}")

        await interaction.response.edit_message(content=None, embed=embed, view=None)

    async def on_cancel(self, interaction: discord.Interaction):
        await interaction.response.edit_message(content="❌ Configuration annulée.", embed=None, view=None)


class SalonHubView(SafeSalonView):
    def __init__(self, author_id: int):
        super().__init__(timeout=180)
        self.author_id = author_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Seul l'administrateur ayant lancé cette commande peut interagir.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Par Catégories", style=discord.ButtonStyle.primary, emoji="📁", row=0)
    async def mode_categories_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        all_cats, all_chs = await fetch_all_guild_channels(interaction.guild)
        view = CategorySetupInteractiveView(self.author_id, all_cats, all_chs)
        await interaction.edit_original_response(content=view.build_status_text(), embed=None, view=view)

    @discord.ui.button(label="Sélection Manuelle", style=discord.ButtonStyle.secondary, emoji="✍️", row=0)
    async def mode_manual_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        all_cats, all_chs = await fetch_all_guild_channels(interaction.guild)
        view = ManualSetupInteractiveView(self.author_id, all_cats, all_chs)
        await interaction.edit_original_response(content=view.build_status_text(), embed=None, view=view)

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

        chosen_channel = random.choice(available_channels)
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
                    "• **📁 Par Catégories** : Récupère toutes les catégories et affiche **tous leurs salons** (avec possibilité d'exclure via menu déroulant ou en tapant leur nom).\n"
                    "• **✍️ Sélection Manuelle** : Affiche tous les salons du serveur par catégorie ou permet de taper leurs noms directement.\n"
                    "• **🗑️ Réinitialiser** : Effacer la configuration existante."
                ),
                color=discord.Color.blue()
            )
            embed.set_footer(text="Fern 🌿 • Configuration des salons")
            view = SalonHubView(user.id)
            return await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

        # Récupération complète des salons du serveur depuis l'API Discord
        await interaction.response.defer(ephemeral=True)
        all_cats, all_chs = await fetch_all_guild_channels(guild)

        # CAS 2 : Mode Manuel
        if (categorie and categorie.strip().lower() == "manuel") or (not categorie and salons):
            if salons:
                target_channels = parse_channel_inputs(guild, salons, channels_pool=all_chs)
                if not target_channels:
                    return await interaction.followup.send(
                        "❌ Aucun salon valide n'a été reconnu dans votre saisie.\n"
                        "Veuillez saisir les noms des salons (ex: `général, gaming`) ou leurs IDs.",
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
                    return await interaction.followup.send("❌ Erreur lors de l'enregistrement en base de données.", ephemeral=True)

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

                return await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                view = ManualSetupInteractiveView(user.id, all_cats, all_chs)
                return await interaction.followup.send(
                    content=view.build_status_text(),
                    view=view,
                    ephemeral=True
                )

        # CAS 3 : Mode Catégories (avec ou sans exclusions)
        categories_found = parse_category_inputs(guild, categorie, categories_list=all_cats)
        if not categories_found:
            return await interaction.followup.send(
                f"❌ Aucune catégorie valide correspondant à `{categorie}` n'a été trouvée sur ce serveur.",
                ephemeral=True
            )

        cat_ids = [str(c.id) for c in categories_found]
        candidate_channels = get_channels_for_categories(categories_found, all_chs)

        excluded_channels = parse_channel_inputs(guild, exclure, channels_pool=candidate_channels or all_chs) if exclure else []
        excluded_ids = [str(ch.id) for ch in excluded_channels]

        resulting_channels = [ch for ch in candidate_channels if str(ch.id) not in excluded_ids]

        if not resulting_channels:
            return await interaction.followup.send(
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
            return await interaction.followup.send("❌ Erreur lors de l'enregistrement en base de données.", ephemeral=True)

        embed = discord.Embed(
            title="✅ Configuration enregistrée avec succès !",
            description="La liste des salons pour `/salon` a été mise à jour en mode **Catégories**.",
            color=discord.Color.green()
        )
        embed.add_field(name="📌 Mode", value="`📁 Par Catégories`", inline=True)
        embed.add_field(name="📁 Catégories incluses", value=", ".join(f"**{c.name}**" for c in categories_found)[:1024], inline=True)

        excl_str = ", ".join(str(ch.mention) for ch in excluded_channels) if excluded_channels else "Aucun"
        embed.add_field(name="🚫 Salons exclus", value=excl_str[:1024], inline=False)

        res_str = ", ".join(str(ch.mention) for ch in resulting_channels)
        embed.add_field(name=f"💬 Salons éligibles au tirage ({len(resulting_channels)})", value=res_str[:1024], inline=False)
        embed.set_footer(text=f"Configuré par {user.display_name}")

        await interaction.followup.send(embed=embed, ephemeral=True)

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
            value="`📁 Par Catégories`" if mode == "CATEGORIES" else "`✍️ Manuel`",
            inline=True
        )

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

        res_mentions = ", ".join(str(ch.mention) for ch in available_channels) if available_channels else "⚠️ Aucun salon actif"
        embed.add_field(
            name=f"🎲 Salons actuellement éligibles au tirage ({len(available_channels)})",
            value=res_mentions[:1024],
            inline=False
        )

        updater_id = settings.get("last_updated_by_id", "0")
        updater_name = settings.get("last_updated_by_name", "Inconnu")
        updated_at_str = format_timestamp(settings.get("last_updated_at", ""))
        embed.add_field(
            name="👤 Dernière modification",
            value=f"• **Par :** <@{updater_id}> (`{updater_name}`)\n• **Date :** {updated_at_str}",
            inline=False
        )

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
