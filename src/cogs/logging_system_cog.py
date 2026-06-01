import discord, json, os
from discord import app_commands
from discord.ext import commands
from src.db import Database, Utils
from datetime import datetime, timezone

class LoggingSystemCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def get_author_type(self, message):
        if message.webhook_id:
            return "WEBHOOK"
        if message.author.bot:
            return "BOT"
        return "USER"

    async def send_public_log(self, guild, embed):
        config_file = "config.json"
        if os.path.exists(config_file):
            with open(config_file, "r", encoding="utf-8") as f:
                try:
                    data = json.load(f)
                    guild_id = str(guild.id)
                    if guild_id in data and "log_channel_id" in data[guild_id]:
                        channel_id = data[guild_id]["log_channel_id"]
                        channel = guild.get_channel(int(channel_id))
                        if channel:
                            await channel.send(embed=embed)
                except Exception as e:
                    print(f"Erreur send_public_log: {e}")

    # --- MESSAGE EVENTS ---
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.guild is None:
            return
            
        # Old code logic for checking duplicates
        current_hash = None
        if message.attachments:
            attachment = message.attachments[0]
            if attachment.content_type and attachment.content_type.startswith('image/'):
                current_hash = await Utils.get_image_hash(attachment)

        already_banned = Database.database_lookup(message.guild.id, message.content, current_hash)
        if already_banned:
            try:
                with open("config.json", "r") as f:
                    config = json.load(f)
                serv_id = str(message.guild.id)
                if serv_id in config and "channel_id" in config[serv_id]:
                    conf = config[serv_id]
                    target_channel = self.bot.get_channel(conf["channel_id"])
                    role_ping = f"<@&{conf['role_id']}>"
                    if target_channel:
                        jump_link = message.jump_url
                        await target_channel.send(
                            f"{role_ping} **Contenue déjà supprimé**\n"
                            f"**Auteur :** {message.author.mention} (`{message.author.id}`)\n"
                            f"**Salon :** {message.channel.mention}\n"
                            f"**Action :** [Cliquer ici pour voir le message]({jump_link})"
                        )
            except Exception as e:
                print(f"Erreur config on_message: {e}")

        # New Universal Logging
        Database.log_message(
            guild_id=message.guild.id,
            channel_id=message.channel.id,
            message_id=message.id,
            author_id=message.author.id,
            author_type=self.get_author_type(message),
            action="CREATE",
            content=message.content
        )

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if before.guild is None or before.content == after.content:
            return

        Database.log_message(
            guild_id=after.guild.id,
            channel_id=after.channel.id,
            message_id=after.id,
            author_id=after.author.id,
            author_type=self.get_author_type(after),
            action="EDIT",
            content=after.content,
            old_content=before.content
        )
        
        embed = discord.Embed(title="Message Modifié", color=discord.Color.yellow())
        embed.add_field(name="Auteur", value=after.author.mention, inline=True)
        embed.add_field(name="Salon", value=after.channel.mention, inline=True)
        embed.add_field(name="Avant", value=before.content or "*Vide*", inline=False)
        embed.add_field(name="Après", value=after.content or "*Vide*", inline=False)
        await self.send_public_log(after.guild, embed)

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        if message.guild is None:
            return

        Database.log_message(
            guild_id=message.guild.id,
            channel_id=message.channel.id,
            message_id=message.id,
            author_id=message.author.id,
            author_type=self.get_author_type(message),
            action="DELETE",
            content=message.content
        )
        
        embed = discord.Embed(title="Message Supprimé", color=discord.Color.red())
        embed.add_field(name="Auteur", value=message.author.mention, inline=True)
        embed.add_field(name="Salon", value=message.channel.mention, inline=True)
        embed.add_field(name="Contenu", value=message.content or "*Vide/Image*", inline=False)
        await self.send_public_log(message.guild, embed)

    # --- MODERATION EVENTS (AUDIT LOGS) ---
    @commands.Cog.listener()
    async def on_member_ban(self, guild, user):
        # Chercher dans l'audit log qui a fait le ban
        async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.ban):
            if entry.target.id == user.id:
                Database.log_moderation(
                    guild_id=guild.id,
                    action_type="BAN",
                    target_id=user.id,
                    actor_id=entry.user.id,
                    reason=entry.reason or "Aucune raison fournie",
                    details=f"Ban détecté via Audit Log (par {entry.user.name})"
                )
                break

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        # Check if it was a kick
        async for entry in member.guild.audit_logs(limit=1, action=discord.AuditLogAction.kick):
            if entry.target.id == member.id:
                Database.log_moderation(
                    guild_id=member.guild.id,
                    action_type="KICK",
                    target_id=member.id,
                    actor_id=entry.user.id,
                    reason=entry.reason or "Aucune raison fournie",
                    details=f"Kick détecté via Audit Log (par {entry.user.name})"
                )
                break

    # --- MEMBER STATE EVENTS ---
    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        if before.nick != after.nick:
            Database.log_member_state(after.guild.id, after.id, "NICKNAME_CHANGE", f"{before.nick} -> {after.nick}")
        
        if before.roles != after.roles:
            added_roles = [r for r in after.roles if r not in before.roles]
            removed_roles = [r for r in before.roles if r not in after.roles]
            if added_roles:
                Database.log_member_state(after.guild.id, after.id, "ROLE_ADD", f"Roles ajoutés: {', '.join(r.name for r in added_roles)}")
            if removed_roles:
                Database.log_member_state(after.guild.id, after.id, "ROLE_REMOVE", f"Roles retirés: {', '.join(r.name for r in removed_roles)}")

    # --- GUILD ENTITY EVENTS (ROLES / CHANNELS) ---
    @commands.Cog.listener()
    async def on_guild_role_create(self, role):
        data = json.dumps({"permissions": role.permissions.value, "position": role.position})
        Database.log_guild_entity(role.guild.id, "ROLE", role.id, "CREATE", role.name, data)

    @commands.Cog.listener()
    async def on_guild_role_update(self, before, after):
        if before.name != after.name or before.permissions != after.permissions or before.position != after.position:
            data = json.dumps({"permissions": after.permissions.value, "position": after.position})
            Database.log_guild_entity(after.guild.id, "ROLE", after.id, "UPDATE", after.name, data)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role):
        Database.log_guild_entity(role.guild.id, "ROLE", role.id, "DELETE", role.name)

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        data = json.dumps({"type": str(channel.type)})
        Database.log_guild_entity(channel.guild.id, "CHANNEL", channel.id, "CREATE", channel.name, data)

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before, after):
        if before.name != after.name:
            data = json.dumps({"type": str(after.type)})
            Database.log_guild_entity(after.guild.id, "CHANNEL", after.id, "UPDATE", after.name, data)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        Database.log_guild_entity(channel.guild.id, "CHANNEL", channel.id, "DELETE", channel.name)

    # --- COMMANDS ---
    @app_commands.command(name="setup_logs", description="Configure le salon pour les logs publics (éditions, suppressions de messages)")
    @app_commands.describe(channel="Le salon de logs")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def setup_logs(self, interaction: discord.Interaction, channel: discord.TextChannel):
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
            
        data[guild_id]["log_channel_id"] = channel.id

        try:
            with open(config_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            await interaction.response.send_message(f"Salon de logs configuré : {channel.mention}", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Erreur : {e}", ephemeral=True)

    @app_commands.command(name="user_full_report", description="Génère un rapport JSON complet sur un utilisateur d'après les logs")
    @app_commands.describe(user_id="ID de l'utilisateur")
    @app_commands.checks.has_permissions(administrator=True)
    async def user_full_report(self, interaction: discord.Interaction, user_id: str):
        await interaction.response.defer(ephemeral=True)
        report = Database.get_user_full_report(interaction.guild.id, user_id)
        if not report:
            return await interaction.followup.send("Aucune donnée trouvée ou erreur.", ephemeral=True)
            
        filename = f"report_{user_id}.json"
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=4, ensure_ascii=False)
            
        await interaction.followup.send(content=f"Voici le rapport complet pour l'utilisateur {user_id}:", file=discord.File(filename))
        os.remove(filename)

    @app_commands.command(name="sync_history", description="Synchronise les anciens messages des salons textuels dans la base de données")
    @app_commands.describe(limit="Nombre de messages par salon (laisser vide = tout récupérer)")
    @app_commands.checks.has_permissions(administrator=True)
    async def sync_history(self, interaction: discord.Interaction, limit: int = None):
        if limit is not None:
            desc = f"limite: {limit} msg/salon"
            fetch_limit = limit
        else:
            desc = "AUCUNE LIMITE — tous les messages seront récupérés"
            fetch_limit = None

        await interaction.response.send_message(
            f"⏳ Début de la synchronisation ({desc})...\nCela peut prendre **beaucoup** de temps.",
            ephemeral=True
        )
        
        count = 0
        channels_done = 0
        total_channels = len(interaction.guild.text_channels)

        for channel in interaction.guild.text_channels:
            try:
                async for msg in channel.history(limit=fetch_limit):
                    Database.log_message(
                        guild_id=msg.guild.id,
                        channel_id=msg.channel.id,
                        message_id=msg.id,
                        author_id=msg.author.id,
                        author_type=self.get_author_type(msg),
                        action="SYNC",
                        content=msg.content
                    )
                    count += 1
            except discord.Forbidden:
                pass
            except Exception as e:
                print(f"Erreur sync sur salon {channel.name}: {e}")
            
            channels_done += 1
            # Mise à jour de progression tous les 5 salons
            if channels_done % 5 == 0:
                try:
                    await interaction.edit_original_response(
                        content=f"⏳ Synchronisation en cours... {channels_done}/{total_channels} salons traités ({count} messages)"
                    )
                except:
                    pass
                
        await interaction.edit_original_response(
            content=f"✅ Synchronisation terminée ! {channels_done}/{total_channels} salons traités — **{count}** messages analysés/loggés."
        )

async def setup(bot):
    await bot.add_cog(LoggingSystemCog(bot))
