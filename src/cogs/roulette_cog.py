import discord
import random
from discord import app_commands
from discord.ext import commands
from src.db import Database

class RouletteCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    setup_group = app_commands.Group(name="setup_talents", description="Configuration de la roulette des talents (Admins)")

    @setup_group.command(name="init_defaults", description="Initialise les 19 talents par défaut et règle la limite max à 19")
    async def setup_init_defaults(self, interaction: discord.Interaction):
        if not interaction.guild:
            return await interaction.response.send_message("❌ Cette commande doit être exécutée dans un serveur.", ephemeral=True)
        if not interaction.user.guild_permissions.administrator and not interaction.user.guild_permissions.manage_guild:
            return await interaction.response.send_message("❌ Vous n'avez pas la permission de configurer la roulette.", ephemeral=True)

        success = Database.init_default_talents(interaction.guild.id)
        if success:
            await interaction.response.send_message(
                "✅ **Roulette des talents initialisée avec succès !**\n"
                "Les 19 talents par défaut ont été chargés et le roll max est configuré sur **19**.\n"
                "Vous pouvez à tout moment modifier ou ajouter un rôle Discord à un talent avec `/setup_talents set_talent`.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message("❌ Erreur lors de l'initialisation des talents par défaut.", ephemeral=True)

    @setup_group.command(name="set_max", description="Définit le chiffre maximum (roll de 0 à N) pour la roulette")
    @app_commands.describe(max_val="Le chiffre maximum N pour les tirages (ex: 19)")
    async def setup_set_max(self, interaction: discord.Interaction, max_val: int):
        if not interaction.guild:
            return await interaction.response.send_message("❌ Cette commande doit être exécutée dans un serveur.", ephemeral=True)
        if not interaction.user.guild_permissions.administrator and not interaction.user.guild_permissions.manage_guild:
            return await interaction.response.send_message("❌ Vous n'avez pas la permission de configurer la roulette.", ephemeral=True)

        if max_val < 0:
            return await interaction.response.send_message("❌ Le chiffre maximum doit être supérieur ou égal à 0.", ephemeral=True)

        success = Database.set_roulette_max_roll(interaction.guild.id, max_val)
        if success:
            await interaction.response.send_message(f"✅ La limite de roll est désormais configurée sur **0 à {max_val}**.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Erreur lors de la mise à jour du max roll.", ephemeral=True)

    @setup_group.command(name="set_talent", description="Ajoute ou modifie un talent pour un chiffre donné")
    @app_commands.describe(
        chiffre="Le chiffre associé au talent (0 à N)",
        description="Description complète du talent envoyée lors du tirage",
        role="Rôle Discord optionnel (son nom servira de titre si le nom n'est pas précisé)",
        nom="Titre / Nom optionnel du talent (si sans rôle ou pour personnaliser le titre)"
    )
    async def setup_set_talent(
        self,
        interaction: discord.Interaction,
        chiffre: int,
        description: str,
        role: discord.Role = None,
        nom: str = None
    ):
        if not interaction.guild:
            return await interaction.response.send_message("❌ Cette commande doit être exécutée dans un serveur.", ephemeral=True)
        if not interaction.user.guild_permissions.administrator and not interaction.user.guild_permissions.manage_guild:
            return await interaction.response.send_message("❌ Vous n'avez pas la permission de configurer la roulette.", ephemeral=True)

        if not nom:
            if role:
                nom = role.name
            else:
                nom = f"Talent #{chiffre}"

        role_id = str(role.id) if role else None
        success = Database.set_talent(interaction.guild.id, chiffre, nom, description, role_id=role_id)
        if success:
            role_msg = f" avec le rôle {role.mention}" if role else " (sans rôle Discord associé)"
            await interaction.response.send_message(
                f"✅ **Talent #{chiffre} enregistré !**\n"
                f"• **Titre :** {nom}\n"
                f"• **Description :** {description}\n"
                f"• **Rôle :** {role_msg}",
                ephemeral=True
            )
        else:
            await interaction.response.send_message("❌ Erreur lors de l'enregistrement du talent.", ephemeral=True)

    @setup_group.command(name="delete_talent", description="Supprime la configuration d'un talent pour un chiffre")
    @app_commands.describe(chiffre="Le chiffre du talent à supprimer")
    async def setup_delete_talent(self, interaction: discord.Interaction, chiffre: int):
        if not interaction.guild:
            return await interaction.response.send_message("❌ Cette commande doit être exécutée dans un serveur.", ephemeral=True)
        if not interaction.user.guild_permissions.administrator and not interaction.user.guild_permissions.manage_guild:
            return await interaction.response.send_message("❌ Vous n'avez pas la permission de configurer la roulette.", ephemeral=True)

        success = Database.delete_talent(interaction.guild.id, chiffre)
        if success:
            await interaction.response.send_message(f"🗑️ Le talent associant le chiffre **#{chiffre}** a été supprimé.", ephemeral=True)
        else:
            await interaction.response.send_message(f"⚠️ Aucun talent n'était configuré pour le chiffre **#{chiffre}**.", ephemeral=True)

    @setup_group.command(name="list", description="Affiche la liste de tous les talents configurés sur ce serveur")
    async def setup_list(self, interaction: discord.Interaction):
        if not interaction.guild:
            return await interaction.response.send_message("❌ Cette commande doit être exécutée dans un serveur.", ephemeral=True)

        max_roll = Database.get_roulette_max_roll(interaction.guild.id)
        talents = Database.get_all_talents(interaction.guild.id)

        if not talents:
            return await interaction.response.send_message(
                f"ℹ️ Aucun talent n'est actuellement configuré sur ce serveur (Roll max : 0 à {max_roll}).\n"
                f"Utilisez `/setup_talents init_defaults` pour charger les 19 talents par défaut.",
                ephemeral=True
            )

        embed = discord.Embed(
            title=f"📜 Configuration de la Roulette (0 à {max_roll})",
            description=f"Total de **{len(talents)}** talent(s) configuré(s) sur ce serveur.",
            color=discord.Color.purple()
        )

        for t in talents[:25]:
            role_text = f"<@&{t['role_id']}>" if t.get("role_id") else "*(aucun)*"
            desc_preview = t['description'] if len(t['description']) <= 120 else t['description'][:117] + "..."
            embed.add_field(
                name=f"#{t['number']} — {t['name']}",
                value=f"**Rôle :** {role_text}\n**Desc :** {desc_preview}",
                inline=False
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _execute_roll(self, interaction: discord.Interaction):
        if not interaction.guild:
            return await interaction.response.send_message("❌ Cette commande doit être utilisée dans un serveur.", ephemeral=True)

        guild_id = str(interaction.guild.id)
        max_roll = Database.get_roulette_max_roll(guild_id)
        roll = random.randint(0, max_roll)

        talent = Database.get_talent(guild_id, roll)

        # Enregistrer le tirage dans la DB
        Database.log_roulette_roll(
            guild_id,
            interaction.user.id,
            roll,
            talent["name"] if talent else None
        )

        embed = discord.Embed(
            title=f"🎰 Tirage de la Roulette : Chiffre {roll}",
            color=discord.Color.gold()
        )
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url if interaction.user.display_avatar else None)

        if talent:
            role_note = ""
            if talent.get("role_id"):
                try:
                    role = interaction.guild.get_role(int(talent["role_id"]))
                    if role:
                        if role not in interaction.user.roles:
                            await interaction.user.add_roles(role, reason=f"Roulette talent #{roll}")
                            role_note = f"\n\n✨ **Le rôle {role.mention} vous a été attribué !**"
                        else:
                            role_note = f"\n\nℹ️ *(Vous possédez déjà le rôle {role.mention})*"
                except Exception as e:
                    role_note = f"\n\n⚠️ *(Ne peux pas attribuer le rôle : {e})*"

            embed.description = (
                f"Tu as eu le chiffre **{roll}** !\n"
                f"Ton rôle/talent est : **{talent['name']}**\n\n"
                f"**Description :**\n{talent['description']}"
                f"{role_note}"
            )
        else:
            embed.description = f"Tu as eu le chiffre **{roll}**.\nAucun talent n'est actuellement associé à ce chiffre."

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="roll_talent", description="Faire tourner la roulette pour obtenir un chiffre et son talent (0 à N)")
    async def roll_talent(self, interaction: discord.Interaction):
        await self._execute_roll(interaction)

    @app_commands.command(name="talent_roulette", description="Faire tourner la roulette pour obtenir un chiffre et son talent (0 à N)")
    async def talent_roulette(self, interaction: discord.Interaction):
        await self._execute_roll(interaction)

async def setup(bot: commands.Bot):
    await bot.add_cog(RouletteCog(bot))
