import os
import threading
from datetime import datetime, timezone
import requests
from flask import Flask, render_template, redirect, request, jsonify
import discord
from discord import app_commands
from discord.ext import commands

# -----------------------------------------------------------------------------
# 1. FLASK WEB SERVER SETUP
# -----------------------------------------------------------------------------
app = Flask(__name__)

# Fetch environment variables for OAuth2 and Bot
DISCORD_CLIENT_ID = os.environ.get("DISCORD_CLIENT_ID")
DISCORD_CLIENT_SECRET = os.environ.get("DISCORD_CLIENT_SECRET")
RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL", "https://doublecheck-pkoq.onrender.com")
REDIRECT_URI = f"{RENDER_URL}/auth/callback"

# Main Admin Dashboard (templates/index.html)
@app.route('/')
def home():
    return render_template('index.html')

# User Verification Landing Page (templates/verify.html)
@app.route('/verify')
def verify_page():
    return render_template('verify.html')

# Endpoint used by static/script.js to update the dashboard live
@app.route('/api/stats')
def stats():
    if bot.is_ready():
        return jsonify({
            "status": "Online",
            "guild_count": len(bot.guilds),
            "latency": round(bot.latency * 1000)
        })
    return jsonify({"status": "Starting...", "guild_count": 0, "latency": 0})

# --- DISCORD OAUTH2 FLOW ---

@app.route('/auth/login')
def auth_login():
    """Redirects the user to Discord's official OAuth authorization page."""
    discord_auth_url = (
        f"https://discord.com/api/oauth2/authorize"
        f"?client_id={DISCORD_CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}"
        f"&response_type=code"
        f"&scope=identify%20guilds.join"
    )
    return redirect(discord_auth_url)

@app.route('/auth/callback')
def auth_callback():
    """Handles the redirect from Discord after the user authorizes access."""
    code = request.args.get('code')
    if not code:
        return "Authorization failed: No authorization code provided.", 400

    # Exchange code for access token
    token_data = {
        'client_id': DISCORD_CLIENT_ID,
        'client_secret': DISCORD_CLIENT_SECRET,
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': REDIRECT_URI
    }
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    
    token_resp = requests.post('https://discord.com/api/v10/oauth2/token', data=token_data, headers=headers)
    token_json = token_resp.json()
    access_token = token_json.get('access_token')

    if not access_token:
        return "Failed to retrieve access token from Discord.", 400

    # Fetch user details using the access token
    user_headers = {'Authorization': f'Bearer {access_token}'}
    user_resp = requests.get('https://discord.com/api/v10/users/@me', headers=user_headers)
    user_data = user_resp.json()

    user_id = user_data.get('id')
    username = user_data.get('username')

    # Calculate account creation timestamp from Discord Snowflake ID
    if user_id:
        snowflake_time = ((int(user_id) >> 22) + 1420070400000) / 1000
        created_at = datetime.fromtimestamp(snowflake_time, tz=timezone.utc)
        account_age_days = (datetime.now(timezone.utc) - created_at).days
    else:
        account_age_days = 0

    # --- ALT ACCOUNT INSPECTION LOGIC ---
    if account_age_days < 3:
        return f"⚠️ Account @{username} is only {account_age_days} days old. Verification flagged for moderator review.", 200

    return f"✅ Account @{username} verified successfully! You can now close this tab and return to Discord.", 200


def run_flask():
    """Runs the Flask web server on Render's assigned dynamic port."""
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)


# -----------------------------------------------------------------------------
# 2. DISCORD BOT SETUP & SLASH COMMANDS
# -----------------------------------------------------------------------------
intents = discord.Intents.default()
intents.members = True

class DoubleCheckBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        print("Syncing DoubleCheck slash commands globally...")
        await self.tree.sync()
        print("Slash commands synced successfully!")

bot = DoubleCheckBot()

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name} ({bot.user.id})")

# --- SLASH COMMANDS ---

@bot.tree.command(name="verify", description="Get an instant link to verify your account.")
async def verify_command(interaction: discord.Interaction):
    verify_url = f"{RENDER_URL}/verify"

    embed = discord.Embed(
        title="🛡️ DoubleCheck Verification",
        description=f"Click the button below to verify your identity and unlock channels in **{interaction.guild.name}**.",
        color=discord.Color.blue()
    )
    
    view = discord.ui.View()
    button = discord.ui.Button(label="Verify Account", url=verify_url, style=discord.ButtonStyle.link)
    view.add_item(button)

    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


@bot.tree.command(name="check-user", description="[Mods Only] Scan a user account for alt risk indicators.")
@app_commands.checks.has_permissions(ban_members=True)
async def check_user_command(interaction: discord.Interaction, member: discord.Member):
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
        embed.add_field(name="⚠️ Risk Flag", value="High Risk: Very new account.", inline=False)
    else:
        embed.add_field(name="✅ Risk Flag", value="Pass: Meets account age threshold.", inline=False)

    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="setup-verify", description="[Admin Only] Create the verify channel, role, and message panel.")
@app_commands.checks.has_permissions(administrator=True)
async def setup_verify_command(interaction: discord.Interaction):
    guild = interaction.guild
    await interaction.response.defer(ephemeral=True)

    # 1. Create or get the "Verified" role
    verified_role = discord.utils.get(guild.roles, name="Verified")
    if not verified_role:
        verified_role = await guild.create_role(
            name="Verified",
            color=discord.Color.green(),
            reason="DoubleCheck automatic role setup"
        )

    # 2. Configure Overwrites for the #verify channel
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=True, send_messages=False),
        verified_role: discord.PermissionOverwrite(read_messages=False)
    }

    # 3. Create or get the #verify channel
    verify_channel = discord.utils.get(guild.text_channels, name="verify")
    if not verify_channel:
        verify_channel = await guild.create_text_channel(
            name="verify",
            overwrites=overwrites,
            reason="DoubleCheck automatic channel setup"
        )

    # 4. Send the persistent Panel Embed into #verify
    verify_url = f"{RENDER_URL}/verify"
    
    panel_embed = discord.Embed(
        title="🛡️ Welcome to " + guild.name,
        description=(
            "To gain full access to the server, you must verify your account.\n\n"
            "Click the button below to complete the verification process through **DoubleCheck**."
        ),
        color=discord.Color.blue()
    )
    panel_embed.set_footer(text="DoubleCheck Security Engine")

    view = discord.ui.View()
    button = discord.ui.Button(
        label="Verify Identity",
        url=verify_url,
        style=discord.ButtonStyle.link,
        emoji="🔐"
    )
    view.add_item(button)

    await verify_channel.send(embed=panel_embed, view=view)

    # 5. Confirm setup to Administrator
    await interaction.followup.send(
        f"✅ Setup complete! Created {verify_channel.mention} and configured the **{verified_role.name}** role.",
        ephemeral=True
    )


@bot.tree.command(name="status", description="Check operational status of DoubleCheck.")
async def status_command(interaction: discord.Interaction):
    latency = round(bot.latency * 1000)
    embed = discord.Embed(
        title="DoubleCheck Status",
        description=f"🟢 **System Operational**\n\n• **Latency:** {latency}ms\n• **Protected Guilds:** {len(bot.guilds)}",
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed)


# --- ERROR HANDLERS ---

@check_user_command.error
async def check_user_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("❌ You need the **Ban Members** permission to use this command.", ephemeral=True)

@setup_verify_command.error
async def setup_verify_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("❌ You need **Administrator** permissions to use `/setup-verify`.", ephemeral=True)


# -----------------------------------------------------------------------------
# 3. RUN BOTH SERVICES
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    # Start Flask on a background thread
    server_thread = threading.Thread(target=run_flask)
    server_thread.daemon = True
    server_thread.start()

    # Start the Discord Bot
    token = os.environ.get("DISCORD_TOKEN")
    if token:
        bot.run(token)
    else:
        print("Error: DISCORD_TOKEN environment variable not set.")
