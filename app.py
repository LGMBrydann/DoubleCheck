import os
import threading
from flask import Flask, render_template, jsonify
import discord
from discord.ext import commands

# --- Flask App ---
app = Flask(__name__)

# --- Discord Bot Setup ---
intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- Routes ---
@app.route('/')
def home():
    # Renders the template from templates/index.html
    return render_template('index.html')

@app.route('/api/stats')
def stats():
    # Sends live data to script.js
    if bot.is_ready():
        return jsonify({
            "status": "Online",
            "guild_count": len(bot.guilds),
            "latency": round(bot.latency * 1000)
        })
    return jsonify({
        "status": "Starting...",
        "guild_count": 0,
        "latency": 0
    })

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    server_thread = threading.Thread(target=run_flask)
    server_thread.daemon = True
    server_thread.start()

    token = os.environ.get("DISCORD_TOKEN")
    if token:
        bot.run(token)
    else:
        print("Error: DISCORD_TOKEN environment variable not set.")
