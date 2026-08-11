import os
import threading
from datetime import datetime, timezone
from flask import Flask, render_template, jsonify
import discord
from discord import app_commands
from discord.ext import commands

# --- Flask Server Setup ---
app = Flask(__name__)

# Main Dashboard (index.html)
@app.route('/')
def home():
    return render_template('index.html')

# Verification Page (verify.html)
@app.route('/verify')
def verify_page():
    return render_template('verify.html')

@app.route('/api/stats')
def stats():
    if bot.is_ready():
        return jsonify({
            "status": "Online",
            "guild_count": len(bot.guilds),
            "latency": round(bot.latency * 1000)
        })
    return jsonify({"status": "Starting...", "guild_count": 0, "latency": 0})

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# --- Discord Bot Setup ---
intents = discord.Intents.default()
intents.members = True

class DoubleCheckBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        # Sync slash commands globally when the bot starts
        print("Syncing slash commands...")
        await self.tree.sync()
        print("Slash commands synced successfully!")

bot = DoubleCheckBot()

# --- Slash Commands ---

# 1. /verify - Gives users a link to verify their account on Render
@bot.tree.command(name="verify", description="Get a verification link to gain access to the server.")
async def verify(interaction: discord.Interaction):
    render_url = os.environ.get("RENDER_EXTERNAL_URL", "https://your-app-name.onrender.com")
    verify_link = f"{render_url}/verify"

    embed = discord.Embed(
        title="🛡️ DoubleCheck Verification",
        description=f"Click the button below to verify your account and gain access to **{interaction.guild.name}**.",
        color=discord.Color.blue()
    )
    
    # Create an interactive web link button inside Discord
    view = discord.ui.View()
    button = discord.ui.Button(label="Verify Account", url=verify_link, style=discord.ButtonStyle.link)
    view.add_item(button)

    # ephemeral=True makes the message visible ONLY to the user running the command
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


# 2. /check-user - Allows moderators to manually inspect an account for alt indicators
@bot.tree.command(name="check-user", description="[Mods Only] Inspect an account for alt indicators.")
@app_commands.checks.has_permissions(ban_members=True)
async def check_user(interaction: discord.Interaction, member: discord.Member):
    account_age = (datetime.now(timezone.utc) - member.created_at).days
    join_age = (datetime.now(timezone.utc) - member.joined_at).days if member.joined_at else 0

    embed = discord.Embed(
        title=f"Security Scan: {member.display_name}",
        color=discord.Color.gold() if account_age < 7 else discord.Color.green()
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="User ID", value=f"`{member.id}`", inline=True)
    embed.add_field(name="Account Age", value=f"{account_age} days old", inline=True)
    embed.add_field(name="Joined Server", value=f"{join_age} days ago", inline=True)
    
    if account_age < 3:
        embed.add_field(name="⚠️ Risk Flag", value="Very fresh account! High likelihood of being an alt.", inline=False)
    else:
        embed.add_field(name="✅ Risk Flag", value="Account age meets standard threshold.", inline=False)

    await interaction.response.send_message(embed=embed, ephemeral=True)


# 3. /status - Check DoubleCheck system operational status
@bot.tree.command(name="status", description="Check the system status of DoubleCheck.")
async def status(interaction: discord.Interaction):
    latency = round(bot.latency * 1000)
    embed = discord.Embed(
        title="DoubleCheck Status",
        description=f"🟢 **System Operational**\n\n• **Latency:** {latency}ms\n• **Protected Guilds:** {len(bot.guilds)}",
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed)


# --- Error Handling for Slash Commands ---
@check_user.error
async def check_user_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("❌ You need the **Ban Members** permission to use this command.", ephemeral=True)


# --- Run Both Services ---
if __name__ == "__main__":
    server_thread = threading.Thread(target=run_flask)
    server_thread.daemon = True
    server_thread.start()

    token = os.environ.get("DISCORD_TOKEN")
    if token:
        bot.run(token)
    else:
        print("Error: DISCORD_TOKEN environment variable not set.")
