import discord
from datetime import datetime

class BanListPagination(discord.ui.View):
    def __init__(self, bans, per_page=5):
        super().__init__(timeout=60)
        self.bans = bans
        self.per_page = per_page
        self.current_page = 0
        self.total_pages = max(1, (len(bans) - 1) // per_page + 1)
        self.update_buttons()

    def update_buttons(self):
        # Active/Désactive les boutons dynamiquement
        self.children[0].disabled = (self.current_page == 0)
        self.children[1].disabled = (self.current_page >= self.total_pages - 1)

    def get_embed(self):
        start = self.current_page * self.per_page
        end = start + self.per_page
        page_bans = self.bans[start:end]

        embed = discord.Embed(
            title="📋 Registre des Membres Bannis",
            color=discord.Color.red(),
            timestamp=datetime.now()
        )
        embed.set_footer(text=f"Page {self.current_page + 1}/{self.total_pages}")

        if not self.bans:
            embed.description = "*Aucun bannissement enregistré dans la base de données.*"
            return embed

        description = ""
        for i, ban in enumerate(page_bans, start=start + 1):
            description += f"**{i}. {ban['username']}**\n"
            description += f"└ **ID :** `{ban['user_id']}`\n"
            description += f"└ **Par :** {ban['banned_by_name']} | **Raison :** *{ban['reason']}*\n\n"
        
        embed.description = description
        return embed

    @discord.ui.button(label="◀ Précédent", style=discord.ButtonStyle.blurple)
    async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page -= 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @discord.ui.button(label="Suivant ▶", style=discord.ButtonStyle.blurple)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page += 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)