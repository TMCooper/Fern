import discord, os, asyncio
from discord import app_commands
from discord.ext import commands
from src.music import Music

class MusicCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="play", description="Joue une musique depuis YouTube")
    async def play(self, interaction: discord.Interaction, url: str):
        member = interaction.user

        # Vérification du salon vocal
        if not member.voice or not member.voice.channel:
            return await interaction.response.send_message(
                "Tu dois être dans un salon vocal", 
                ephemeral=True
            )

        # On "diffère" la réponse car le téléchargement peut prendre plus de 3 secondes
        await interaction.response.defer()

        vocal_channel = member.voice.channel
        vc = interaction.guild.voice_client

        # Connexion ou déplacement
        if vc:
            if vc.channel != vocal_channel:
                await vc.move_to(vocal_channel)
        else:
            vc = await vocal_channel.connect()

        try:
            title, file_path = await Music.download(url)

            # Lecture de l'audio
            if vc.is_playing():
                vc.stop()
            
            def after_playing(error):
                if error:
                    print(f"Erreur lors de la lecture : {error}")
                
                # On vérifie si le fichier existe et on le supprime
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                        print(f"Fichier supprimé : {file_path}")
                    except Exception as e:
                        print(f"Impossible de supprimer le fichier : {e}")

            vc.play(discord.FFmpegPCMAudio(file_path), after=after_playing)
            
            await interaction.followup.send(f"En train de jouer : **{title}**")

        except Exception as e:
            print(f"Erreur: {e}")
            await interaction.followup.send("Une erreur est survenue lors du téléchargement.")

    @app_commands.command(name="stop", description="Déconnecte le bot proprement")
    async def stop(self, interaction: discord.Interaction):
        vc = interaction.guild.voice_client
        
        if not vc:
            return await interaction.response.send_message("Je ne suis pas connecté à un salon vocal.", ephemeral=True)

        try:
            await interaction.response.send_message("Déconnexion en cours...")

            if vc.is_playing() or vc.is_paused():
                vc.stop()

            path_to_clean = getattr(vc, "current_file", None)

            await vc.disconnect()

            if path_to_clean and os.path.exists(path_to_clean):
                await asyncio.sleep(0.5)
                try:
                    os.remove(path_to_clean)
                    print(f"Fichier nettoyé : {path_to_clean}")
                except Exception as e:
                    print(f"Erreur nettoyage : {e}")

        except Exception as e:
            print(f"Erreur lors du stop : {e}")

            if not interaction.response.is_done():
                await interaction.response.send_message("Une erreur est survenue lors de la déconnexion.")

async def setup(bot):
    await bot.add_cog(MusicCog(bot))
