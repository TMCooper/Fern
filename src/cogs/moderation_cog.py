import discord, os, json, random, re
from urllib.parse import urlparse
from discord import app_commands
from discord.ext import commands
from src.db import Database, Utils
from src.BanListPagination import BanListPagination
from datetime import datetime

# --- CONFIGURATION DES AUTOCOMPLETES ---
async def ban_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    members = Database.search_members(interaction.guild.id, current)
    return [
        app_commands.Choice(
            name=f"{m['display_name'] or m['username']} ({m['username']}) — ID: {m['user_id']}", 
            value=str(m['user_id'])
        )
        for m in members
    ][:25]

async def unban_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    banned_members = Database.search_banned_members(interaction.guild.id, current)
    return [
        app_commands.Choice(
            name=f"{m['username']} — ID: {m['user_id']}", 
            value=str(m['user_id'])
        )
        for m in banned_members
    ][:25]

class ModerationCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        # Les context menus ne peuvent pas être définis avec un décorateur dans un Cog.
        # On les enregistre manuellement dans le command tree.
        self.ban_and_delete_ctx_menu = app_commands.ContextMenu(
            name="Bannir et Supprimer",
            callback=self.ban_and_delete,
        )
        self.bot.tree.add_command(self.ban_and_delete_ctx_menu)

        self.archive_url_and_delete_ctx_menu = app_commands.ContextMenu(
                    name="Supprimer et Achiver l'url",
                    callback=self.archive_and_delete,
        )
        self.bot.tree.add_command(self.archive_url_and_delete_ctx_menu)

    async def archive_and_delete(self, interaction: discord.Interaction, message: discord.Message):
            if not interaction.user.guild_permissions.manage_messages:
                return await interaction.response.send_message("Vous n'avez pas la permission de faire cela.", ephemeral=True)

            models = r'(https?://[^\s<>]+)' 
            resultats = re.findall(models, message.content)
            
            if resultats:
                ajouts_reussis = 0
                
                # On boucle bêtement sur tous les liens trouvés
                for url in resultats:
                    success, msg = Database.ban_url(
                        str(message.guild.id), 
                        str(message.author.id), 
                        str(interaction.user.id), 
                        url
                    )
                    if success:
                        ajouts_reussis += 1
                
                # On supprime le message
                try:
                    await message.delete()
                    await interaction.response.send_message(f"Le message a été supprimé. {ajouts_reussis} lien(s) ajouté(s) à la blacklist.", ephemeral=True)
                except discord.Forbidden:
                    await interaction.response.send_message("Les liens ont été bannis, mais je n'ai pas la permission de supprimer le message.", ephemeral=True)
                except Exception as e:
                    await interaction.response.send_message(f"Erreur lors de la suppression : {e}", ephemeral=True)

            else:
                return await interaction.response.send_message("Le message que vous tentez de supprimer ne contient pas de lien.", ephemeral=True)

    async def cog_unload(self):
        self.bot.tree.remove_command(self.ban_and_delete_ctx_menu.name, type=self.ban_and_delete_ctx_menu.type)

    async def ban_and_delete(self, interaction: discord.Interaction, message: discord.Message):
        # Vérification manuelle des permissions
        if not interaction.user.guild_permissions.manage_messages:
            return await interaction.response.send_message("Vous n'avez pas la permission de faire cela.", ephemeral=True)

        hashes_found = []
        for attachment in message.attachments:
            if attachment.content_type and attachment.content_type.startswith('image/'):
                try:
                    file_hash = await Utils.get_image_hash(attachment)
                    hashes_found.append(file_hash)
                except:
                    continue

        str_hashes = ",".join(hashes_found) if hashes_found else ""

        success, msg = Database.database_incrementation(
            interaction.guild.id,
            interaction.guild.name,
            message.content,
            message.author.name,
            message.author.id,
            interaction.user.name,
            interaction.user.id,
            str_hashes,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
        
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

    @app_commands.command(name="ban_texte", description="Ajoute manuellement un texte à la base de données des messages interdits")
    @app_commands.describe(texte="Le texte à bannir")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def ban_texte(self, interaction: discord.Interaction, texte: str):
        success, msg = Database.database_incrementation(
            interaction.guild.id,
            interaction.guild.name,
            texte,
            "Ajout Manuel",
            "0",
            interaction.user.name,
            interaction.user.id,
            "",
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
        if success:
            await interaction.response.send_message("Le texte a été ajouté à la base de données des messages interdits.", ephemeral=True)
        else:
            await interaction.response.send_message(f"Impossible d'ajouter : {msg}", ephemeral=True)

    @app_commands.command(name="setup_alerts", description="Configure le salon et le rôle pour les alertes de modération")
    @app_commands.describe(channel="Le salon où envoyer les alertes", role="Le rôle à mentionner (ping)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def setup_alerts(self, interaction: discord.Interaction, channel: discord.TextChannel, role: discord.Role):
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

    @app_commands.command(name="champignon_setup", description="Configure les rôles pour la loterie champignon")
    @app_commands.describe(role_cible="Le rôle parmi lequel tirer au sort", role_recompense="Le rôle à donner a la personne tirer au sort")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def champ_setup(self, interaction: discord.Interaction, role_cible: discord.Role, role_recompense: discord.Role):
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
            
        data[guild_id]["champignon_role_cible_id"] = role_cible.id
        data[guild_id]["champignon_role_recompense_id"] = role_recompense.id

        try:
            with open(config_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            
            await interaction.response.send_message(
                f"✅ Configuration réussie :\n"
                f"• Rôle ciblé : {role_cible.mention}\n"
                f"• Rôle récompense : {role_recompense.mention}",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(f"Erreur lors de l'écriture du fichier : {e}", ephemeral=True)

    @app_commands.command(name="champignon", description="Tire au sort un membre et lui donne le rôle récompense")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def champignon(self, interaction: discord.Interaction):
        config_file = "config.json"
        if not os.path.exists(config_file):
            return await interaction.response.send_message("Le bot n'est pas encore configuré sur ce serveur.", ephemeral=True)
            
        with open(config_file, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                data = {}
                
        guild_id = str(interaction.guild.id)
        if guild_id not in data or "champignon_role_cible_id" not in data[guild_id] or "champignon_role_recompense_id" not in data[guild_id]:
            return await interaction.response.send_message("Les rôles champignon ne sont pas configurés. Utilisez `/champignon_setup`.", ephemeral=True)
            
        role_cible_id = data[guild_id]["champignon_role_cible_id"]
        role_recompense_id = data[guild_id]["champignon_role_recompense_id"]
        
        role_cible = interaction.guild.get_role(role_cible_id)
        role_recompense = interaction.guild.get_role(role_recompense_id)
        
        if not role_cible or not role_recompense:
            return await interaction.response.send_message("L'un des rôles configurés n'existe plus sur le serveur.", ephemeral=True)
            
        members_with_role = role_cible.members
        if not members_with_role:
            return await interaction.response.send_message(f"Aucun membre ne possède le rôle {role_cible.name}.", ephemeral=True)
            
        winner = random.choice(members_with_role)
        
        try:
            await winner.add_roles(role_recompense)
            await interaction.response.send_message(f"Le grand gagnant est {winner.mention} ! Il a reçu le rôle {role_recompense.mention}.")
        except discord.Forbidden:
            await interaction.response.send_message(f"Le grand gagnant est {winner.mention} ! Erreur : Je n'ai pas les permissions pour lui donner le rôle {role_recompense.name}.")
        except Exception as e:
            await interaction.response.send_message(f"Le grand gagnant est {winner.mention} ! Erreur lors de l'ajout du rôle : {e}")

    @app_commands.command(name="roulette_setup", description="Configure le rôle pour la commande roulette")
    @app_commands.describe(role_cible="Le rôle parmi lequel tirer au sort")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def roulette_setup(self, interaction: discord.Interaction, role_cible: discord.Role):
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
            
        data[guild_id]["roulette_role_cible_id"] = role_cible.id

        try:
            with open(config_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            
            await interaction.response.send_message(
                f"Configuration de la roulette réussie :\n"
                f"• Rôle ciblé : {role_cible.mention}",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(f"Erreur lors de l'écriture du fichier : {e}", ephemeral=True)

    @app_commands.command(name="roulette", description="Tire au sort un membre ayant le rôle configuré et le mentionne")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def roulette(self, interaction: discord.Interaction):
        config_file = "config.json"
        if not os.path.exists(config_file):
            return await interaction.response.send_message("Le bot n'est pas encore configuré sur ce serveur.", ephemeral=True)
            
        with open(config_file, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                data = {}
                
        guild_id = str(interaction.guild.id)
        if guild_id not in data or "roulette_role_cible_id" not in data[guild_id]:
            return await interaction.response.send_message("Le rôle pour la roulette n'est pas configuré. Utilisez `/roulette_setup`.", ephemeral=True)
            
        role_cible_id = data[guild_id]["roulette_role_cible_id"]
        
        role_cible = interaction.guild.get_role(role_cible_id)
        
        if not role_cible:
            return await interaction.response.send_message("Le rôle configuré n'existe plus sur le serveur.", ephemeral=True)
            
        members_with_role = role_cible.members
        if not members_with_role:
            return await interaction.response.send_message(f"Aucun membre ne possède le rôle {role_cible.name}.", ephemeral=True)
            
        winner = random.choice(members_with_role)
        
        await interaction.response.send_message(f"La roulette a tourné... et s'arrête sur {winner.mention} !")

    @app_commands.command(name="ban", description="Bannir un membre (présent ou ayant quitté le serveur).")
    @app_commands.autocomplete(user_id=ban_autocomplete)
    @app_commands.describe(user_id="Le membre ou l'ID à bannir", reason="Raison du bannissement")
    @app_commands.checks.has_permissions(ban_members=True)
    async def ban_member(self, interaction: discord.Interaction, user_id: str, reason: str = "Aucune raison fournie"):
        await interaction.response.defer()
        try:
            user = await self.bot.fetch_user(int(user_id))
            await interaction.guild.ban(user, reason=reason)
            
            db_members = Database.search_members(interaction.guild.id, user_id)
            db_member = next((m for m in db_members if str(m['user_id']) == str(user_id)), None)
            username = db_member['username'] if db_member else user.name

            Database.add_ban(
                guild_id=interaction.guild.id,
                user_id=user_id,
                username=username,
                banned_by_name=interaction.user.name,
                banned_by_id=interaction.user.id,
                reason=reason
            )
            
            embed = discord.Embed(title="Membre Banni", color=discord.Color.red(), timestamp=datetime.now())
            if user.display_avatar:
                embed.set_thumbnail(url=user.display_avatar.url)
            embed.add_field(name="Utilisateur", value=f"{user.mention} (`{user.name}`)", inline=True)
            embed.add_field(name="ID", value=f"`{user_id}`", inline=True)
            embed.add_field(name="Modérateur", value=interaction.user.mention, inline=False)
            embed.add_field(name="Raison", value=f"*{reason}*", inline=False)
            
            await interaction.followup.send(embed=embed)
            
        except discord.Forbidden:
            await interaction.followup.send("Je n'ai pas les permissions nécessaires pour bannir cet utilisateur.", ephemeral=True)
        except (discord.NotFound, ValueError):
            await interaction.followup.send("Impossible de trouver cet utilisateur sur Discord.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Une erreur est survenue : {e}", ephemeral=True)

    @app_commands.command(name="unban", description="Débannir un membre via la base de données ou son ID.")
    @app_commands.autocomplete(user_id=unban_autocomplete)
    @app_commands.describe(user_id="Le membre banni ou son ID", reason="Raison du débannissement")
    @app_commands.checks.has_permissions(ban_members=True)
    async def unban_member(self, interaction: discord.Interaction, user_id: str, reason: str = "Aucune raison fournie"):
        await interaction.response.defer()
        try:
            user = await self.bot.fetch_user(int(user_id))
            await interaction.guild.unban(user, reason=reason)
            
            success = Database.remove_ban(
                guild_id=interaction.guild.id,
                user_id=user_id,
                unbanned_by_name=interaction.user.name,
                unbanned_by_id=interaction.user.id,
                unban_reason=reason
            )
            
            embed = discord.Embed(title="Membre Débanni", color=discord.Color.green(), timestamp=datetime.now())
            if user.display_avatar:
                embed.set_thumbnail(url=user.display_avatar.url)
            embed.add_field(name="Utilisateur", value=f"{user.mention} (`{user.name}`)", inline=True)
            embed.add_field(name="ID", value=f"`{user_id}`", inline=True)
            embed.add_field(name="Modérateur", value=interaction.user.mention, inline=False)
            embed.add_field(name="Raison du déban", value=f"*{reason}*", inline=False)
            
            if not success:
                embed.set_footer(text="Note: Ce ban n'était pas actif dans le registre persistant.")
                
            await interaction.followup.send(embed=embed)
            
        except discord.NotFound:
            await interaction.followup.send("Cet utilisateur n'est pas banni de ce serveur.", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("Je n'ai pas la permission de débannir des membres.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Une erreur est survenue : {e}", ephemeral=True)

    @app_commands.command(name="ban_list", description="Afficher la liste des membres actuellement bannis.")
    @app_commands.checks.has_permissions(ban_members=True)
    async def ban_list(self, interaction: discord.Interaction):
        bans = Database.get_all_active_bans(interaction.guild.id)
        view = BanListPagination(bans, per_page=5)
        await interaction.response.send_message(embed=view.get_embed(), view=view)

    @app_commands.command(name="ban_info", description="Voir les détails et la raison du bannissement d'un membre.")
    @app_commands.autocomplete(user_id=unban_autocomplete)
    @app_commands.describe(user_id="Le membre banni")
    @app_commands.checks.has_permissions(ban_members=True)
    async def ban_info(self, interaction: discord.Interaction, user_id: str):
        ban = Database.get_ban_info(interaction.guild.id, user_id)
        if not ban:
            return await interaction.response.send_message("Aucune information trouvée dans la base de données.", ephemeral=True)
        
        try:
            user = await self.bot.fetch_user(int(user_id))
            avatar_url = user.display_avatar.url if user.display_avatar else None
        except:
            avatar_url = None

        embed = discord.Embed(title=f"ℹ Infos Bannissement — {ban['username']}", color=discord.Color.orange())
        if avatar_url:
            embed.set_thumbnail(url=avatar_url)
            
        embed.add_field(name="Membre", value=f"<@{user_id}>", inline=True)
        embed.add_field(name="ID Utilisateur", value=f"`{user_id}`", inline=True)
        embed.add_field(name="Banni par", value=f"{ban['banned_by_name']} (<@{ban['banned_by_id']}>)", inline=False)
        embed.add_field(name="Date du ban", value=f"`{ban['banned_at']}`", inline=True)
        embed.add_field(name="Raison spécifiée", value=f"*{ban['reason']}*", inline=False)
        
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="vestige", description="Consulter l'historique complet des sanctions d'un utilisateur.")
    @app_commands.autocomplete(user_id=ban_autocomplete)
    @app_commands.describe(user_id="L'utilisateur à vérifier (sélectionne ou entre un ID)")
    @app_commands.checks.has_permissions(ban_members=True)
    async def vestige(self, interaction: discord.Interaction, user_id: str):
        await interaction.response.defer()
        
        history = Database.get_user_history(interaction.guild.id, user_id)
        
        try:
            user = await self.bot.fetch_user(int(user_id))
            username = user.name
            avatar_url = user.display_avatar.url if user.display_avatar else None
        except:
            username = history[0]['real_username'] if history else "Utilisateur Inconnu"
            avatar_url = None

        if not history:
            return await interaction.followup.send(f"Aucun historique de bannissement trouvé pour **{username}** (`{user_id}`).", ephemeral=True)
        
        total_bans = len(history)
        active_ban = next((b for b in history if b['is_active'] == 1), None)
        
        embed = discord.Embed(
            title=f"📜 Historique de Modération — {username}",
            description=f"**ID :** `{user_id}`\n**Nombre total de bans :** `{total_bans}`\n**Statut actuel :** {'🔴 Actuellement banni' if active_ban else '🟢 Non banni'}",
            color=discord.Color.orange(),
            timestamp=datetime.now()
        )
        if avatar_url:
            embed.set_thumbnail(url=avatar_url)
            
        for i, ban in enumerate(history[:5], 1):
            status_str = "🔴 [Toujours Actif]" if ban['is_active'] == 1 else "🟢 [Débanni]"
            
            ban_details = f"**Banni le :** `{ban['banned_at']}` par {ban['banned_by_name']}\n"
            ban_details += f"└ **Raison du ban :** *{ban['reason']}*\n"
            
            if ban['is_active'] == 0 and ban['unbanned_at']:
                ban_details += f"└ **Débanni le :** `{ban['unbanned_at']}` par {ban['unbanned_by_name']}\n"
                ban_details += f"└ **Raison du déban :** *{ban['unban_reason'] or 'Aucune raison'}*\n"
                
            embed.add_field(
                name=f"Sanction #{total_bans - i + 1} {status_str}",
                value=ban_details,
                inline=False
            )
            
        if total_bans > 5:
            embed.set_footer(text=f"Affichage des 5 bans les plus récents sur un total de {total_bans}.")
            
        await interaction.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(ModerationCog(bot))
